"""Evaluate a baseline model with an optional class-specific specialist.

This is an isolated gate tool. It never changes production weights or labels.
The specialist may be limited to selected classes and may be preferred for
same-class duplicate decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from compare_detector_candidates import (
    draw_issue_map,
    drawing_issues,
    load_truths,
    predict_tiles,
)
from detector_ensemble import (
    baseline_priority_merge,
    intersection_over_smaller,
    is_duplicate,
)


def issue_counts(issues):
    counts = Counter(issue["type"] for issue in issues)
    return {
        "missing": counts["missing"],
        "fixed": counts["fixed"],
        "regression": counts["regression"],
        "extra": counts["extra"],
        "box_review": counts["box_review"],
    }


def serializable_predictions(predictions):
    return {
        drawing: [
            {
                **prediction,
                "box": [round(float(value), 4) for value in prediction["box"]],
                "confidence": round(float(prediction["confidence"]), 6),
            }
            for prediction in items
        ]
        for drawing, items in sorted(predictions.items())
    }


def write_report(
    output_root,
    confidence,
    baseline_label,
    addition_label,
    addition_classes,
    preferred_classes,
    summaries,
    all_issues,
    suppressed_by_drawing,
    ensemble_by_drawing,
    gate_passed,
):
    payload = {
        "schema_version": 1,
        "status": (
            "detector_gate_passed_full_ocr_gate_required"
            if gate_passed
            else "detector_gate_failed"
        ),
        "production_changed": False,
        "confidence_threshold": confidence,
        "merge_policy": {
            "baseline_label": baseline_label,
            "addition_label": addition_label,
            "addition_classes": sorted(addition_classes),
            "preferred_addition_classes": sorted(preferred_classes),
            "same_class_iou_duplicate_threshold": 0.30,
            "same_class_containment_duplicate_threshold": 0.70,
        },
        "summaries": summaries,
        "issues": all_issues,
        "suppressed_specialist_predictions": serializable_predictions(
            suppressed_by_drawing
        ),
        "ensemble_predictions": serializable_predictions(ensemble_by_drawing),
        "detector_gate_passed": gate_passed,
        "next_required_step": (
            "Run the complete OCR golden regression without changing production"
            if gate_passed
            else "Do not run production activation; inspect regressions and extras"
        ),
    }
    (output_root / "ensemble_gate.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        f"# {baseline_label} + {addition_label} Specialist Detector Gate",
        "",
        f"Decision: **{'PASS' if gate_passed else 'FAIL'}**",
        "",
        "Production changed: **No**",
        "",
        (
            f"Merge rule: retain {baseline_label} as the baseline; allow "
            f"{addition_label} only for {', '.join(sorted(addition_classes)) or 'all classes'}."
        ),
        "",
        "| Drawing | Approved | V3 matches | Ensemble matches | V3 extras | Ensemble extras | Regressions | Added fixes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for drawing, summary in summaries.items():
        counts = issue_counts(all_issues[drawing])
        lines.append(
            f"| {drawing} | {summary['approved']} | "
            f"{summary['baseline_matches']} | {summary['candidate_matches']} | "
            f"{summary['baseline_extras']} | {summary['candidate_extras']} | "
            f"{counts['regression']} | {counts['fixed']} |"
        )
    lines.extend(
        [
            "",
            "The detector gate passes only when:",
            "",
            "- no V3-correct characteristic is lost;",
            "- no false extra prediction is introduced;",
            "- every drawing has at least as many approved matches as V3.",
            "",
            (
                "Next: run the complete OCR golden regression. Do not activate "
                "production yet."
                if gate_passed
                else "Stop: the ensemble is not eligible for the full OCR gate."
            ),
        ]
    )
    (output_root / "ENSEMBLE_GATE_DECISION.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--baseline-model", required=True, type=Path)
    parser.add_argument("--addition-model", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--confidence", type=float, default=0.60)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--addition-label", default="specialist")
    parser.add_argument(
        "--addition-classes",
        default="",
        help="Comma-separated classes the specialist may contribute.",
    )
    parser.add_argument(
        "--preferred-addition-classes",
        default="",
        help="Comma-separated classes where a duplicate specialist box wins.",
    )
    args = parser.parse_args()

    dataset_root = args.dataset.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    addition_classes = {
        item.strip()
        for item in args.addition_classes.split(",")
        if item.strip()
    }
    preferred_classes = {
        item.strip()
        for item in args.preferred_addition_classes.split(",")
        if item.strip()
    }
    truths_by_drawing = load_truths(dataset_root, args.split)
    baseline = predict_tiles(
        args.baseline_model.resolve(),
        dataset_root,
        args.split,
        args.confidence,
        args.imgsz,
        args.device,
    )
    addition = predict_tiles(
        args.addition_model.resolve(),
        dataset_root,
        args.split,
        args.confidence,
        args.imgsz,
        args.device,
    )

    ensemble_by_drawing = {}
    suppressed_by_drawing = {}
    summaries = {}
    all_issues = {}
    detector_gate_passed = True
    for drawing, truths in sorted(truths_by_drawing.items()):
        ensemble, suppressed = baseline_priority_merge(
            baseline.get(drawing, []),
            addition.get(drawing, []),
            addition_classes=addition_classes,
            preferred_addition_classes=preferred_classes,
            baseline_source=args.baseline_label,
            addition_source=args.addition_label,
        )
        issues, summary = drawing_issues(
            truths, baseline.get(drawing, []), ensemble
        )
        counts = issue_counts(issues)
        drawing_passed = (
            counts["regression"] == 0
            and summary["candidate_extras"] == 0
            and summary["candidate_matches"] >= summary["baseline_matches"]
        )
        detector_gate_passed = detector_gate_passed and drawing_passed
        preview = dataset_root / "previews" / f"{drawing}_labels.png"
        issue_map = output_root / "issue_maps" / f"{drawing}_v3_ensemble_issues.png"
        draw_issue_map(preview, issue_map, issues)
        ensemble_by_drawing[drawing] = ensemble
        suppressed_by_drawing[drawing] = suppressed
        summaries[drawing] = summary
        all_issues[drawing] = issues

    write_report(
        output_root,
        args.confidence,
        args.baseline_label,
        args.addition_label,
        addition_classes,
        preferred_classes,
        summaries,
        all_issues,
        suppressed_by_drawing,
        ensemble_by_drawing,
        detector_gate_passed,
    )
    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "detector_gate_passed": detector_gate_passed,
                "summaries": summaries,
            },
            indent=2,
        )
    )
    return 0 if detector_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
