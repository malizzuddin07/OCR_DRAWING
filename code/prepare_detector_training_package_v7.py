"""Prepare conservative candidate V7 from V3 with diverse rehearsal tiles.

Candidate V6 over-specialized on one hard drawing and regressed on the untouched
C3010 test drawing. V7 keeps the same approved labels and drawing-level split,
uses each approved hard tile once, and adds broad dimension/surface-finish
rehearsal from the training drawings. Reserved validation/test drawings are
never duplicated or used for training.
"""

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
HARD_REPEAT_COUNT = 1
REHEARSAL_CLASSES = ("dimension", "surface_finish")


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
    source_rows = read_manifest_rows(source)
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
    hard_tiles = {
        row["Tile"].replace("\\", "/")
        for row in source_rows
        if row["Drawing"] == "W3-C111266801-01"
        and str(row["Balloons"]).strip() in hard_balloons
    }
    if not hard_tiles:
        raise ValueError("No approved hard-example tiles were resolved")
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
            raise FileNotFoundError(f"Approved dataset is incomplete: {missing}")
        manifest = builder.load_json(source_path / "dataset_manifest.json")
        approval = builder.load_json(
            source_path / "APPROVED_FOR_TRAINING_PREPARATION.json"
        )
        if (
            manifest.get("annotation_count") != EXPECTED_LABELS
            or manifest.get("drawing_count") != 17
        ):
            raise ValueError("Approved dataset is not 966 labels / 17 drawings")
        if (
            approval.get("status")
            != "human_approved_for_candidate_training_preparation"
            or approval.get("approved_label_count") != EXPECTED_LABELS
        ):
            raise ValueError("Approved dataset has no valid human approval")
        for field, filename in (
            ("dataset_manifest_sha256", "dataset_manifest.json"),
            ("labels_manifest_sha256", "labels_manifest.csv"),
            ("data_yaml_sha256", "data.yaml"),
        ):
            if approval.get(field) != builder.sha256(source_path / filename):
                raise ValueError(f"Approved dataset changed after approval: {field}")
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

    def choose_rehearsal_tiles(training_tiles):
        by_drawing = defaultdict(list)
        for tile in training_tiles:
            by_drawing[tile["drawing"]].append(tile)
        selected = {}
        for drawing in builder.DRAWING_SPLITS["train"]:
            candidates = by_drawing[drawing]
            if not candidates:
                raise ValueError(f"No training tiles found for {drawing}")
            drawing_selected = set()
            for class_name in REHEARSAL_CLASSES:
                class_candidates = [
                    tile
                    for tile in candidates
                    if tile["counts"].get(class_name, 0) > 0
                ]
                if not class_candidates:
                    continue
                unused = [
                    tile
                    for tile in class_candidates
                    if tile["image"].stem not in drawing_selected
                    and tile["image"].stem not in hard_tile_stems
                ]
                pool = unused or [
                    tile
                    for tile in class_candidates
                    if tile["image"].stem not in drawing_selected
                ]
                pool = pool or class_candidates
                pool.sort(
                    key=lambda tile: (
                        -tile["counts"].get(class_name, 0),
                        -sum(tile["counts"].values()),
                        tile["image"].stem,
                    )
                )
                chosen = pool[0]
                stem = chosen["image"].stem
                drawing_selected.add(stem)
                entry = selected.setdefault(
                    stem, {"tile": chosen, "purposes": []}
                )
                entry["purposes"].append(class_name)
        covered_drawings = {entry["tile"]["drawing"] for entry in selected.values()}
        if covered_drawings != set(builder.DRAWING_SPLITS["train"]):
            missing = set(builder.DRAWING_SPLITS["train"]) - covered_drawings
            raise ValueError(f"Rehearsal does not cover training drawings: {missing}")
        for class_name in REHEARSAL_CLASSES:
            if not any(
                class_name in entry["purposes"] for entry in selected.values()
            ):
                raise ValueError(f"No rehearsal tile selected for {class_name}")
        return selected

    def copy_repeat(output, source_tile, suffix):
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
        return image_destination

    def repeat_protected_tiles(output, training_tiles, original_counts):
        effective = Counter(original_counts)
        details = []
        hard_selected = [
            tile for tile in training_tiles if tile["image"].stem in hard_tile_stems
        ]
        if {tile["image"].stem for tile in hard_selected} != hard_tile_stems:
            raise ValueError("Not every approved hard tile is in the train split")
        for source_tile in sorted(hard_selected, key=lambda item: item["image"].stem):
            for repeat in range(1, HARD_REPEAT_COUNT + 1):
                destination = copy_repeat(
                    output, source_tile, f"__v7hard_{repeat:02d}"
                )
                effective.update(source_tile["counts"])
                details.append(
                    {
                        "purpose": "approved_hard_example_repetition",
                        "source_drawing": source_tile["drawing"],
                        "source_image": source_tile["image"].name,
                        "repeated_image": destination.name,
                        "repeat": repeat,
                        "object_counts": dict(source_tile["counts"]),
                    }
                )

        rehearsal = choose_rehearsal_tiles(training_tiles)
        for stem, entry in sorted(rehearsal.items()):
            source_tile = entry["tile"]
            destination = copy_repeat(output, source_tile, "__v7rehearsal_01")
            effective.update(source_tile["counts"])
            details.append(
                {
                    "purpose": "diverse_regression_rehearsal",
                    "protected_classes": entry["purposes"],
                    "source_drawing": source_tile["drawing"],
                    "source_image": source_tile["image"].name,
                    "repeated_image": destination.name,
                    "object_counts": dict(source_tile["counts"]),
                }
            )
        return effective, details

    builder.validate_source = validate_source
    builder.read_rows = read_rows
    builder.copy_approved_tiles = copy_approved_tiles
    builder.oversample_rare_training_tiles = repeat_protected_tiles
    builder.RARE_CLASS_TARGETS = {}
    builder.prepare(args)

    manifest_path = args.output / "training_package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    details = manifest["oversampling_details"]
    hard_details = [
        item
        for item in details
        if item["purpose"] == "approved_hard_example_repetition"
    ]
    rehearsal_details = [
        item
        for item in details
        if item["purpose"] == "diverse_regression_rehearsal"
    ]
    rehearsal_drawings = {
        item["source_drawing"] for item in rehearsal_details
    }
    manifest.pop("test_drawings_reserved_from_candidate_v5_training", None)
    manifest.update(
        {
            "schema_version": 7,
            "status": "prepared_not_trained",
            "approved_label_count": EXPECTED_LABELS,
            "starting_model": "candidate_detector_v3_best.pt",
            "candidate_name": "golden_detector_v7",
            "strategy": (
                "candidate_v3_plus_single_hard_repeat_and_diverse_regression_rehearsal"
            ),
            "hard_example_count": 21,
            "hard_example_unique_tile_count": len(hard_tile_stems),
            "hard_repeat_count_per_tile": HARD_REPEAT_COUNT,
            "hard_repeat_tile_count": len(hard_details),
            "rehearsal_classes": list(REHEARSAL_CLASSES),
            "rehearsal_unique_tile_count": len(rehearsal_details),
            "rehearsal_drawing_count": len(rehearsal_drawings),
            "test_drawings_reserved_from_candidate_v7_training": True,
            "c3010_used_for_training": False,
            "hard_example_review": str(HARD_REVIEW),
            "rare_class_targets": {},
            "previous_candidate_gate": {
                "candidate": "V6",
                "status": "rejected",
                "v3_matches": 17,
                "v6_matches": 14,
                "fixed": 3,
                "regressions": 6,
                "extras": 0,
                "regression_drawing": "C3010-035-250F",
                "regression_classes": ["dimension", "surface_finish"],
            },
            "required_gate": (
                "Candidate V7 must have zero regression and zero false extra "
                "against V3 on all three untouched reserved drawings, improve "
                "the approved W3-C111266801-01 hard examples, and pass the "
                "complete OCR golden regression before activation."
            ),
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    config = """# Candidate V7: conservative V3 fine-tuning with diverse rehearsal.
model: candidate_detector_v3_best.pt
data: runtime_data.yaml
epochs: 60
imgsz: 1280
batch: 4
device: 0
patience: 18
optimizer: AdamW
lr0: 0.00001
lrf: 0.1
weight_decay: 0.001
freeze: 10
box: 10.0
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v7
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
        "# Detector Candidate Training Package V7\n\n"
        "This isolated package uses 966 unchanged human-approved labels and "
        "starts from Candidate V3. It repeats each approved hard tile once and "
        "adds diverse dimension/surface-finish rehearsal from every training "
        "drawing. C3010 and every validation/test drawing remain untouched. "
        "Production is not changed by this package.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "approved_labels": EXPECTED_LABELS,
                "hard_examples": 21,
                "hard_tiles": len(hard_tile_stems),
                "hard_repeats": len(hard_details),
                "rehearsal_tiles": len(rehearsal_details),
                "rehearsal_drawings": len(rehearsal_drawings),
                "starting_model": "candidate_detector_v3_best.pt",
                "production_model_will_change": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
