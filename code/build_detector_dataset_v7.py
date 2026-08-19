"""Build detector dataset v7 by adding the approved missing vertical 10 label."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import cv2


ROOT = Path(r"C:\Users\izzuddin\Desktop\OCR DRAWING")
SOURCE = ROOT / "golden_tests" / "detector_dataset_v6"
OUTPUT = ROOT / "golden_tests" / "detector_dataset_v7"
REVIEW = (
    ROOT
    / "golden_tests"
    / "HARD_EXAMPLE_REVIEW_W3_C111266801_20260731_V2"
)
DRAWING = "W3-C111266801-01"
TILE = "images/train/W3-C111266801-01__x2880_y1920.png"
NEW_LABEL = {
    "Drawing": DRAWING,
    "Split": "train",
    "Tile": TILE,
    "Class": "dimension",
    "Source": "hard_example_human_approved_20260731",
    "Balloons": "58",
    "X": "3452.0",
    "Y": "2110.0",
    "Width": "42.0",
    "Height": "70.0",
}
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
TILE_PATTERN = re.compile(r"__x(\d+)_y(\d+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if reader.fieldnames is None:
            raise ValueError("labels_manifest.csv has no header")
        return rows, reader.fieldnames


def write_rows(path: Path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_source():
    approval = load_json(SOURCE / "APPROVED_FOR_TRAINING_PREPARATION.json")
    if approval.get("approved_label_count") != 965:
        raise ValueError("Dataset v6 does not contain 965 approved labels")
    for field, filename in (
        ("dataset_manifest_sha256", "dataset_manifest.json"),
        ("labels_manifest_sha256", "labels_manifest.csv"),
        ("data_yaml_sha256", "data.yaml"),
    ):
        if approval.get(field) != sha256(SOURCE / filename):
            raise ValueError(f"Dataset v6 approval hash mismatch: {field}")
    review = load_json(REVIEW / "review_manifest.json")
    if review.get("hard_label_count") != 21:
        raise ValueError("The approved V2 review must contain 21 hard labels")
    label = review.get("supplemental_label", {})
    if (
        label.get("balloons") != "58"
        or label.get("expected_value") != "10"
        or label.get("box") != [3452.0, 2110.0, 42.0, 70.0]
    ):
        raise ValueError("The supplemental label does not match the reviewed box")
    return approval, review


def tile_origin(tile: str):
    match = TILE_PATTERN.search(Path(tile).stem)
    if not match:
        raise ValueError(f"Cannot parse tile origin: {tile}")
    return int(match.group(1)), int(match.group(2))


def regenerate_tile(rows):
    tile_rows = [row for row in rows if row["Tile"].replace("\\", "/") == TILE]
    image_path = OUTPUT / TILE
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    image_height, image_width = image.shape[:2]
    origin_x, origin_y = tile_origin(TILE)
    lines = []
    for row in sorted(tile_rows, key=lambda item: (float(item["Y"]), float(item["X"]))):
        class_id = CLASS_NAMES.index(row["Class"])
        x = float(row["X"]) - origin_x
        y = float(row["Y"]) - origin_y
        width = float(row["Width"])
        height = float(row["Height"])
        if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
            raise ValueError(f"Box outside target tile: {row}")
        lines.append(
            f"{class_id} "
            f"{(x + width / 2) / image_width:.8f} "
            f"{(y + height / 2) / image_height:.8f} "
            f"{width / image_width:.8f} "
            f"{height / image_height:.8f}"
        )
    label_path = OUTPUT / "labels" / "train" / f"{Path(TILE).stem}.txt"
    label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_yolo(path: Path):
    counts = Counter()
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if not parts:
            continue
        if len(parts) != 5:
            raise ValueError(f"Malformed YOLO row in {path}: {raw}")
        class_id = int(parts[0])
        values = [float(value) for value in parts[1:]]
        if class_id not in range(len(CLASS_NAMES)):
            raise ValueError(f"Invalid class ID in {path}: {class_id}")
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"Invalid normalized coordinates in {path}: {raw}")
        counts[CLASS_NAMES[class_id]] += 1
    return counts


def validate_dataset(rows):
    if len(rows) != 966:
        raise ValueError(f"Expected 966 rows, found {len(rows)}")
    class_counts = Counter(row["Class"] for row in rows)
    split_counts = Counter(row["Split"] for row in rows)
    drawings = {row["Drawing"] for row in rows}
    if len(drawings) != 17 or set(class_counts) != set(CLASS_NAMES):
        raise ValueError("Dataset drawing/class coverage changed unexpectedly")
    rows_by_tile = {}
    for row in rows:
        tile = row["Tile"].replace("\\", "/")
        rows_by_tile.setdefault(tile, Counter())[row["Class"]] += 1
    for tile, expected in rows_by_tile.items():
        split = tile.split("/")[1]
        label = OUTPUT / "labels" / split / f"{Path(tile).stem}.txt"
        if parse_yolo(label) != expected:
            raise ValueError(f"Manifest/YOLO mismatch: {tile}")
    return {
        "annotation_count": len(rows),
        "drawing_count": len(drawings),
        "class_counts": dict(sorted(class_counts.items())),
        "split_annotation_counts": dict(sorted(split_counts.items())),
        "manifest_yolo_pairs_validated": len(rows_by_tile),
        "all_eight_classes_present": True,
    }


def main():
    source_approval, review = validate_source()
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    shutil.copytree(SOURCE, OUTPUT)

    rows, fields = read_rows(OUTPUT / "labels_manifest.csv")
    if any(
        row["Drawing"] == DRAWING and row["Balloons"] == NEW_LABEL["Balloons"]
        for row in rows
    ):
        raise ValueError("Balloon 58 already exists")
    rows.append(NEW_LABEL.copy())
    write_rows(OUTPUT / "labels_manifest.csv", rows, fields)
    regenerate_tile(rows)
    shutil.copy2(
        REVIEW / f"{DRAWING}_all_approved_labels.png",
        OUTPUT / "previews" / f"{DRAWING}_labels.png",
    )

    validation = validate_dataset(rows)
    manifest_path = OUTPUT / "dataset_manifest.json"
    manifest = load_json(manifest_path)
    manifest.update(
        {
            "status": "human_approved_17_drawing_dataset_v7",
            "purpose": (
                "Preserve dataset v6 and add the human-confirmed missing vertical "
                "dimension 10 from W3-C111266801-01"
            ),
            "base_dataset": str(SOURCE),
            "base_dataset_manifest_sha256": sha256(SOURCE / "dataset_manifest.json"),
            **validation,
            "hard_example_review": str(REVIEW),
            "hard_example_count": 21,
            "new_annotation_count": 1,
            "new_annotation": NEW_LABEL,
            "required_next_step": (
                "Prepare an isolated candidate V6 hard-example fine-tuning package "
                "starting from candidate V3; do not modify production"
            ),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    approval_record = {
        "schema_version": 1,
        "approval_date": str(date.today()),
        "status": "human_approved_hard_examples",
        "drawing": DRAWING,
        "user_confirmation": (
            "The 57 existing boxes are approved and the added vertical 10 box is approved"
        ),
        "approved_preview_label_count": 58,
        "hard_example_count": 21,
        "new_annotation_count": 1,
        "new_annotation": NEW_LABEL,
        "review_manifest_sha256": sha256(REVIEW / "review_manifest.json"),
        "labels_sha256": sha256(REVIEW / f"{DRAWING}_hard_labels.json"),
        "preview_sha256": sha256(
            REVIEW / f"{DRAWING}_all_approved_labels.png"
        ),
        "production_model_changed": False,
    }
    (OUTPUT / "W3_C111266801_HARD_EXAMPLES_APPROVED.json").write_text(
        json.dumps(approval_record, indent=2) + "\n", encoding="utf-8"
    )
    (REVIEW / "APPROVED.json").write_text(
        json.dumps(approval_record, indent=2) + "\n", encoding="utf-8"
    )

    approval = {
        "schema_version": 1,
        "status": "human_approved_for_candidate_training_preparation",
        "approval_date": str(date.today()),
        "approval_basis": (
            "Dataset v6 remains approved; the user approved all 58 boxes for "
            "W3-C111266801-01, including the new vertical dimension 10."
        ),
        "approved_drawing_count": 17,
        "approved_label_count": 966,
        "base_approved_label_count": source_approval["approved_label_count"],
        "new_annotation_count": 1,
        "hard_example_count": 21,
        "dataset_manifest_sha256": sha256(manifest_path),
        "labels_manifest_sha256": sha256(OUTPUT / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(OUTPUT / "data.yaml"),
        "preview_count": len(list((OUTPUT / "previews").glob("*_labels.png"))),
        "drawing_level_split_no_tile_leakage": True,
        "all_eight_classes_present": True,
        "training_allowed": False,
        "production_model_change_authorized": False,
        "next_required_step": (
            "Prepare isolated candidate-v6 hard-example training package from V3."
        ),
    }
    (OUTPUT / "APPROVED_FOR_TRAINING_PREPARATION.json").write_text(
        json.dumps(approval, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
