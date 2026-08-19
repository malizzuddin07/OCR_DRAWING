"""Create a new review revision by adding one human-reported missing label."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import cv2


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


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def draw_box(image, label, *, show_tag: bool):
    x, y, width, height = (round(value) for value in label["box"])
    color = CLASS_COLORS[label["class_name"]]
    thickness = max(2, round(max(image.shape[:2]) / 2200))
    cv2.rectangle(image, (x, y), (x + width, y + height), color, thickness)
    if not show_tag:
        return

    font_scale = max(0.55, max(image.shape[:2]) / 7800)
    tag = f"{label['hard_id']} B{label['balloons']}"
    (text_width, text_height), baseline = cv2.getTextSize(
        tag, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    tag_x = x
    tag_y = max(text_height + baseline + 4, y - 4)
    cv2.rectangle(
        image,
        (tag_x, tag_y - text_height - baseline - 4),
        (tag_x + text_width + 8, tag_y + 3),
        color,
        -1,
    )
    cv2.putText(
        image,
        tag,
        (tag_x + 4, tag_y - baseline),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-review", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--hard-id", required=True)
    parser.add_argument("--balloon", required=True)
    parser.add_argument("--class-name", required=True, choices=CLASS_COLORS)
    parser.add_argument("--expected-value", required=True)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--width", required=True, type=float)
    parser.add_argument("--height", required=True, type=float)
    args = parser.parse_args()

    base = args.base_review.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(output)

    labels_path = base / f"{args.drawing}_hard_labels.json"
    focused_path = base / f"{args.drawing}_hard_labels.png"
    approved_path = base / f"{args.drawing}_all_approved_labels.png"
    payload = load_json(labels_path)

    if any(item["hard_id"] == args.hard_id for item in payload["labels"]):
        raise ValueError(f"Duplicate hard ID: {args.hard_id}")
    if any(str(item["balloons"]) == args.balloon for item in payload["labels"]):
        raise ValueError(f"Duplicate balloon: {args.balloon}")

    supplemental = {
        "hard_id": args.hard_id,
        "drawing": args.drawing,
        "issue": "MISSING",
        "severity": "HIGH",
        "class_name": args.class_name,
        "balloons": args.balloon,
        "expected_value": args.expected_value,
        "box": [args.x, args.y, args.width, args.height],
        "source": "human_reported_supplemental_label",
    }
    payload["labels"].append(supplemental)
    payload["label_count"] = len(payload["labels"])
    payload["missing_issue_labels"] = sum(
        item["issue"] == "MISSING" for item in payload["labels"]
    )

    focused = cv2.imread(str(focused_path))
    approved = cv2.imread(str(approved_path))
    if focused is None or approved is None:
        raise FileNotFoundError("Could not load the base review previews")
    x, y, width, height = supplemental["box"]
    for image in (focused, approved):
        if x < 0 or y < 0 or x + width > image.shape[1] or y + height > image.shape[0]:
            raise ValueError(f"Supplemental box is outside the image: {supplemental['box']}")

    draw_box(focused, supplemental, show_tag=True)
    draw_box(approved, supplemental, show_tag=False)

    output.mkdir(parents=True)
    new_focused = output / focused_path.name
    new_approved = output / approved_path.name
    if not cv2.imwrite(str(new_focused), focused):
        raise OSError(new_focused)
    if not cv2.imwrite(str(new_approved), approved):
        raise OSError(new_approved)

    (output / labels_path.name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    instructions = output / "REVIEW_INSTRUCTIONS.md"
    instructions.write_text(
        f"""# {args.drawing} hard-example label review V2

Review `{new_approved.name}`.

- The previously approved 57 boxes are unchanged.
- The only new box is balloon {args.balloon}, dimension `{args.expected_value}`.
- Confirm the new orange box tightly contains the complete value.

Nothing in this folder is approved for training yet.
""",
        encoding="utf-8",
    )
    shutil.copy2(base / "review_manifest.json", output / "base_review_manifest.json")
    manifest = {
        "schema_version": 1,
        "status": "human_visual_review_required",
        "training_allowed": False,
        "production_model_change_authorized": False,
        "drawing": args.drawing,
        "hard_label_count": len(payload["labels"]),
        "approved_preview_label_count": 58,
        "supplemental_label": supplemental,
        "focused_preview": new_focused.name,
        "full_approved_preview": new_approved.name,
        "labels": labels_path.name,
        "instructions": instructions.name,
        "base_review": str(base),
    }
    (output / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
