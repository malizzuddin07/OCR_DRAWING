"""Create detector_dataset_v6 from the approved v5 dataset.

Only the corrections explicitly confirmed during the reserved V4 review are
applied. The source dataset is never modified.
"""

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
SOURCE = ROOT / "golden_tests" / "detector_dataset_v5"
OUTPUT = ROOT / "golden_tests" / "detector_dataset_v6"
ORIGINAL = (
    ROOT
    / "golden_tests"
    / "UNUSED_BATCH_1_20260727"
    / "raw_batch"
    / "W3-C111266101-01"
    / "original.png"
)

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
CLASS_COLORS = {
    "dimension": (20, 120, 255),
    "diameter": (255, 100, 20),
    "radius": (80, 180, 80),
    "chamfer_callout": (180, 80, 180),
    "thread_callout": (40, 180, 220),
    "hole_callout": (220, 140, 40),
    "surface_finish": (220, 80, 120),
    "gdt_frame": (40, 40, 220),
}
TARGET_DRAWING = "W3-C111266101-01"
TARGET_BALLOON = "A20"
OLD_BOX = (2825.0, 1265.0, 230.0, 275.0)
NEW_BOX = (2833.0, 1265.0, 169.0, 275.0)
TILE_PATTERN = re.compile(r"__x(\d+)_y(\d+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_v5_approval() -> dict:
    approval = load_json(SOURCE / "APPROVED_FOR_TRAINING_PREPARATION.json")
    expected = {
        "dataset_manifest_sha256": sha256(SOURCE / "dataset_manifest.json"),
        "labels_manifest_sha256": sha256(SOURCE / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(SOURCE / "data.yaml"),
    }
    if approval.get("approved_label_count") != 965:
        raise ValueError("The source dataset does not contain 965 approved labels")
    for field, actual in expected.items():
        if approval.get(field) != actual:
            raise ValueError(f"Source approval hash mismatch: {field}")
    return approval


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if reader.fieldnames is None:
            raise ValueError("labels_manifest.csv has no header")
        return rows, reader.fieldnames


def write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tile_origin(tile_value: str) -> tuple[int, int]:
    match = TILE_PATTERN.search(Path(tile_value).stem)
    if not match:
        raise ValueError(f"Cannot read tile origin: {tile_value}")
    return int(match.group(1)), int(match.group(2))


def regenerate_target_tile(rows: list[dict]) -> None:
    target_rows = [
        row
        for row in rows
        if row["Tile"].replace("\\", "/")
        == "images/test/W3-C111266101-01__x1920_y0960.png"
    ]
    if not target_rows:
        raise ValueError("Target tile has no manifest rows")
    image_path = OUTPUT / target_rows[0]["Tile"]
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    image_height, image_width = image.shape[:2]
    origin_x, origin_y = tile_origin(target_rows[0]["Tile"])
    lines = []
    for row in sorted(target_rows, key=lambda item: (float(item["Y"]), float(item["X"]))):
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
    label_path = (
        OUTPUT
        / "labels"
        / "test"
        / "W3-C111266101-01__x1920_y0960.txt"
    )
    label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def regenerate_preview(rows: list[dict]) -> None:
    image = cv2.imread(str(ORIGINAL))
    if image is None:
        raise FileNotFoundError(ORIGINAL)
    thickness = max(2, round(max(image.shape[:2]) / 2200))
    drawing_rows = [row for row in rows if row["Drawing"] == TARGET_DRAWING]
    for row in drawing_rows:
        x = round(float(row["X"]))
        y = round(float(row["Y"]))
        width = round(float(row["Width"]))
        height = round(float(row["Height"]))
        cv2.rectangle(
            image,
            (x, y),
            (x + width, y + height),
            CLASS_COLORS[row["Class"]],
            thickness,
        )
    preview_path = OUTPUT / "previews" / f"{TARGET_DRAWING}_labels.png"
    if not cv2.imwrite(str(preview_path), image):
        raise OSError(f"Could not write {preview_path}")


def parse_yolo(path: Path) -> Counter:
    counts = Counter()
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if not parts:
            continue
        if len(parts) != 5:
            raise ValueError(f"Malformed YOLO line in {path}: {raw}")
        class_id = int(parts[0])
        values = [float(value) for value in parts[1:]]
        if class_id not in range(len(CLASS_NAMES)) or not all(
            0.0 <= value <= 1.0 for value in values
        ):
            raise ValueError(f"Invalid YOLO line in {path}: {raw}")
        counts[CLASS_NAMES[class_id]] += 1
    return counts


def validate_dataset(rows: list[dict]) -> dict:
    if len(rows) != 965:
        raise ValueError(f"Expected 965 rows, found {len(rows)}")
    class_counts = Counter(row["Class"] for row in rows)
    split_counts = Counter(row["Split"] for row in rows)
    drawing_counts = Counter(row["Drawing"] for row in rows)
    if set(class_counts) != set(CLASS_NAMES):
        raise ValueError("Not all eight detector classes are present")
    if len(drawing_counts) != 17:
        raise ValueError(f"Expected 17 drawings, found {len(drawing_counts)}")

    manifest_by_tile: dict[str, Counter] = {}
    for row in rows:
        tile = row["Tile"].replace("\\", "/")
        manifest_by_tile.setdefault(tile, Counter())[row["Class"]] += 1
    for tile, expected in manifest_by_tile.items():
        split = tile.split("/")[1]
        label_path = OUTPUT / "labels" / split / f"{Path(tile).stem}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(label_path)
        actual = parse_yolo(label_path)
        if actual != expected:
            raise ValueError(f"Manifest/YOLO mismatch: {tile}: {expected} != {actual}")

    return {
        "annotation_count": len(rows),
        "drawing_count": len(drawing_counts),
        "class_counts": dict(sorted(class_counts.items())),
        "split_annotation_counts": dict(sorted(split_counts.items())),
        "all_eight_classes_present": True,
        "manifest_yolo_pairs_validated": len(manifest_by_tile),
    }


def main() -> None:
    source_approval = validate_v5_approval()
    if OUTPUT.exists():
        raise FileExistsError(
            f"{OUTPUT} already exists; remove it only after checking why this script ran twice"
        )
    shutil.copytree(SOURCE, OUTPUT)

    rows, fields = read_rows(OUTPUT / "labels_manifest.csv")
    matches = [
        row
        for row in rows
        if row["Drawing"] == TARGET_DRAWING and row["Balloons"] == TARGET_BALLOON
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one A20 row, found {len(matches)}")
    target = matches[0]
    current = tuple(float(target[field]) for field in ("X", "Y", "Width", "Height"))
    if current != OLD_BOX:
        raise ValueError(f"A20 source box changed: expected {OLD_BOX}, found {current}")
    for field, value in zip(("X", "Y", "Width", "Height"), NEW_BOX):
        target[field] = f"{value:.1f}"
    target["Source"] = "reserved_v4_human_confirmed_tightened"
    write_rows(OUTPUT / "labels_manifest.csv", rows, fields)
    regenerate_target_tile(rows)
    regenerate_preview(rows)

    manifest_path = OUTPUT / "dataset_manifest.json"
    manifest = load_json(manifest_path)
    manifest.update(
        {
            "status": "human_approved_17_drawing_dataset_v6",
            "purpose": "Preserve dataset v5 and apply the final human-confirmed V4 reserved-map corrections",
            "base_dataset": str(SOURCE),
            "base_dataset_manifest_sha256": sha256(SOURCE / "dataset_manifest.json"),
            "correction_count": 1,
            "corrections": [
                {
                    "drawing": TARGET_DRAWING,
                    "annotation": TARGET_BALLOON,
                    "class": "surface_finish",
                    "old_box": list(OLD_BOX),
                    "new_box": list(NEW_BOX),
                    "reason": "MISSING 36 / A20 was confirmed correct but its approved box was too wide; tighten around the complete surface-finish callout",
                    "human_confirmation": "All other V4 reserved issue maps confirmed",
                },
                {
                    "drawing": "C3010-035-250F",
                    "annotation": "BOX 1",
                    "change": "none",
                    "reason": "The existing inner approved orange box remains correct; the larger V4 prediction is rejected",
                },
            ],
            "required_next_step": "Build and train isolated candidate V5 from production candidate V3; do not modify production",
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    validation = validate_dataset(rows)
    correction_record = {
        "schema_version": 1,
        "date": str(date.today()),
        "status": "confirmed_corrections_applied",
        "source_dataset": str(SOURCE),
        "output_dataset": str(OUTPUT),
        "user_confirmation": "All corrections complete; all other V4 reserved issue maps confirmed",
        "corrections": manifest["corrections"],
        "validation": validation,
        "production_model_changed": False,
    }
    (OUTPUT / "CONFIRMED_V4_RESERVED_CORRECTIONS.json").write_text(
        json.dumps(correction_record, indent=2) + "\n", encoding="utf-8"
    )

    approval = {
        "schema_version": 1,
        "status": "human_approved_for_candidate_training_preparation",
        "approval_date": str(date.today()),
        "approval_basis": "Dataset v5 was approved, the two V4 reserved-map corrections were resolved, and the user confirmed every other issue-map item.",
        "approved_drawing_count": validation["drawing_count"],
        "approved_label_count": validation["annotation_count"],
        "base_approved_label_count": source_approval["approved_label_count"],
        "geometry_correction_count": 1,
        "dataset_manifest_sha256": sha256(manifest_path),
        "labels_manifest_sha256": sha256(OUTPUT / "labels_manifest.csv"),
        "data_yaml_sha256": sha256(OUTPUT / "data.yaml"),
        "preview_count": len(list((OUTPUT / "previews").glob("*_labels.png"))),
        "drawing_level_split_no_tile_leakage": True,
        "all_eight_classes_present": True,
        "training_allowed": False,
        "production_model_change_authorized": False,
        "next_required_step": "Prepare isolated candidate-v5 training package starting from candidate V3.",
    }
    (OUTPUT / "APPROVED_FOR_TRAINING_PREPARATION.json").write_text(
        json.dumps(approval, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
