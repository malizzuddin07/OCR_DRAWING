"""Prepare an isolated candidate-training package from detector dataset v4.

This script validates the locked approval, copies the approved train/val/test
tiles without changing their drawing-level split, and carries forward the
reviewed negative tiles from package v1. It never starts training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
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
    if manifest.get("annotation_count") != 639 or manifest.get("drawing_count") != 11:
        raise ValueError("Dataset v4 must contain exactly 639 labels from 11 drawings")
    if approval.get("status") != "human_approved_for_candidate_training_preparation":
        raise ValueError("Dataset has no valid human training-preparation approval")
    if approval.get("approved_label_count") != 639:
        raise ValueError("Approval label count changed")
    expected = {
        "dataset_manifest_sha256": sha256(source / "dataset_manifest.json"),
        "labels_manifest_sha256": sha256(source / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(source / "data.yaml"),
    }
    for field, value in expected.items():
        if approval.get(field) != value:
            raise ValueError(f"Approved dataset changed after approval: {field}")
    if not manifest.get("drawing_level_split_no_tile_leakage"):
        raise ValueError("Drawing split leakage is not allowed")
    if not manifest.get("train_contains_all_classes"):
        raise ValueError("Training split does not contain every class")
    return manifest, approval


def drawing_lookup(manifest):
    result = {}
    for split, drawings in manifest["drawing_splits"].items():
        for drawing in drawings:
            if drawing in result:
                raise ValueError(f"Drawing appears in multiple splits: {drawing}")
            result[drawing] = split
    return result


def negative_drawing(stem: str, drawings):
    marker = "__negative_"
    if marker not in stem:
        return None
    drawing = stem.split(marker, 1)[0]
    return drawing if drawing in drawings else None


def copy_positive_tiles(source: Path, output: Path):
    tiles = Counter()
    objects = Counter()
    class_counts = {split: Counter() for split in SPLITS}
    for split in SPLITS:
        image_dir = source / "images" / split
        label_dir = source / "labels" / split
        images = {path.stem: path for path in image_dir.glob("*.png")}
        labels = {path.stem: path for path in label_dir.glob("*.txt")}
        if images.keys() != labels.keys():
            raise ValueError(f"{split}: source image/label names do not match")
        for stem in sorted(images):
            destination_image = output / "images" / split / images[stem].name
            destination_label = output / "labels" / split / labels[stem].name
            destination_image.parent.mkdir(parents=True, exist_ok=True)
            destination_label.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(images[stem], destination_image)
            shutil.copy2(labels[stem], destination_label)
            lines = [
                line.strip()
                for line in labels[stem].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            tiles[split] += 1
            objects[split] += len(lines)
            for line in lines:
                parts = line.split()
                if len(parts) != 5:
                    raise ValueError(f"Malformed YOLO row in {labels[stem]}: {line}")
                class_id = int(parts[0])
                if class_id < 0 or class_id >= len(CLASS_NAMES):
                    raise ValueError(f"Invalid class in {labels[stem]}: {class_id}")
                class_counts[split][CLASS_NAMES[class_id]] += 1
    return tiles, objects, class_counts


def carry_forward_negatives(previous: Path, output: Path, lookup):
    counts = Counter()
    details = []
    if not previous.is_dir():
        return counts, details
    seen = set()
    for prior_split in SPLITS:
        for label in sorted((previous / "labels" / prior_split).glob("*__negative_*.txt")):
            drawing = negative_drawing(label.stem, lookup)
            image = previous / "images" / prior_split / f"{label.stem}.png"
            if drawing is None or not image.is_file() or label.stem in seen:
                continue
            if label.read_text(encoding="utf-8").strip():
                raise ValueError(f"Negative label is not empty: {label}")
            split = lookup[drawing]
            destination_image = output / "images" / split / image.name
            destination_label = output / "labels" / split / label.name
            destination_image.parent.mkdir(parents=True, exist_ok=True)
            destination_label.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, destination_image)
            shutil.copy2(label, destination_label)
            seen.add(label.stem)
            counts[split] += 1
            details.append(
                {
                    "drawing": drawing,
                    "split": split,
                    "image": destination_image.relative_to(output).as_posix(),
                    "sha256": sha256(destination_image),
                }
            )
    return counts, details


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
    manifest, approval = validate_source(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    positive_tiles, positive_objects, class_counts = copy_positive_tiles(
        args.source, args.output
    )
    lookup = drawing_lookup(manifest)
    negative_tiles, negative_details = carry_forward_negatives(
        args.previous_package, args.output, lookup
    )
    missing_classes = [
        name for name in CLASS_NAMES if class_counts["train"].get(name, 0) == 0
    ]
    if missing_classes:
        raise ValueError(f"Training split is missing classes: {missing_classes}")
    if sum(positive_objects.values()) != 639:
        raise ValueError("Copied object total is not 639")

    write_data_yaml(args.output)
    shutil.copy2(
        args.source / "APPROVED_FOR_TRAINING_PREPARATION.json",
        args.output / "source_dataset_approval.json",
    )
    config = """# Isolated candidate v2 training. Production is not changed.
model: candidate_detector_v1_best.pt
data: data.yaml
epochs: 150
imgsz: 1280
batch: 4
device: 0
patience: 35
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v2
pretrained: true
plots: true
"""
    (args.output / "training_config.yaml").write_text(config, encoding="utf-8")
    package = {
        "schema_version": 2,
        "status": "prepared_not_trained",
        "source_dataset": str(args.source),
        "source_dataset_manifest_sha256": sha256(
            args.source / "dataset_manifest.json"
        ),
        "source_labels_manifest_sha256": sha256(args.source / "labels_manifest.csv"),
        "source_approval_sha256": sha256(
            args.source / "APPROVED_FOR_TRAINING_PREPARATION.json"
        ),
        "approved_drawing_count": 11,
        "approved_label_count": 639,
        "starting_model": "candidate_detector_v1_best.pt",
        "starting_model_is_production": False,
        "production_model_will_change": False,
        "drawing_level_split_no_tile_leakage": True,
        "training_splits": manifest["drawing_splits"],
        "positive_tiles": dict(positive_tiles),
        "negative_tiles": dict(negative_tiles),
        "positive_objects": dict(positive_objects),
        "class_counts_by_split": {
            split: {
                name: class_counts[split].get(name, 0) for name in CLASS_NAMES
            }
            for split in SPLITS
        },
        "train_contains_all_classes": True,
        "negative_tile_details": negative_details,
        "approval_status": approval["status"],
        "required_gate": (
            "Candidate v2 must pass validation and full OCR golden regression "
            "before production activation."
        ),
    }
    (args.output / "training_package_manifest.json").write_text(
        json.dumps(package, indent=2) + "\n", encoding="utf-8"
    )
    readme = f"""# Detector Candidate Training Package v2

Status: prepared only. Training has not started.

- Approved drawings: 11
- Approved boxes: 639
- Positive tiles: {sum(positive_tiles.values())}
- Reviewed negative tiles: {sum(negative_tiles.values())}
- Starting model: candidate detector v1 best.pt
- Production model changed: no

This package must be trained as an isolated candidate. Do not replace the
production model until the candidate passes the detector checks and the full
OCR golden regression gate.
"""
    (args.output / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(package, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--previous-package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
