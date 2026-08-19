"""Run local tiled symbol detection on one rendered engineering drawing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import cv2

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

os.environ.setdefault("YOLO_SYMBOL_TILING_ENABLED", "1")

from vision_tools import detect_symbols_with_yolo


COLORS = {
    "local_yolo": (0, 140, 255),
    "local_yolo_ensemble_addition": (180, 60, 180),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    image_path = args.image.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image was not found: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Image could not be opened: {image_path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    detections = detect_symbols_with_yolo(image)

    json_path = args.output_dir / "tiled_symbol_detections.json"
    json_path.write_text(
        json.dumps(detections, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    preview = image.copy()
    for detection in detections:
        x = int(detection["X"])
        y = int(detection["Y"])
        width = int(detection["Width"])
        height = int(detection["Height"])
        detector = str(detection.get("Detector", ""))
        color = COLORS.get(detector, (0, 180, 0))
        cv2.rectangle(preview, (x, y), (x + width, y + height), color, 3)
        label = (
            f"{detection.get('Symbol Class', '')} "
            f"{float(detection.get('Confidence', 0)):.2f}"
        )
        cv2.putText(
            preview,
            label,
            (x, max(20, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    preview_path = args.output_dir / "tiled_symbol_detections.png"
    if not cv2.imwrite(str(preview_path), preview):
        raise OSError(f"Could not write preview: {preview_path}")

    detector_counts = Counter(
        str(item.get("Detector", "")) for item in detections
    )
    class_counts = Counter(
        str(item.get("Symbol Class", "")) for item in detections
    )
    summary = {
        "image": str(image_path),
        "image_width": int(image.shape[1]),
        "image_height": int(image.shape[0]),
        "detection_total": len(detections),
        "detector_counts": dict(sorted(detector_counts.items())),
        "class_counts": dict(sorted(class_counts.items())),
        "json": str(json_path),
        "preview": str(preview_path),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
