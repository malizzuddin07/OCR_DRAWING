"""Build an isolated, balanced detector candidate-v5 training package.

The approved detector_dataset_v6 annotations are never edited. This builder:

1. reassigns whole drawings to a better train/val/test split;
2. preserves drawing-level isolation;
3. copies the reviewed negative tiles;
4. duplicates only approved training tiles containing rare classes.

Validation and test images are never duplicated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


CLASS_NAMES = [
    "dimension",
    "diameter",
    "radius",
    "chamfer_callout",
    "thread_callout",
    "hole_callout",
    "surface_finish",
    "gdt_frame",
]
SPLITS = ("train", "val", "test")

# Whole drawings remain isolated so no tile from one drawing crosses splits.
# The newest Drawing 6 stays in test and is never used for candidate-v5 training.
DRAWING_SPLITS = {
    "train": [
        "C3020-060-201F-02",
        "FAB-C-3060-010-9100 W3-C100807301-00",
        "W3-C090489701-1A",
        "W3-C111260501-01",
        "W3-C111262601-02",
        "W3-C111262801-2A",
        "W3-C111262901-0B",
        "W3-C111265901-03",
        "W3-C111266801-01",
    ],
    "val": [
        "W3-C081236901-00",
        "W3-C081779801-00",
        "W3-C111260901-0B",
        "W3-C111265401-00",
        "W3-C171246401-00",
    ],
    "test": [
        "C3010-035-250F",
        "W3-C111262701-01",
        "W3-C111266101-01",
    ],
}

# These are effective training-instance targets, not new annotations. V4 only
# balanced diameter and chamfer. V5 balances every underrepresented symbol
# class, including surface finish and GD&T, which regressed in V4.
RARE_CLASS_TARGETS = {
    "diameter": 24,
    "radius": 45,
    "chamfer_callout": 45,
    "thread_callout": 55,
    "hole_callout": 55,
    "surface_finish": 90,
    "gdt_frame": 60,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source(source: Path):
    required = [
        "dataset_manifest.json",
        "labels_manifest.csv",
        "data.yaml",
        "APPROVED_FOR_TRAINING_PREPARATION.json",
    ]
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Approved dataset is incomplete: {missing}")

    manifest = load_json(source / "dataset_manifest.json")
    approval = load_json(source / "APPROVED_FOR_TRAINING_PREPARATION.json")
    if manifest.get("annotation_count") != 965 or manifest.get("drawing_count") != 17:
        raise ValueError("Dataset v6 must contain exactly 965 labels from 17 drawings")
    if approval.get("status") != "human_approved_for_candidate_training_preparation":
        raise ValueError("Dataset has no valid human approval")
    if approval.get("approved_label_count") != 965:
        raise ValueError("Approved label count changed")

    expected_hashes = {
        "dataset_manifest_sha256": sha256(source / "dataset_manifest.json"),
        "labels_manifest_sha256": sha256(source / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(source / "data.yaml"),
    }
    for field, actual in expected_hashes.items():
        if approval.get(field) != actual:
            raise ValueError(f"Approved dataset changed after approval: {field}")
    return manifest, approval


def split_lookup():
    lookup = {}
    for split, drawings in DRAWING_SPLITS.items():
        for drawing in drawings:
            if drawing in lookup:
                raise ValueError(f"Drawing appears in multiple splits: {drawing}")
            lookup[drawing] = split
    if len(lookup) != 17:
        raise ValueError(f"Expected 17 unique split drawings, found {len(lookup)}")
    return lookup


def read_rows(source: Path):
    with (source / "labels_manifest.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 965:
        raise ValueError(f"Expected 965 manifest rows, found {len(rows)}")
    return rows


def parse_yolo_label(path: Path):
    counts = Counter()
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Malformed YOLO row in {path}: {line}")
        class_id = int(parts[0])
        if class_id < 0 or class_id >= len(CLASS_NAMES):
            raise ValueError(f"Invalid class ID in {path}: {class_id}")
        for value in parts[1:]:
            number = float(value)
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"Out-of-range YOLO coordinate in {path}: {line}")
        counts[CLASS_NAMES[class_id]] += 1
        lines.append(line)
    return lines, counts


def copy_approved_tiles(source: Path, output: Path, lookup, rows):
    rows_by_tile = defaultdict(list)
    for row in rows:
        drawing = row["Drawing"].strip()
        if drawing not in lookup:
            raise ValueError(f"Drawing is missing from v3 split plan: {drawing}")
        rows_by_tile[row["Tile"].replace("\\", "/")].append(row)

    split_tiles = Counter()
    split_objects = Counter()
    split_classes = {split: Counter() for split in SPLITS}
    training_tiles = []

    for relative_tile, tile_rows in sorted(rows_by_tile.items()):
        drawing = tile_rows[0]["Drawing"].strip()
        original_split = tile_rows[0]["Split"].strip()
        target_split = lookup[drawing]
        image_source = source / relative_tile
        label_source = (
            source / "labels" / original_split / f"{image_source.stem}.txt"
        )
        if not image_source.is_file() or not label_source.is_file():
            raise FileNotFoundError(
                f"Missing approved image/label pair: {image_source}, {label_source}"
            )

        lines, label_counts = parse_yolo_label(label_source)
        manifest_counts = Counter(row["Class"].strip() for row in tile_rows)
        if label_counts != manifest_counts:
            raise ValueError(f"Manifest/YOLO mismatch for {image_source.name}")

        image_destination = output / "images" / target_split / image_source.name
        label_destination = output / "labels" / target_split / label_source.name
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

    if sum(split_objects.values()) != 965:
        raise ValueError("Copied approved-object total is not 965")
    return training_tiles, split_tiles, split_objects, split_classes


def negative_drawing(stem: str, drawings):
    marker = "__negative_"
    if marker not in stem:
        return None
    drawing = stem.split(marker, 1)[0]
    return drawing if drawing in drawings else None


def copy_negatives(previous: Path, output: Path, lookup):
    counts = Counter()
    details = []
    seen = set()
    if not previous.is_dir():
        return counts, details
    for previous_split in SPLITS:
        label_dir = previous / "labels" / previous_split
        for label in sorted(label_dir.glob("*__negative_*.txt")):
            drawing = negative_drawing(label.stem, lookup)
            image = previous / "images" / previous_split / f"{label.stem}.png"
            if drawing is None or not image.is_file() or label.stem in seen:
                continue
            if label.read_text(encoding="utf-8").strip():
                raise ValueError(f"Reviewed negative label is not empty: {label}")
            target_split = lookup[drawing]
            image_destination = output / "images" / target_split / image.name
            label_destination = output / "labels" / target_split / label.name
            image_destination.parent.mkdir(parents=True, exist_ok=True)
            label_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, image_destination)
            shutil.copy2(label, label_destination)
            seen.add(label.stem)
            counts[target_split] += 1
            details.append(
                {
                    "drawing": drawing,
                    "split": target_split,
                    "image": image_destination.relative_to(output).as_posix(),
                    "sha256": sha256(image_destination),
                }
            )
    return counts, details


def oversample_rare_training_tiles(output: Path, training_tiles, original_counts):
    effective = Counter(original_counts)
    duplicate_counts = Counter()
    details = []

    for class_name, target in RARE_CLASS_TARGETS.items():
        candidates = [
            tile for tile in training_tiles if tile["counts"].get(class_name, 0) > 0
        ]
        if not candidates:
            raise ValueError(f"No training tile contains rare class {class_name}")
        while effective[class_name] < target:
            candidates.sort(
                key=lambda tile: (
                    duplicate_counts[tile["image"].stem],
                    sum(tile["counts"].values()),
                    tile["image"].stem,
                )
            )
            source_tile = candidates[0]
            stem = source_tile["image"].stem
            duplicate_counts[stem] += 1
            duplicate_number = duplicate_counts[stem]
            if duplicate_number > 6:
                raise ValueError(
                    f"Rare-class oversampling exceeded safe cap for {stem}"
                )
            suffix = f"__v5repeat_{duplicate_number:02d}"
            image_destination = (
                output
                / "images"
                / "train"
                / f"{source_tile['image'].stem}{suffix}{source_tile['image'].suffix}"
            )
            label_destination = (
                output
                / "labels"
                / "train"
                / f"{source_tile['label'].stem}{suffix}{source_tile['label'].suffix}"
            )
            shutil.copy2(source_tile["image"], image_destination)
            shutil.copy2(source_tile["label"], label_destination)
            effective.update(source_tile["counts"])
            details.append(
                {
                    "target_class": class_name,
                    "source_drawing": source_tile["drawing"],
                    "source_image": source_tile["image"].name,
                    "repeated_image": image_destination.name,
                    "object_counts": dict(source_tile["counts"]),
                }
            )
    return effective, details


def write_data_yaml(output: Path):
    content = [
        "path: .",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    content.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    (output / "data.yaml").write_text("\n".join(content) + "\n", encoding="utf-8")


def prepare(args):
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"Output folder is not empty: {args.output}")
    source_manifest, approval = validate_source(args.source)
    lookup = split_lookup()
    source_drawings = {
        drawing
        for drawings in source_manifest["drawing_splits"].values()
        for drawing in drawings
    }
    if source_drawings != set(lookup):
        raise ValueError("The v3 split plan does not match all approved drawings")

    args.output.mkdir(parents=True, exist_ok=True)
    rows = read_rows(args.source)
    (
        training_tiles,
        positive_tiles,
        positive_objects,
        class_counts,
    ) = copy_approved_tiles(args.source, args.output, lookup, rows)
    negative_tiles, negative_details = copy_negatives(
        args.previous_package, args.output, lookup
    )

    for split in SPLITS:
        missing = [name for name in CLASS_NAMES if class_counts[split][name] == 0]
        if missing:
            raise ValueError(f"{split} split is missing classes: {missing}")

    effective_train_counts, oversampling_details = oversample_rare_training_tiles(
        args.output, training_tiles, class_counts["train"]
    )
    for name, target in RARE_CLASS_TARGETS.items():
        if effective_train_counts[name] < target:
            raise ValueError(f"Effective {name} count did not reach {target}")

    write_data_yaml(args.output)
    shutil.copy2(
        args.source / "APPROVED_FOR_TRAINING_PREPARATION.json",
        args.output / "source_dataset_approval.json",
    )

    training_config = """# Candidate v5: localization-focused engineering-drawing fine-tuning.
model: candidate_detector_v3_best.pt
data: runtime_data.yaml
epochs: 100
imgsz: 1280
batch: 4
device: 0
patience: 30
optimizer: AdamW
lr0: 0.00005
lrf: 0.1
freeze: 5
box: 10.0
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v5
fliplr: 0.0
flipud: 0.0
mosaic: 0.0
mixup: 0.0
erasing: 0.0
hsv_h: 0.0
hsv_s: 0.0
hsv_v: 0.05
"""
    (args.output / "training_config.yaml").write_text(
        training_config, encoding="utf-8"
    )

    package_manifest = {
        "schema_version": 5,
        "status": "prepared_not_trained",
        "source_dataset": str(args.source),
        "source_dataset_manifest_sha256": sha256(
            args.source / "dataset_manifest.json"
        ),
        "source_labels_manifest_sha256": sha256(
            args.source / "labels_manifest.csv"
        ),
        "source_approval_sha256": sha256(
            args.source / "APPROVED_FOR_TRAINING_PREPARATION.json"
        ),
        "approved_drawing_count": 17,
        "approved_label_count": 965,
        "starting_model": "candidate_detector_v3_best.pt",
        "starting_model_is_production": False,
        "production_model_will_change": False,
        "drawing_level_split_no_tile_leakage": True,
        "training_splits": DRAWING_SPLITS,
        "test_drawings_reserved_from_candidate_v5_training": True,
        "positive_tiles": dict(positive_tiles),
        "negative_tiles": dict(negative_tiles),
        "positive_objects": dict(positive_objects),
        "class_counts_by_split": {
            split: {name: class_counts[split][name] for name in CLASS_NAMES}
            for split in SPLITS
        },
        "rare_class_targets": RARE_CLASS_TARGETS,
        "effective_train_class_counts": {
            name: effective_train_counts[name] for name in CLASS_NAMES
        },
        "oversampled_training_tile_count": len(oversampling_details),
        "oversampling_details": oversampling_details,
        "negative_tile_details": negative_details,
        "all_classes_present_in_every_split": True,
        "approval_status": approval["status"],
        "required_gate": (
            "Candidate v5 must beat candidate v3 on the same independent detector "
            "test set without important class regression, then pass the full OCR "
            "golden regression before production activation."
        ),
    }
    (args.output / "training_package_manifest.json").write_text(
        json.dumps(package_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "README.md").write_text(
        "# Detector Candidate Training Package v5\n\n"
        "This is an isolated candidate package. It uses 965 unchanged, approved "
        "annotations. Only approved training tiles containing rare classes are "
        "repeated. Validation and test tiles are never repeated. Production is "
        "not changed by this package.\n",
        encoding="utf-8",
    )
    print(json.dumps(package_manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--previous-package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
