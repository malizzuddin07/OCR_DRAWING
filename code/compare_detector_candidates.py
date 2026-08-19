"""Compare two YOLO detector candidates on an approved tiled dataset.

The tool is intentionally review-only. It does not modify labels, train a
model, or activate production weights. Predictions from overlapping tiles are
converted back to full-page coordinates, deduplicated, matched to approved
labels, and drawn on the approved full-page previews.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import cv2
from ultralytics import YOLO


TILE_PATTERN = re.compile(r"__x(?P<x>\d+)_y(?P<y>\d+)")
COLORS = {
    "fixed": (40, 170, 40),
    "regression": (0, 120, 255),
    "missing": (0, 0, 255),
    "extra": (255, 0, 255),
    "box_review": (0, 200, 255),
}


def box_iou(first, second):
    """Return intersection-over-union for x, y, width, height boxes."""
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def classwise_nms(predictions, threshold=0.5):
    """Deduplicate predictions produced by overlapping full-page tiles."""
    kept = []
    by_class = defaultdict(list)
    for prediction in predictions:
        by_class[prediction["class_name"]].append(prediction)
    for class_predictions in by_class.values():
        ordered = sorted(
            class_predictions, key=lambda item: item["confidence"], reverse=True
        )
        while ordered:
            best = ordered.pop(0)
            kept.append(best)
            ordered = [
                item
                for item in ordered
                if box_iou(best["box"], item["box"]) < threshold
            ]
    return kept


def greedy_matches(truths, predictions, threshold=0.5):
    """Match predictions to approved boxes one-to-one by class and IoU."""
    candidates = []
    for truth_index, truth in enumerate(truths):
        for prediction_index, prediction in enumerate(predictions):
            if truth["class_name"] != prediction["class_name"]:
                continue
            overlap = box_iou(truth["box"], prediction["box"])
            if overlap >= threshold:
                candidates.append((overlap, truth_index, prediction_index))
    matched_truths = {}
    matched_predictions = set()
    for overlap, truth_index, prediction_index in sorted(candidates, reverse=True):
        if truth_index in matched_truths or prediction_index in matched_predictions:
            continue
        matched_truths[truth_index] = {
            "prediction_index": prediction_index,
            "iou": overlap,
        }
        matched_predictions.add(prediction_index)
    return matched_truths, matched_predictions


def load_truths(dataset_root, split):
    drawings = defaultdict(list)
    manifest_path = dataset_root / "labels_manifest.csv"
    with manifest_path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row["Split"] != split:
                continue
            drawings[row["Drawing"]].append(
                {
                    "class_name": row["Class"],
                    "box": [
                        float(row["X"]),
                        float(row["Y"]),
                        float(row["Width"]),
                        float(row["Height"]),
                    ],
                    "label_id": row["Balloons"],
                }
            )
    return drawings


def predict_tiles(model_path, dataset_root, split, confidence, image_size, device):
    model = YOLO(str(model_path))
    predictions = defaultdict(list)
    image_paths = sorted((dataset_root / "images" / split).glob("*.png"))
    results = model.predict(
        [str(path) for path in image_paths],
        conf=confidence,
        imgsz=image_size,
        device=device,
        batch=1,
        stream=True,
        verbose=False,
    )
    names = model.names
    for image_path, result in zip(image_paths, results):
        match = TILE_PATTERN.search(image_path.stem)
        if not match:
            raise ValueError(f"Tile name has no coordinate suffix: {image_path.name}")
        drawing = image_path.stem[: match.start()]
        offset_x = int(match.group("x"))
        offset_y = int(match.group("y"))
        if result.boxes is None:
            continue
        for box in result.boxes:
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
            class_id = int(box.cls[0])
            predictions[drawing].append(
                {
                    "class_name": str(names[class_id]),
                    "box": [
                        x1 + offset_x,
                        y1 + offset_y,
                        x2 - x1,
                        y2 - y1,
                    ],
                    "confidence": float(box.conf[0]),
                    "tile": image_path.name,
                }
            )
    return {
        drawing: classwise_nms(items)
        for drawing, items in predictions.items()
    }


def drawing_issues(truths, baseline_predictions, candidate_predictions):
    baseline_matches, baseline_prediction_matches = greedy_matches(
        truths, baseline_predictions
    )
    candidate_matches, candidate_prediction_matches = greedy_matches(
        truths, candidate_predictions
    )
    issues = []
    for truth_index, truth in enumerate(truths):
        baseline_match = baseline_matches.get(truth_index)
        candidate_match = candidate_matches.get(truth_index)
        if candidate_match is None:
            issues.append(
                {
                    "type": "regression" if baseline_match else "missing",
                    "class_name": truth["class_name"],
                    "label_id": truth["label_id"],
                    "box": truth["box"],
                    "baseline_iou": baseline_match["iou"] if baseline_match else None,
                    "candidate_iou": None,
                }
            )
        elif baseline_match is None:
            issues.append(
                {
                    "type": "fixed",
                    "class_name": truth["class_name"],
                    "label_id": truth["label_id"],
                    "box": truth["box"],
                    "baseline_iou": None,
                    "candidate_iou": candidate_match["iou"],
                }
            )
        elif candidate_match["iou"] < 0.75:
            candidate_prediction = candidate_predictions[
                candidate_match["prediction_index"]
            ]
            issues.append(
                {
                    "type": "box_review",
                    "class_name": truth["class_name"],
                    "label_id": truth["label_id"],
                    "box": candidate_prediction["box"],
                    "approved_box": truth["box"],
                    "baseline_iou": baseline_match["iou"],
                    "candidate_iou": candidate_match["iou"],
                }
            )
    for prediction_index, prediction in enumerate(candidate_predictions):
        if prediction_index not in candidate_prediction_matches:
            issues.append(
                {
                    "type": "extra",
                    "class_name": prediction["class_name"],
                    "label_id": "",
                    "box": prediction["box"],
                    "confidence": prediction["confidence"],
                    "baseline_iou": None,
                    "candidate_iou": None,
                }
            )
    return issues, {
        "approved": len(truths),
        "baseline_predictions": len(baseline_predictions),
        "candidate_predictions": len(candidate_predictions),
        "baseline_matches": len(baseline_matches),
        "candidate_matches": len(candidate_matches),
        "baseline_extras": len(baseline_predictions) - len(baseline_prediction_matches),
        "candidate_extras": len(candidate_predictions) - len(candidate_prediction_matches),
    }


def draw_label(image, text, x, y, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.55, min(image.shape[:2]) / 2500)
    thickness = max(1, round(scale * 2))
    (width, height), baseline = cv2.getTextSize(
        text, font, scale, thickness
    )
    top = max(0, y - height - baseline - 8)
    right = min(image.shape[1] - 1, x + width + 8)
    cv2.rectangle(image, (x, top), (right, y), color, -1)
    cv2.putText(
        image,
        text,
        (x + 4, y - baseline - 2),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def draw_issue_map(preview_path, output_path, issues):
    image = cv2.imread(str(preview_path))
    if image is None:
        raise FileNotFoundError(f"Could not read preview: {preview_path}")
    counters = Counter()
    for issue in issues:
        issue_type = issue["type"]
        counters[issue_type] += 1
        prefix = {
            "fixed": "FIXED",
            "regression": "REGRESSION",
            "missing": "MISSING",
            "extra": "EXTRA",
            "box_review": "BOX",
        }[issue_type]
        identifier = f"{prefix} {counters[issue_type]}"
        x, y, width, height = [round(value) for value in issue["box"]]
        color = COLORS[issue_type]
        line_width = max(2, round(min(image.shape[:2]) / 1200))
        cv2.rectangle(
            image,
            (max(0, x), max(0, y)),
            (min(image.shape[1] - 1, x + width), min(image.shape[0] - 1, y + height)),
            color,
            line_width,
        )
        draw_label(image, identifier, max(0, x), max(20, y), color)
        issue["review_id"] = identifier
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise OSError(f"Could not write issue map: {output_path}")


def write_review(output_root, summaries, all_issues, confidence):
    rows = []
    for drawing, issues in all_issues.items():
        for issue in issues:
            rows.append(
                {
                    "Drawing": drawing,
                    "Review ID": issue["review_id"],
                    "Type": issue["type"],
                    "Class": issue["class_name"],
                    "Approved Label": issue.get("label_id", ""),
                    "Confidence": round(issue.get("confidence", 0), 4)
                    if issue.get("confidence") is not None
                    else "",
                    "Baseline IoU": round(issue["baseline_iou"], 4)
                    if issue.get("baseline_iou") is not None
                    else "",
                    "Candidate IoU": round(issue["candidate_iou"], 4)
                    if issue.get("candidate_iou") is not None
                    else "",
                    "Box": json.dumps([round(value, 2) for value in issue["box"]]),
                }
            )
    with (output_root / "issues.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["Drawing"])
        writer.writeheader()
        writer.writerows(rows)
    (output_root / "comparison.json").write_text(
        json.dumps(
            {
                "status": "review_required_not_approved",
                "production_changed": False,
                "confidence_threshold": confidence,
                "summaries": summaries,
                "issues": all_issues,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = [
        "# V3 versus V4 reserved-drawing review",
        "",
        "Status: REVIEW REQUIRED - NOT APPROVED FOR TRAINING OR PRODUCTION",
        "",
        f"Predictions use the current production confidence threshold of {confidence:.2f}.",
        "",
        "## Colours",
        "",
        "- RED MISSING: both models missed an approved characteristic.",
        "- ORANGE REGRESSION: V3 found it but V4 missed it.",
        "- MAGENTA EXTRA: V4 predicted a box with no approved match.",
        "- YELLOW BOX: V4 found the characteristic but the box needs size/position review.",
        "- GREEN FIXED: V4 found an approved characteristic missed by V3.",
        "",
        "## Drawing summary",
        "",
        "| Drawing | Approved | V3 matched | V4 matched | V3 extras | V4 extras |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for drawing, summary in summaries.items():
        lines.append(
            f"| {drawing} | {summary['approved']} | "
            f"{summary['baseline_matches']} | {summary['candidate_matches']} | "
            f"{summary['baseline_extras']} | {summary['candidate_extras']} |"
        )
    lines.extend(
        [
            "",
            "## What to check",
            "",
            "Open each PNG in issue_maps/. Report only IDs that are wrong, for example:",
            "",
            "`W3-C111266101-01: EXTRA 2 is actually needed; BOX 3 must move left.`",
            "",
            "Do not edit labels or start training until this review is confirmed.",
        ]
    )
    (output_root / "REVIEW_INSTRUCTIONS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--baseline-model", required=True, type=Path)
    parser.add_argument("--candidate-model", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--confidence", type=float, default=0.60)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    dataset_root = args.dataset.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    truths_by_drawing = load_truths(dataset_root, args.split)
    baseline = predict_tiles(
        args.baseline_model.resolve(),
        dataset_root,
        args.split,
        args.confidence,
        args.imgsz,
        args.device,
    )
    candidate = predict_tiles(
        args.candidate_model.resolve(),
        dataset_root,
        args.split,
        args.confidence,
        args.imgsz,
        args.device,
    )

    summaries = {}
    all_issues = {}
    for drawing, truths in sorted(truths_by_drawing.items()):
        issues, summary = drawing_issues(
            truths, baseline.get(drawing, []), candidate.get(drawing, [])
        )
        preview = dataset_root / "previews" / f"{drawing}_labels.png"
        output = output_root / "issue_maps" / f"{drawing}_v3_v4_issues.png"
        draw_issue_map(preview, output, issues)
        summaries[drawing] = summary
        all_issues[drawing] = issues
    write_review(output_root, summaries, all_issues, args.confidence)
    print(json.dumps({"output_root": str(output_root), "summaries": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
