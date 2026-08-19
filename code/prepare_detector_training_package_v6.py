"""Prepare candidate V6 using approved hard-example tiles and candidate V3."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(r"C:\Users\izzuddin\Desktop\OCR DRAWING")
BASE_BUILDER = ROOT / "code" / "prepare_detector_training_package_v5.py"
HARD_REVIEW = (
    ROOT
    / "golden_tests"
    / "HARD_EXAMPLE_REVIEW_W3_C111266801_20260731_V2"
)
EXPECTED_LABELS = 966
HARD_REPEAT_COUNT = 2


def load_builder():
    spec = importlib.util.spec_from_file_location("v5_builder", BASE_BUILDER)
    if spec is None or spec.loader is None:
        raise ImportError(BASE_BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_manifest_rows(source: Path):
    with (source / "labels_manifest.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_LABELS:
        raise ValueError(f"Expected {EXPECTED_LABELS} labels, found {len(rows)}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--previous-package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    builder = load_builder()
    source = args.source.resolve()
    review_payload = json.loads(
        (HARD_REVIEW / "W3-C111266801-01_hard_labels.json").read_text(
            encoding="utf-8"
        )
    )
    if review_payload.get("label_count") != 21:
        raise ValueError("Expected 21 approved hard examples")
    hard_balloons = {
        str(item["balloons"]).strip() for item in review_payload["labels"]
    }
    source_rows = read_manifest_rows(source)
    hard_tiles = {
        row["Tile"].replace("\\", "/")
        for row in source_rows
        if row["Drawing"] == "W3-C111266801-01"
        and str(row["Balloons"]).strip() in hard_balloons
    }
    if not hard_tiles:
        raise ValueError("No hard-example training tiles were resolved")
    hard_tile_stems = {Path(tile).stem for tile in hard_tiles}

    def validate_source(source_path: Path):
        required = [
            "dataset_manifest.json",
            "labels_manifest.csv",
            "data.yaml",
            "APPROVED_FOR_TRAINING_PREPARATION.json",
        ]
        missing = [name for name in required if not (source_path / name).is_file()]
        if missing:
            raise FileNotFoundError(f"Dataset v7 is incomplete: {missing}")
        manifest = builder.load_json(source_path / "dataset_manifest.json")
        approval = builder.load_json(
            source_path / "APPROVED_FOR_TRAINING_PREPARATION.json"
        )
        if (
            manifest.get("annotation_count") != EXPECTED_LABELS
            or manifest.get("drawing_count") != 17
        ):
            raise ValueError("Dataset v7 count is not 966 labels / 17 drawings")
        if (
            approval.get("status")
            != "human_approved_for_candidate_training_preparation"
            or approval.get("approved_label_count") != EXPECTED_LABELS
        ):
            raise ValueError("Dataset v7 has no valid human approval")
        for field, filename in (
            ("dataset_manifest_sha256", "dataset_manifest.json"),
            ("labels_manifest_sha256", "labels_manifest.csv"),
            ("data_yaml_sha256", "data.yaml"),
        ):
            if approval.get(field) != builder.sha256(source_path / filename):
                raise ValueError(f"Dataset v7 changed after approval: {field}")
        return manifest, approval

    def read_rows(source_path: Path):
        return read_manifest_rows(source_path)

    def copy_approved_tiles(source_path, output, lookup, rows):
        rows_by_tile = defaultdict(list)
        for row in rows:
            drawing = row["Drawing"].strip()
            if drawing not in lookup:
                raise ValueError(f"Drawing missing from split plan: {drawing}")
            rows_by_tile[row["Tile"].replace("\\", "/")].append(row)

        split_tiles = Counter()
        split_objects = Counter()
        split_classes = {split: Counter() for split in builder.SPLITS}
        training_tiles = []
        for relative_tile, tile_rows in sorted(rows_by_tile.items()):
            drawing = tile_rows[0]["Drawing"].strip()
            original_split = tile_rows[0]["Split"].strip()
            target_split = lookup[drawing]
            image_source = source_path / relative_tile
            label_source = (
                source_path
                / "labels"
                / original_split
                / f"{image_source.stem}.txt"
            )
            if not image_source.is_file() or not label_source.is_file():
                raise FileNotFoundError(image_source)
            lines, label_counts = builder.parse_yolo_label(label_source)
            expected = Counter(row["Class"].strip() for row in tile_rows)
            if label_counts != expected:
                raise ValueError(f"Manifest/YOLO mismatch: {relative_tile}")
            image_destination = (
                output / "images" / target_split / image_source.name
            )
            label_destination = (
                output / "labels" / target_split / label_source.name
            )
            image_destination.parent.mkdir(parents=True, exist_ok=True)
            label_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_source, image_destination)
            shutil.copy2(label_source, label_destination)
            split_tiles[target_split] += 1
            split_objects[target_split] += len(lines)
            split_classes[target_split].update(label_counts)
            if target_split == "train":
                training_tiles.append(
                    {
                        "drawing": drawing,
                        "image": image_destination,
                        "label": label_destination,
                        "counts": label_counts,
                    }
                )
        if sum(split_objects.values()) != EXPECTED_LABELS:
            raise ValueError("Copied approved-object total is not 966")
        return training_tiles, split_tiles, split_objects, split_classes

    def repeat_hard_tiles(output, training_tiles, original_counts):
        effective = Counter(original_counts)
        details = []
        selected = [
            tile for tile in training_tiles if tile["image"].stem in hard_tile_stems
        ]
        if {tile["image"].stem for tile in selected} != hard_tile_stems:
            raise ValueError("Not every approved hard tile is in the train split")
        for source_tile in sorted(selected, key=lambda item: item["image"].stem):
            for repeat in range(1, HARD_REPEAT_COUNT + 1):
                suffix = f"__v6hard_{repeat:02d}"
                image_destination = (
                    output
                    / "images"
                    / "train"
                    / f"{source_tile['image'].stem}{suffix}.png"
                )
                label_destination = (
                    output
                    / "labels"
                    / "train"
                    / f"{source_tile['label'].stem}{suffix}.txt"
                )
                shutil.copy2(source_tile["image"], image_destination)
                shutil.copy2(source_tile["label"], label_destination)
                effective.update(source_tile["counts"])
                details.append(
                    {
                        "purpose": "approved_hard_example_repetition",
                        "source_drawing": source_tile["drawing"],
                        "source_image": source_tile["image"].name,
                        "repeated_image": image_destination.name,
                        "repeat": repeat,
                        "object_counts": dict(source_tile["counts"]),
                    }
                )
        return effective, details

    builder.validate_source = validate_source
    builder.read_rows = read_rows
    builder.copy_approved_tiles = copy_approved_tiles
    builder.oversample_rare_training_tiles = repeat_hard_tiles
    builder.RARE_CLASS_TARGETS = {}
    builder.prepare(args)

    manifest_path = args.output / "training_package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("test_drawings_reserved_from_candidate_v5_training", None)
    manifest.update(
        {
            "schema_version": 6,
            "status": "prepared_not_trained",
            "approved_label_count": EXPECTED_LABELS,
            "starting_model": "candidate_detector_v3_best.pt",
            "candidate_name": "golden_detector_v6",
            "strategy": "candidate_v3_plus_approved_hard_example_tile_repetition",
            "hard_example_count": 21,
            "hard_example_unique_tile_count": len(hard_tile_stems),
            "hard_repeat_count_per_tile": HARD_REPEAT_COUNT,
            "test_drawings_reserved_from_candidate_v6_training": True,
            "hard_example_review": str(HARD_REVIEW),
            "rare_class_targets": {},
            "required_gate": (
                "Candidate V6 must introduce no regression or false extra on the "
                "reserved detector set, improve W3-C111266801-01 hard examples, "
                "and pass the complete OCR golden regression before activation."
            ),
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    config = """# Candidate V6: conservative hard-example fine-tuning from V3.
model: candidate_detector_v3_best.pt
data: runtime_data.yaml
epochs: 60
imgsz: 1280
batch: 4
device: 0
patience: 20
optimizer: AdamW
lr0: 0.00002
lrf: 0.1
freeze: 10
box: 10.0
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v6
fliplr: 0.0
flipud: 0.0
mosaic: 0.0
mixup: 0.0
erasing: 0.0
hsv_h: 0.0
hsv_s: 0.0
hsv_v: 0.03
"""
    (args.output / "training_config.yaml").write_text(config, encoding="utf-8")
    (args.output / "README.md").write_text(
        "# Detector Candidate Training Package V6\n\n"
        "This isolated package uses 966 human-approved labels. It starts from "
        "Candidate V3 and repeats only the approved hard-example training tiles "
        "twice. Validation and test drawings are not repeated. Production is "
        "not changed by this package.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "approved_labels": EXPECTED_LABELS,
                "hard_examples": 21,
                "hard_tiles": len(hard_tile_stems),
                "hard_repeats": len(manifest["oversampling_details"]),
                "starting_model": "candidate_detector_v3_best.pt",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
