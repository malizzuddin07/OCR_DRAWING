"""Draw proposal IDs on full-page detector review previews.

The proposal numbers come directly from each unapproved label_proposals.json
file, so they match correction reports such as CODEX_PRE_REVIEW.md.
"""

from __future__ import annotations

import argparse
import json
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


def readable_text_color(bgr):
    blue, green, red = bgr
    brightness = 0.114 * blue + 0.587 * green + 0.299 * red
    return (0, 0, 0) if brightness >= 145 else (255, 255, 255)


def draw_numbered_preview(image, proposals):
    preview = image.copy()
    max_side = max(preview.shape[:2])
    thickness = max(3, round(max_side / 1800))
    font_scale = max(0.65, max_side / 6500)
    font_thickness = max(2, round(thickness * 0.75))
    for proposal in proposals:
        x, y, width, height = (round(float(value)) for value in proposal["box"])
        color = CLASS_COLORS.get(proposal["class_name"], (0, 100, 255))
        cv2.rectangle(preview, (x, y), (x + width, y + height), color, thickness)

        label = f"ID {proposal['proposal_id']}"
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            font_thickness,
        )
        padding = max(5, thickness + 2)
        label_width = text_width + padding * 2
        label_height = text_height + baseline + padding * 2
        label_x = max(0, min(preview.shape[1] - label_width, x))
        label_y2 = y - max(2, thickness)
        label_y1 = label_y2 - label_height
        if label_y1 < 0:
            label_y1 = min(preview.shape[0] - label_height, y + height + max(2, thickness))
            label_y2 = label_y1 + label_height
        cv2.rectangle(
            preview,
            (label_x, label_y1),
            (label_x + label_width, label_y2),
            color,
            -1,
        )
        cv2.putText(
            preview,
            label,
            (label_x + padding, label_y2 - baseline - padding),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            readable_text_color(color),
            font_thickness,
            cv2.LINE_AA,
        )
    return preview


def build_numbered_previews(batch_root: Path, output_dir: Path):
    status = load_json(batch_root / "batch_status.json")
    if status.get("status") != "complete":
        raise ValueError("Detector review batch is not complete.")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for entry in status["drawings"]:
        drawing = entry["drawing"]
        drawing_dir = batch_root / drawing
        image = cv2.imread(str(drawing_dir / "original.png"))
        if image is None:
            raise FileNotFoundError(drawing_dir / "original.png")
        payload = load_json(drawing_dir / "label_proposals.json")
        preview = draw_numbered_preview(image, payload["proposals"])
        output_path = output_dir / f"{drawing}_numbered_labels.png"
        if not cv2.imwrite(str(output_path), preview):
            raise OSError(f"Could not write {output_path}")
        outputs.append(
            {
                "drawing": drawing,
                "proposal_count": len(payload["proposals"]),
                "preview": output_path.name,
            }
        )
    manifest = {
        "schema_version": 1,
        "source_batch": str(batch_root),
        "status": "unapproved_numbered_review_previews",
        "drawings": outputs,
    }
    (output_dir / "numbered_preview_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_numbered_previews(args.batch_root.resolve(), args.output_dir.resolve())
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
