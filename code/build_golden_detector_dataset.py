"""Build a reviewable YOLO detector dataset from approved golden drawings.

The approved characteristic coordinates are immutable OCR/parsing truth. Human
reviewed EXTRA detections may be added as detector-only positives without
rewriting the approved Excel values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = PROJECT_ROOT / "golden_tests"
DEFAULT_BASELINE = GOLDEN_ROOT / "runs" / "local_baseline_20260722_081233" / "run_1"
DEFAULT_REVIEW = (
    GOLDEN_ROOT
    / "comparison_reports"
    / "local_baseline_20260722_081233"
    / "missed_characteristics_analysis"
    / "human_detection_review.json"
)
DEFAULT_OUTPUT = GOLDEN_ROOT / "detector_dataset_v3"

# Keep these names aligned with the user's Roboflow object-detection project.
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

DRAWING_SPLITS = {
    "train": ["W3-C111262801-2A", "W3-C111265901-03", "W3-C111266801-01"],
    "val": ["W3-C171246401-00"],
    "test": ["C3010-035-250F"],
}

TYPE_PRIORITY = (
    ("gdt", "gdt_frame"),
    ("surface_finish", "surface_finish"),
    ("metric_thread", "thread_callout"),
    ("hole_callout", "hole_callout"),
    ("diameter", "diameter"),
    ("radius", "radius"),
    ("chamfer", "chamfer_callout"),
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def characteristic_rows(payload, drawing="unknown"):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("characteristics", payload.get("records", []))
    raise ValueError(f"{drawing}: unsupported characteristics payload type")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def clean(value) -> str:
    return " ".join(str(value or "").split())


def row_box(row):
    try:
        box = tuple(float(row[key]) for key in ("X", "Y", "Width", "Height"))
    except (KeyError, TypeError, ValueError):
        return None
    if box[2] <= 0 or box[3] <= 0:
        return None
    return box


def group_rows_by_box(rows):
    grouped = {}
    invalid = []
    for row in rows:
        box = row_box(row)
        if box is None:
            invalid.append(row)
            continue
        key = tuple(round(value, 2) for value in box)
        grouped.setdefault(key, []).append(row)
    return [{"box": key, "rows": values} for key, values in grouped.items()], invalid


def detector_class(rows) -> str:
    measurement_types = {clean(row.get("Measurement Type")).lower() for row in rows}
    for measurement_type, class_name in TYPE_PRIORITY:
        if measurement_type in measurement_types:
            return class_name
    return "dimension"


def group_balloons(rows) -> str:
    return ", ".join(clean(row.get("Balloon No")) for row in rows)


def apply_box_overrides(drawing, groups, review):
    overrides = review["drawings"][drawing].get("box_overrides", [])
    applied = 0
    for override in overrides:
        expected_balloon = clean(override.get("expected_balloon"))
        matches = [group for group in groups if group_balloons(group["rows"]) == expected_balloon]
        if len(matches) != 1:
            raise ValueError(
                f"{drawing}: box override for expected balloon {expected_balloon!r} matched {len(matches)} groups"
            )
        group = matches[0]
        group["original_box"] = group["box"]
        group["box"] = tuple(float(override[key]) for key in ("X", "Y", "Width", "Height"))
        group["source"] = "human_box_override"
        group["override_reason"] = clean(override.get("required_text"))
        applied += 1
    return applied


def tile_starts(length: int, tile_size: int, overlap: int):
    if length <= tile_size:
        return [0]
    stride = tile_size - overlap
    starts = list(range(0, max(1, length - tile_size + 1), stride))
    final_start = length - tile_size
    if starts[-1] != final_start:
        starts.append(final_start)
    return starts


def choose_tile(box, tiles, margin=8):
    x, y, width, height = box
    center_x, center_y = x + width / 2, y + height / 2
    candidates = []
    for tile in tiles:
        tx, ty, tw, th = tile
        if x < tx + margin or y < ty + margin:
            continue
        if x + width > tx + tw - margin or y + height > ty + th - margin:
            continue
        edge_distance = min(x - tx, y - ty, tx + tw - (x + width), ty + th - (y + height))
        center_distance = abs(center_x - (tx + tw / 2)) + abs(center_y - (ty + th / 2))
        candidates.append((edge_distance, -center_distance, tile))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def normalized_yolo(box, tile):
    x, y, width, height = box
    tx, ty, tw, th = tile
    center_x = (x - tx + width / 2) / tw
    center_y = (y - ty + height / 2) / th
    return center_x, center_y, width / tw, height / th


def accepted_extra_groups(drawing, review, baseline_root):
    decisions = review["drawings"][drawing]["accept_current_detection"]
    accepted = {
        clean(item.get("current_balloon"))
        for item in decisions
        if item.get("generated_issue") == "EXTRA"
    }
    if not accepted:
        return []
    current_path = baseline_root / drawing / "characteristics.json"
    payload = load_json(current_path)
    rows = characteristic_rows(payload, drawing)
    groups, invalid = group_rows_by_box(rows)
    if invalid:
        raise ValueError(f"{drawing}: current characteristics contain invalid boxes")
    selected = [group for group in groups if group_balloons(group["rows"]) in accepted]
    found = {group_balloons(group["rows"]) for group in selected}
    missing = sorted(accepted - found)
    if missing:
        raise ValueError(f"{drawing}: reviewed EXTRA balloons not found: {missing}")
    for group in selected:
        group["source"] = "human_accepted_extra"
    return selected


def load_annotations(drawing, review, baseline_root):
    expected_path = GOLDEN_ROOT / "expected_characteristics" / f"{drawing}_expected.json"
    payload = load_json(expected_path)
    groups, invalid = group_rows_by_box(payload["records"])
    if invalid:
        raise ValueError(f"{drawing}: {len(invalid)} approved records have invalid boxes")
    for group in groups:
        group["source"] = "approved_expected"
    override_count = apply_box_overrides(drawing, groups, review)
    groups.extend(accepted_extra_groups(drawing, review, baseline_root))

    # Human-accepted extras must not duplicate an approved box.
    seen = set()
    unique = []
    for group in groups:
        key = tuple(round(value, 2) for value in group["box"])
        if key in seen:
            if group["source"] == "human_accepted_extra":
                continue
            raise ValueError(f"{drawing}: duplicate approved physical box {key}")
        seen.add(key)
        group["class_name"] = detector_class(group["rows"])
        unique.append(group)
    return unique, expected_path, override_count


def draw_preview(image, annotations, output_path):
    colors = {
        name: tuple(int(value) for value in color)
        for name, color in zip(
            CLASS_NAMES,
            [(20, 120, 255), (255, 100, 20), (80, 180, 80), (180, 80, 180),
             (40, 180, 220), (220, 140, 40), (220, 80, 120), (40, 40, 220)],
        )
    }
    preview = image.copy()
    for item in annotations:
        x, y, width, height = (round(value) for value in item["box"])
        color = colors[item["class_name"]]
        cv2.rectangle(preview, (x, y), (x + width, y + height), color, 3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), preview):
        raise OSError(f"Could not write preview {output_path}")


def build_dataset(output_root, baseline_root, review_path, tile_size=1280, overlap=320):
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output folder is not empty: {output_root}")
    if overlap < 0 or overlap >= tile_size:
        raise ValueError("Overlap must be at least 0 and smaller than tile size")

    review = load_json(review_path)
    class_ids = {name: index for index, name in enumerate(CLASS_NAMES)}
    records = []
    drawing_summaries = []
    total_annotations = 0
    split_lookup = {drawing: split for split, drawings in DRAWING_SPLITS.items() for drawing in drawings}

    for drawing in sorted(split_lookup):
        split = split_lookup[drawing]
        image_path = baseline_root / drawing / "original.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read source image: {image_path}")
        height, width = image.shape[:2]
        annotations, expected_path, override_count = load_annotations(drawing, review, baseline_root)
        for item in annotations:
            x, y, box_width, box_height = item["box"]
            if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
                raise ValueError(f"{drawing}: out-of-bounds box {item['box']}")

        tiles = [
            (x, y, min(tile_size, width), min(tile_size, height))
            for y in tile_starts(height, tile_size, overlap)
            for x in tile_starts(width, tile_size, overlap)
        ]
        assignments = {tile: [] for tile in tiles}
        for item in annotations:
            tile = choose_tile(item["box"], tiles)
            if tile is None:
                raise ValueError(f"{drawing}: no safe tile contains box {item['box']}")
            assignments[tile].append(item)

        used_tiles = 0
        class_counts = Counter()
        for tile, tile_annotations in assignments.items():
            if not tile_annotations:
                continue
            tx, ty, tw, th = tile
            stem = f"{drawing}__x{tx:04d}_y{ty:04d}"
            image_output = output_root / "images" / split / f"{stem}.png"
            label_output = output_root / "labels" / split / f"{stem}.txt"
            image_output.parent.mkdir(parents=True, exist_ok=True)
            label_output.parent.mkdir(parents=True, exist_ok=True)
            crop = image[ty : ty + th, tx : tx + tw]
            if not cv2.imwrite(str(image_output), crop):
                raise OSError(f"Could not write tile {image_output}")

            label_lines = []
            for item in sorted(tile_annotations, key=lambda value: (value["box"][1], value["box"][0])):
                normalized = normalized_yolo(item["box"], tile)
                if not all(0 < value <= 1 for value in normalized):
                    raise ValueError(f"{drawing}: invalid normalized label {normalized}")
                class_id = class_ids[item["class_name"]]
                label_lines.append(f"{class_id} " + " ".join(f"{value:.8f}" for value in normalized))
                class_counts[item["class_name"]] += 1
                records.append(
                    {
                        "Drawing": drawing,
                        "Split": split,
                        "Tile": image_output.relative_to(output_root).as_posix(),
                        "Class": item["class_name"],
                        "Source": item["source"],
                        "Balloons": group_balloons(item["rows"]),
                        "X": item["box"][0],
                        "Y": item["box"][1],
                        "Width": item["box"][2],
                        "Height": item["box"][3],
                    }
                )
            label_output.write_text("\n".join(label_lines) + "\n", encoding="utf-8")
            used_tiles += 1

        draw_preview(image, annotations, output_root / "previews" / f"{drawing}_labels.png")
        total_annotations += len(annotations)
        drawing_summaries.append(
            {
                "drawing": drawing,
                "split": split,
                "source_image": str(image_path),
                "source_image_sha256": sha256(image_path),
                "expected_characteristics": str(expected_path),
                "physical_callouts": len(annotations),
                "approved_callouts": sum(
                    item["source"] in {"approved_expected", "human_box_override"} for item in annotations
                ),
                "human_accepted_extras": sum(item["source"] == "human_accepted_extra" for item in annotations),
                "human_box_overrides": override_count,
                "tiles": used_tiles,
                "class_counts": dict(sorted(class_counts.items())),
            }
        )

    output_root.mkdir(parents=True, exist_ok=True)
    yaml_lines = ["path: .", "train: images/train", "val: images/val", "test: images/test", "names:"]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    (output_root / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    with (output_root / "labels_manifest.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    class_totals = Counter(record["Class"] for record in records)
    split_totals = Counter(record["Split"] for record in records)
    manifest = {
        "schema_version": 1,
        "status": "ready_for_visual_label_QC_not_training",
        "purpose": "Candidate detector dataset built from five human-approved golden drawings",
        "warning": "Five drawings are not enough to claim production accuracy. Keep a new drawing sealed as an independent holdout before deployment.",
        "tile_size": tile_size,
        "tile_overlap": overlap,
        "classes": CLASS_NAMES,
        "drawing_splits": DRAWING_SPLITS,
        "drawing_level_split_no_tile_leakage": True,
        "annotation_count": total_annotations,
        "class_counts": dict(sorted(class_totals.items())),
        "split_annotation_counts": dict(sorted(split_totals.items())),
        "human_accepted_extra_count": sum(record["Source"] == "human_accepted_extra" for record in records),
        "human_box_override_count": sum(item["human_box_overrides"] for item in drawing_summaries),
        "human_review_file": str(review_path),
        "human_review_sha256": sha256(review_path),
        "drawings": drawing_summaries,
    }
    (output_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report_lines = [
        "# Golden Detector Dataset v3",
        "",
        "Status: ready for visual label QC; not approved for training yet.",
        "",
        f"- Drawings: {len(drawing_summaries)}",
        f"- Physical callout labels: {total_annotations}",
        f"- Human-accepted extra labels: {manifest['human_accepted_extra_count']}",
        f"- Human-reviewed box corrections: {manifest['human_box_override_count']}",
        f"- Tile size: {tile_size} px with {overlap} px overlap",
        "- Split rule: entire drawings stay in one split",
        "",
        "## Class counts",
        "",
    ]
    report_lines.extend(f"- {name}: {class_totals.get(name, 0)}" for name in CLASS_NAMES)
    report_lines.extend(
        [
            "",
            "## Required next check",
            "",
            "Open the five images in previews/. Confirm every box covers one complete required callout and no Japanese-only note or drawing line is labelled.",
            "",
            "Do not train or promote a model until this visual check is approved and a separate unseen holdout drawing is prepared.",
        ]
    )
    (output_root / "QUALITY_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline-root", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--tile-size", type=int, default=1280)
    parser.add_argument("--overlap", type=int, default=320)
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = build_dataset(args.output, args.baseline_root, args.review, args.tile_size, args.overlap)
    print(f"Dataset: {args.output}")
    print(f"Drawings: {len(manifest['drawings'])}")
    print(f"Labels: {manifest['annotation_count']}")
    print(f"Human-accepted extras: {manifest['human_accepted_extra_count']}")
    print(f"Human box corrections: {manifest['human_box_override_count']}")
    print("Status: visual label QC required before training")


if __name__ == "__main__":
    main()
