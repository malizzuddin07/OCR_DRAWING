"""Prepare protected V8 by focusing V7 on two approved missed callouts."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(r"C:\Users\izzuddin\Desktop\OCR DRAWING")
SOURCE = ROOT / "golden_tests" / "detector_training_package_v7"
OUTPUT = ROOT / "golden_tests" / "detector_training_package_v8"
FOCUS_STEMS = (
    "W3-C111266801-01__x1920_y0000",  # approved tiny dimension 6
    "W3-C111266801-01__x0960_y1920",  # approved vertical 4H8 fit callout
)
FOCUS_REPEAT_COUNT = 3
CLASS_NAMES = (
    "dimension", "diameter", "radius", "chamfer_callout",
    "thread_callout", "hole_callout", "surface_finish", "gdt_frame",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def label_counts(path: Path) -> Counter:
    counts = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid YOLO label in {path}: {line}")
        class_id = int(fields[0])
        if not 0 <= class_id < len(CLASS_NAMES):
            raise ValueError(f"Invalid class id {class_id} in {path}")
        counts[CLASS_NAMES[class_id]] += 1
    return counts


def main() -> None:
    source_manifest_path = SOURCE / "training_package_manifest.json"
    if not source_manifest_path.is_file():
        raise FileNotFoundError(source_manifest_path)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("schema_version") != 7:
        raise ValueError("V8 must be derived from the approved V7 package")
    if source_manifest.get("approved_label_count") != 966:
        raise ValueError("V7 approved-label count changed")
    if source_manifest.get("c3010_used_for_training"):
        raise ValueError("Reserved C3010 drawing must not enter training")
    if OUTPUT.exists():
        raise FileExistsError(f"V8 package already exists: {OUTPUT}")

    shutil.copytree(SOURCE, OUTPUT)
    manifest = json.loads(
        (OUTPUT / "training_package_manifest.json").read_text(encoding="utf-8")
    )
    effective = Counter(manifest["effective_train_class_counts"])
    details = list(manifest.get("oversampling_details", []))
    focus_details = []

    for stem in FOCUS_STEMS:
        source_image = OUTPUT / "images" / "train" / f"{stem}.png"
        source_label = OUTPUT / "labels" / "train" / f"{stem}.txt"
        if not source_image.is_file() or not source_label.is_file():
            raise FileNotFoundError(f"Approved focus tile is missing: {stem}")
        counts = label_counts(source_label)
        if counts.get("dimension", 0) <= 0:
            raise ValueError(f"Focus tile has no approved dimension label: {stem}")
        for repeat in range(1, FOCUS_REPEAT_COUNT + 1):
            suffix = f"__v8focus_{repeat:02d}"
            image_destination = source_image.with_name(f"{stem}{suffix}.png")
            label_destination = source_label.with_name(f"{stem}{suffix}.txt")
            shutil.copy2(source_image, image_destination)
            shutil.copy2(source_label, label_destination)
            effective.update(counts)
            item = {
                "purpose": "approved_v8_missed_callout_focus",
                "source_drawing": "W3-C111266801-01",
                "source_image": source_image.name,
                "repeated_image": image_destination.name,
                "repeat": repeat,
                "object_counts": dict(counts),
            }
            details.append(item)
            focus_details.append(item)

    manifest.update(
        {
            "schema_version": 8,
            "status": "prepared_not_trained",
            "candidate_name": "golden_detector_v8",
            "starting_model": "candidate_detector_v7_best.pt",
            "starting_model_is_production": False,
            "production_model_will_change": False,
            "strategy": "candidate_v7_plus_two_approved_focus_tiles_with_v7_rehearsal",
            "effective_train_class_counts": dict(effective),
            "oversampled_training_tile_count": int(
                manifest.get("oversampled_training_tile_count", 0)
            ) + len(focus_details),
            "oversampling_details": details,
            "v8_focus_tile_stems": list(FOCUS_STEMS),
            "v8_focus_tile_count": len(FOCUS_STEMS),
            "v8_focus_repeat_count_per_tile": FOCUS_REPEAT_COUNT,
            "v8_focus_repeat_tile_count": len(focus_details),
            "v8_focus_targets": ["dimension 6", "4H8 +0.018/0 DEPTH 5"],
            "source_v7_manifest_sha256": sha256(source_manifest_path),
            "test_drawings_reserved_from_candidate_v8_training": True,
            "c3010_used_for_training": False,
            "required_gate": (
                "V8 must recover the two approved focus callouts, introduce no "
                "reserved-drawing regression or false extra, pass all five OCR "
                "golden drawings, and repeat identically before activation."
            ),
        }
    )
    (OUTPUT / "training_package_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "training_config.yaml").write_text(
        """# Candidate V8: conservative V7 focus fine-tuning.
model: candidate_detector_v7_best.pt
data: runtime_data.yaml
epochs: 40
imgsz: 1280
batch: 4
device: 0
patience: 12
optimizer: AdamW
lr0: 0.000005
lrf: 0.1
weight_decay: 0.001
freeze: 10
box: 12.0
seed: 42
deterministic: true
workers: 2
cache: false
save_period: 10
project: runs/candidate_detector
name: golden_detector_v8
fliplr: 0.0
flipud: 0.0
mosaic: 0.0
mixup: 0.0
erasing: 0.0
hsv_h: 0.0
hsv_s: 0.0
hsv_v: 0.02
""",
        encoding="utf-8",
    )
    (OUTPUT / "README.md").write_text(
        "# Detector Candidate Training Package V8\n\n"
        "Protected V7 fine-tuning with three extra copies of each of two "
        "human-approved hard tiles. Reserved validation/test drawings remain "
        "unchanged. Production is not modified.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "approved_labels": manifest["approved_label_count"],
        "focus_tiles": len(FOCUS_STEMS),
        "focus_repeats": len(focus_details),
        "starting_model": manifest["starting_model"],
        "production_model_will_change": False,
    }, indent=2))


if __name__ == "__main__":
    main()
