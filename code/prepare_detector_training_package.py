"""Prepare a safe candidate-training package from approved detector dataset v3.

This script never starts training and never uploads data. It reorganizes the
approved tiles using a drawing-level split that covers all classes in training,
and adds a small set of clean negative tiles to reduce false detections on notes
and drawing lines.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_golden_detector_dataset import tile_starts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "golden_tests" / "detector_dataset_v3"
DEFAULT_OUTPUT = PROJECT_ROOT / "golden_tests" / "detector_training_package_v1"

# Keep whole drawings in one split. This arrangement is deliberate: the prior
# split had no diameter examples in train. The test drawing covers all 8 classes.
TRAINING_SPLITS = {
    "train": ["C3010-035-250F", "W3-C111262801-2A", "W3-C111265901-03"],
    "val": ["W3-C111266801-01"],
    "test": ["W3-C171246401-00"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def split_lookup():
    return {drawing: split for split, drawings in TRAINING_SPLITS.items() for drawing in drawings}


def boxes_intersect(tile, box):
    tx, ty, tw, th = tile
    x, y, width, height = box
    return x < tx + tw and x + width > tx and y < ty + th and y + height > ty


def ink_density(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float((gray < 220).sum()) / float(gray.size)


def validate_source(source_root: Path):
    required = [
        "dataset_manifest.json",
        "labels_manifest.csv",
        "data.yaml",
        "APPROVED_FOR_TRAINING_PREPARATION.json",
    ]
    missing = [name for name in required if not (source_root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Approved source dataset is incomplete: {missing}")
    manifest = load_json(source_root / "dataset_manifest.json")
    if manifest.get("annotation_count") != 303:
        raise ValueError("Approved source must contain exactly 303 physical callout labels")
    if manifest.get("human_box_override_count") != 3:
        raise ValueError("Approved source must contain the three reviewed box corrections")
    approval = load_json(source_root / "APPROVED_FOR_TRAINING_PREPARATION.json")
    if approval.get("status") != "human_approved_for_candidate_training_preparation":
        raise ValueError("Source detector dataset has no valid human training-preparation approval")
    if approval.get("approved_label_count") != manifest.get("annotation_count"):
        raise ValueError("Approval label count does not match the source manifest")
    expected_hashes = {
        "dataset_manifest_sha256": sha256(source_root / "dataset_manifest.json"),
        "labels_manifest_sha256": sha256(source_root / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(source_root / "data.yaml"),
    }
    for field, actual_hash in expected_hashes.items():
        if approval.get(field) != actual_hash:
            raise ValueError(f"Approved source changed after approval: {field}")
    return manifest


def find_label_path(source_root, relative_image):
    relative = Path(relative_image)
    parts = list(relative.parts)
    if not parts or parts[0] != "images":
        raise ValueError(f"Unexpected source tile path: {relative_image}")
    parts[0] = "labels"
    return source_root.joinpath(*parts).with_suffix(".txt")


def write_data_yaml(output_root, classes):
    lines = ["path: .", "train: images/train", "val: images/val", "test: images/test", "names:"]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(classes))
    (output_root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_training_config(output_root):
    content = """# Candidate training configuration. Preparation only; training is not started.
model: yolov8s.pt
data: data.yaml
epochs: 150
imgsz: 1280
batch: 4
device: auto
patience: 30
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v1
pretrained: true
plots: true
"""
    (output_root / "training_config.yaml").write_text(content, encoding="utf-8")


def prepare(source_root, output_root, negatives_per_drawing=4):
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output folder is not empty: {output_root}")
    source_manifest = validate_source(source_root)
    rows = load_csv(source_root / "labels_manifest.csv")
    lookup = split_lookup()
    if set(lookup) != {item["drawing"] for item in source_manifest["drawings"]}:
        raise ValueError("Training split drawings do not match the approved source drawings")

    output_root.mkdir(parents=True, exist_ok=True)
    tile_rows = defaultdict(list)
    drawing_boxes = defaultdict(list)
    for row in rows:
        tile_rows[row["Tile"]].append(row)
        drawing_boxes[row["Drawing"]].append(
            (float(row["X"]), float(row["Y"]), float(row["Width"]), float(row["Height"]))
        )

    positive_tiles = Counter()
    positive_objects = Counter()
    class_by_split = {split: Counter() for split in TRAINING_SPLITS}
    copied_tiles = set()
    for relative_image, tile_records in sorted(tile_rows.items()):
        drawing = tile_records[0]["Drawing"]
        split = lookup[drawing]
        source_image = source_root / relative_image
        source_label = find_label_path(source_root, relative_image)
        destination_image = output_root / "images" / split / source_image.name
        destination_label = output_root / "labels" / split / source_label.name
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        destination_label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, destination_image)
        shutil.copy2(source_label, destination_label)
        copied_tiles.add((drawing, source_image.stem))
        positive_tiles[split] += 1
        positive_objects[split] += len(tile_records)
        for record in tile_records:
            class_by_split[split][record["Class"]] += 1

    negative_tiles = Counter()
    negative_details = []
    tile_size = int(source_manifest["tile_size"])
    overlap = int(source_manifest["tile_overlap"])
    source_drawings = {item["drawing"]: item for item in source_manifest["drawings"]}
    for drawing in sorted(lookup):
        split = lookup[drawing]
        image_path = Path(source_drawings[drawing]["source_image"])
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read source image: {image_path}")
        height, width = image.shape[:2]
        candidates = []
        for y in tile_starts(height, tile_size, overlap):
            for x in tile_starts(width, tile_size, overlap):
                tile = (x, y, min(tile_size, width), min(tile_size, height))
                if any(boxes_intersect(tile, box) for box in drawing_boxes[drawing]):
                    continue
                crop = image[y : y + tile[3], x : x + tile[2]]
                density = ink_density(crop)
                if density < 0.002:
                    continue
                candidates.append((density, tile, crop))
        for density, tile, crop in sorted(candidates, key=lambda item: item[0], reverse=True)[:negatives_per_drawing]:
            x, y, _, _ = tile
            stem = f"{drawing}__negative_x{x:04d}_y{y:04d}"
            image_output = output_root / "images" / split / f"{stem}.png"
            label_output = output_root / "labels" / split / f"{stem}.txt"
            image_output.parent.mkdir(parents=True, exist_ok=True)
            label_output.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(image_output), crop):
                raise OSError(f"Could not write negative tile: {image_output}")
            label_output.write_text("", encoding="utf-8")
            negative_tiles[split] += 1
            negative_details.append(
                {"drawing": drawing, "split": split, "tile": image_output.relative_to(output_root).as_posix(), "ink_density": round(density, 6)}
            )

    classes = source_manifest["classes"]
    missing_train_classes = [name for name in classes if class_by_split["train"][name] == 0]
    if missing_train_classes:
        raise ValueError(f"Unsafe training split; missing classes: {missing_train_classes}")

    write_data_yaml(output_root, classes)
    write_training_config(output_root)
    shutil.copy2(
        source_root / "APPROVED_FOR_TRAINING_PREPARATION.json",
        output_root / "source_dataset_approval.json",
    )
    package_manifest = {
        "schema_version": 1,
        "status": "prepared_not_trained",
        "source_dataset": str(source_root),
        "source_dataset_manifest_sha256": sha256(source_root / "dataset_manifest.json"),
        "source_labels_manifest_sha256": sha256(source_root / "labels_manifest.csv"),
        "source_approval_sha256": sha256(source_root / "APPROVED_FOR_TRAINING_PREPARATION.json"),
        "approved_label_count": int(source_manifest["annotation_count"]),
        "human_box_corrections": int(source_manifest["human_box_override_count"]),
        "drawing_level_split_no_tile_leakage": True,
        "training_splits": TRAINING_SPLITS,
        "positive_tiles": dict(positive_tiles),
        "negative_tiles": dict(negative_tiles),
        "positive_objects": dict(positive_objects),
        "class_counts_by_split": {
            split: {name: class_by_split[split][name] for name in classes}
            for split in TRAINING_SPLITS
        },
        "train_contains_all_classes": not missing_train_classes,
        "negative_tile_details": negative_details,
        "limitations": [
            "Only five approved drawings are available.",
            "The test drawing is a regression reference, not a never-seen production holdout.",
            "A candidate must not replace the active model until the strict golden gate and human approval pass.",
        ],
    }
    (output_root / "training_package_manifest.json").write_text(
        json.dumps(package_manifest, indent=2), encoding="utf-8"
    )

    readme = [
        "# Detector Candidate Training Package v1",
        "",
        "Status: prepared only. No training or upload has started.",
        "",
        f"- Approved labels: {source_manifest['annotation_count']}",
        f"- Positive tiles: {sum(positive_tiles.values())}",
        f"- Negative tiles: {sum(negative_tiles.values())}",
        "- Training split includes all eight classes: YES",
        "- Drawing-level split leakage: NONE",
        "",
        "The negative tiles contain drawing content but no approved characteristics. They help reduce false detections on notes, title blocks, and drawing lines.",
        "",
        "Do not replace the production model directly after training. The candidate must first pass test-set evaluation, two fresh golden-suite runs, the strict gate, and human approval.",
    ]
    (output_root / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return package_manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--negatives-per-drawing", type=int, default=4)
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = prepare(args.source, args.output, args.negatives_per_drawing)
    print(f"Training package: {args.output}")
    print(f"Approved labels: {manifest['approved_label_count']}")
    print(f"Positive tiles: {sum(manifest['positive_tiles'].values())}")
    print(f"Negative tiles: {sum(manifest['negative_tiles'].values())}")
    print(f"Train contains all classes: {manifest['train_contains_all_classes']}")
    print("Status: prepared; training not started")


if __name__ == "__main__":
    main()
