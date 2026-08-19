"""Build detector dataset v4 from the locked v3 dataset plus six approvals.

This script verifies every Stage 2 approval hash, keeps drawings in one split,
and produces review previews. It never starts training or changes production.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import cv2


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

NEW_DRAWING_SPLITS = {
    "FAB-C-3060-010-9100 W3-C100807301-00": "train",
    "W3-C111260501-01": "train",
    "W3-C111262601-02": "train",
    "W3-C081779801-00": "val",
    "W3-C111260901-0B": "val",
    "W3-C111262701-01": "test",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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
        edge_distance = min(
            x - tx,
            y - ty,
            tx + tw - (x + width),
            ty + th - (y + height),
        )
        center_distance = abs(center_x - (tx + tw / 2)) + abs(center_y - (ty + th / 2))
        candidates.append((edge_distance, -center_distance, tile))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def containing_tile(box, image_width, image_height, tile_size, margin=8):
    """Create a clamped tile that fully contains a box near a grid boundary."""
    x, y, width, height = box
    tile_width = min(tile_size, image_width)
    tile_height = min(tile_size, image_height)
    if width + 2 * margin > tile_width or height + 2 * margin > tile_height:
        return None
    center_x = x + width / 2
    center_y = y + height / 2
    tx = int(round(center_x - tile_width / 2))
    ty = int(round(center_y - tile_height / 2))
    tx = max(0, min(tx, image_width - tile_width))
    ty = max(0, min(ty, image_height - tile_height))
    tile = (tx, ty, tile_width, tile_height)
    return tile if choose_tile(box, [tile], margin=margin) is not None else None


def normalized_yolo(box, tile):
    x, y, width, height = box
    tx, ty, tw, th = tile
    return (
        (x - tx + width / 2) / tw,
        (y - ty + height / 2) / th,
        width / tw,
        height / th,
    )


def verify_approval(approval_path: Path, review_root: Path):
    approval = load_json(approval_path)
    drawing = approval["drawing"]
    labels_path = review_root / approval["approved_labels"]
    plan_path = review_root / approval["approved_plan"]
    preview_path = review_root / approval["approved_preview"]
    paths = {"labels": labels_path, "plan": plan_path, "preview": preview_path}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{drawing}: approved {name} is missing: {path}")
        expected_hash = approval["sha256"][name]
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"{drawing}: approved {name} hash changed; "
                f"expected {expected_hash}, got {actual_hash}"
            )
    payload = load_json(labels_path)
    labels = payload.get("labels", [])
    if payload.get("drawing") != drawing:
        raise ValueError(f"{drawing}: labels payload belongs to {payload.get('drawing')}")
    if len(labels) != int(approval["approved_label_count"]):
        raise ValueError(
            f"{drawing}: approved count is {approval['approved_label_count']}, "
            f"but labels file contains {len(labels)}"
        )
    return approval, labels, paths


def overlap_ratio(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    width = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    height = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    overlap = width * height
    if overlap <= 0:
        return 0.0
    return overlap / min(aw * ah, bw * bh)


def validate_labels(drawing, labels, image_width, image_height):
    seen_ids = set()
    boxes = []
    for label in labels:
        label_id = str(label["label_id"])
        if label_id in seen_ids:
            raise ValueError(f"{drawing}: duplicate label ID {label_id}")
        seen_ids.add(label_id)
        class_name = label["class_name"]
        if class_name not in CLASS_NAMES:
            raise ValueError(f"{drawing}: unknown class {class_name}")
        box = tuple(float(value) for value in label["box"])
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            raise ValueError(f"{drawing}: invalid box for {label_id}: {box}")
        if box[0] < 0 or box[1] < 0 or box[0] + box[2] > image_width or box[1] + box[3] > image_height:
            raise ValueError(f"{drawing}: out-of-bounds box for {label_id}: {box}")
        boxes.append((label_id, box))
    severe = []
    for index, (first_id, first_box) in enumerate(boxes):
        for second_id, second_box in boxes[index + 1 :]:
            ratio = overlap_ratio(first_box, second_box)
            if ratio > 0.25:
                severe.append(
                    {"first": first_id, "second": second_id, "containment_ratio": round(ratio, 4)}
                )
    if severe:
        raise ValueError(f"{drawing}: severe approved label overlaps: {severe[:10]}")


def copy_base_dataset(source: Path, output: Path):
    for folder in ("images", "labels", "previews"):
        shutil.copytree(source / folder, output / folder, dirs_exist_ok=True)
    shutil.copy2(source / "data.yaml", output / "data.yaml")


def build(args):
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"Output folder is not empty: {args.output}")
    if args.overlap < 0 or args.overlap >= args.tile_size:
        raise ValueError("Overlap must be non-negative and smaller than tile size")

    base_manifest_path = args.base_dataset / "dataset_manifest.json"
    base_manifest = load_json(base_manifest_path)
    if int(base_manifest["annotation_count"]) != 303:
        raise ValueError("The locked v3 base no longer contains exactly 303 labels")

    approval_paths = sorted(args.review_root.glob("STAGE_2_DRAWING_*_APPROVED.json"))
    if len(approval_paths) != 6:
        raise ValueError(f"Expected exactly six Stage 2 approval files, found {len(approval_paths)}")

    args.output.mkdir(parents=True, exist_ok=True)
    copy_base_dataset(args.base_dataset, args.output)

    with (args.base_dataset / "labels_manifest.csv").open(
        newline="", encoding="utf-8-sig"
    ) as stream:
        records = list(csv.DictReader(stream))

    base_splits = {
        split: list(drawings)
        for split, drawings in base_manifest["drawing_splits"].items()
    }
    combined_splits = {split: list(drawings) for split, drawings in base_splits.items()}
    new_drawing_summaries = []
    approval_summaries = []
    class_ids = {name: index for index, name in enumerate(CLASS_NAMES)}

    for approval_path in approval_paths:
        approval, labels, approved_paths = verify_approval(approval_path, args.review_root)
        drawing = approval["drawing"]
        if drawing not in NEW_DRAWING_SPLITS:
            raise ValueError(f"Unexpected approved drawing: {drawing}")
        split = NEW_DRAWING_SPLITS[drawing]
        combined_splits[split].append(drawing)
        image_path = args.batch_root / drawing / "original.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read source image: {image_path}")
        image_height, image_width = image.shape[:2]
        validate_labels(drawing, labels, image_width, image_height)

        tiles = [
            (x, y, min(args.tile_size, image_width), min(args.tile_size, image_height))
            for y in tile_starts(image_height, args.tile_size, args.overlap)
            for x in tile_starts(image_width, args.tile_size, args.overlap)
        ]
        assignments = {tile: [] for tile in tiles}
        for label in labels:
            box = tuple(float(value) for value in label["box"])
            tile = choose_tile(box, tiles)
            if tile is None:
                tile = containing_tile(
                    box, image_width, image_height, args.tile_size
                )
                if tile is None:
                    raise ValueError(
                        f"{drawing}: no safe tile contains {label['label_id']} {box}"
                    )
                if tile not in assignments:
                    assignments[tile] = []
            assignments[tile].append(label)

        class_counts = Counter()
        used_tiles = 0
        for tile, tile_labels in assignments.items():
            if not tile_labels:
                continue
            tx, ty, tw, th = tile
            stem = f"{drawing}__x{tx:04d}_y{ty:04d}"
            image_output = args.output / "images" / split / f"{stem}.png"
            label_output = args.output / "labels" / split / f"{stem}.txt"
            image_output.parent.mkdir(parents=True, exist_ok=True)
            label_output.parent.mkdir(parents=True, exist_ok=True)
            crop = image[ty : ty + th, tx : tx + tw]
            if not cv2.imwrite(str(image_output), crop):
                raise OSError(f"Could not write tile {image_output}")

            lines = []
            for label in sorted(tile_labels, key=lambda item: (item["box"][1], item["box"][0])):
                box = tuple(float(value) for value in label["box"])
                normalized = normalized_yolo(box, tile)
                if not all(0 < value <= 1 for value in normalized):
                    raise ValueError(f"{drawing}: invalid normalized label {normalized}")
                class_name = label["class_name"]
                lines.append(
                    f"{class_ids[class_name]} "
                    + " ".join(f"{value:.8f}" for value in normalized)
                )
                class_counts[class_name] += 1
                records.append(
                    {
                        "Drawing": drawing,
                        "Split": split,
                        "Tile": image_output.relative_to(args.output).as_posix(),
                        "Class": class_name,
                        "Source": "stage2_human_approved",
                        "Balloons": label["label_id"],
                        "X": box[0],
                        "Y": box[1],
                        "Width": box[2],
                        "Height": box[3],
                    }
                )
            label_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
            used_tiles += 1

        preview_output = args.output / "previews" / f"{drawing}_labels.png"
        shutil.copy2(approved_paths["preview"], preview_output)
        new_drawing_summaries.append(
            {
                "drawing": drawing,
                "split": split,
                "approved_labels": len(labels),
                "tiles": used_tiles,
                "class_counts": dict(sorted(class_counts.items())),
                "source_image": str(image_path),
                "source_image_sha256": sha256(image_path),
                "approval_file": str(approval_path),
                "approval_file_sha256": sha256(approval_path),
            }
        )
        approval_summaries.append(
            {
                "drawing": drawing,
                "approval": approval_path.name,
                "approved_label_count": int(approval["approved_label_count"]),
                "labels_sha256": approval["sha256"]["labels"],
                "plan_sha256": approval["sha256"]["plan"],
                "preview_sha256": approval["sha256"]["preview"],
            }
        )

    expected_total = 303 + sum(item["approved_label_count"] for item in approval_summaries)
    if expected_total != 639 or len(records) != expected_total:
        raise ValueError(f"Expected 639 combined labels, built {len(records)}")

    fields = ["Drawing", "Split", "Tile", "Class", "Source", "Balloons", "X", "Y", "Width", "Height"]
    with (args.output / "labels_manifest.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    class_counts = Counter(row["Class"] for row in records)
    split_counts = Counter(row["Split"] for row in records)
    train_classes = {row["Class"] for row in records if row["Split"] == "train"}
    missing_train_classes = sorted(set(CLASS_NAMES) - train_classes)
    if missing_train_classes:
        raise ValueError(f"Training split is missing classes: {missing_train_classes}")

    image_counts = {}
    for split in ("train", "val", "test"):
        image_files = list((args.output / "images" / split).glob("*.png"))
        label_files = list((args.output / "labels" / split).glob("*.txt"))
        image_stems = {path.stem for path in image_files}
        label_stems = {path.stem for path in label_files}
        if image_stems != label_stems:
            raise ValueError(
                f"{split}: image/label mismatch; "
                f"images only={sorted(image_stems-label_stems)[:5]}, "
                f"labels only={sorted(label_stems-image_stems)[:5]}"
            )
        image_counts[split] = len(image_files)

    data_yaml = [
        "path: .",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    data_yaml.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    (args.output / "data.yaml").write_text("\n".join(data_yaml) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "status": "combined_11_drawing_dataset_ready_for_visual_QC_not_training",
        "training_allowed": False,
        "production_model_change_authorized": False,
        "purpose": "Combine locked detector dataset v3 with six Stage 2 human-approved drawings",
        "base_dataset": str(args.base_dataset),
        "base_dataset_manifest_sha256": sha256(base_manifest_path),
        "base_annotation_count": 303,
        "new_annotation_count": 336,
        "annotation_count": len(records),
        "drawing_count": sum(len(drawings) for drawings in combined_splits.values()),
        "tile_size": args.tile_size,
        "tile_overlap": args.overlap,
        "classes": CLASS_NAMES,
        "class_counts": dict(sorted(class_counts.items())),
        "split_annotation_counts": dict(sorted(split_counts.items())),
        "split_tile_counts": image_counts,
        "drawing_splits": combined_splits,
        "drawing_level_split_no_tile_leakage": True,
        "train_contains_all_classes": True,
        "approvals": approval_summaries,
        "new_drawings": new_drawing_summaries,
        "required_next_step": "Human visual review of all 11 previews before candidate training package preparation",
    }
    (args.output / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    report = [
        "# Approved Detector Dataset v4",
        "",
        "Status: combined and structurally validated; visual approval still required.",
        "",
        f"- Drawings: {manifest['drawing_count']}",
        f"- Labels: {manifest['annotation_count']} (303 existing + 336 new)",
        f"- Train/val/test labels: {split_counts['train']}/{split_counts['val']}/{split_counts['test']}",
        f"- Train/val/test tiles: {image_counts['train']}/{image_counts['val']}/{image_counts['test']}",
        "- Drawing-level split: yes; no drawing appears in more than one split",
        "- Approval hashes: verified for all six new drawings",
        "- Training started: no",
        "- Production model changed: no",
        "",
        "## Class counts",
        "",
    ]
    report.extend(f"- {name}: {class_counts.get(name, 0)}" for name in CLASS_NAMES)
    report.extend(
        [
            "",
            "## Required visual check",
            "",
            "Open every image in previews/. Confirm each box contains one complete characteristic,",
            "contains no unwanted note or triangle, and does not cut a value or overlap another label.",
            "",
            "Only after all 11 previews are approved may a new candidate training package be prepared.",
        ]
    )
    (args.output / "QUALITY_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dataset", required=True, type=Path)
    parser.add_argument("--review-root", required=True, type=Path)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tile-size", type=int, default=1280)
    parser.add_argument("--overlap", type=int, default=320)
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
