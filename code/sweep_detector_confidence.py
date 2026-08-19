"""Sweep detector confidence thresholds using one cached prediction pass.

This tool is review-only. It never trains a model, edits approved labels, or
activates production weights. Both models predict once at the minimum requested
confidence. Higher thresholds are evaluated by filtering those cached boxes.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path


def load_comparator(path: Path):
    spec = importlib.util.spec_from_file_location("detector_compare", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def filtered(predictions, threshold):
    return {
        drawing: [
            item for item in items if float(item["confidence"]) >= threshold
        ]
        for drawing, items in predictions.items()
    }


def aggregate(comparator, truths_by_drawing, baseline, candidate):
    totals = Counter()
    class_totals = {}
    issues_by_drawing = {}
    for drawing, truths in sorted(truths_by_drawing.items()):
        baseline_items = baseline.get(drawing, [])
        candidate_items = candidate.get(drawing, [])
        issues, summary = comparator.drawing_issues(
            truths, baseline_items, candidate_items
        )
        issues_by_drawing[drawing] = issues
        for key, value in summary.items():
            totals[key] += int(value)
        totals.update(issue["type"] for issue in issues)

        for class_name in sorted({truth["class_name"] for truth in truths}):
            class_truths = [
                truth for truth in truths if truth["class_name"] == class_name
            ]
            class_baseline = [
                item for item in baseline_items if item["class_name"] == class_name
            ]
            class_candidate = [
                item for item in candidate_items if item["class_name"] == class_name
            ]
            baseline_matches, baseline_prediction_matches = comparator.greedy_matches(
                class_truths, class_baseline
            )
            candidate_matches, candidate_prediction_matches = comparator.greedy_matches(
                class_truths, class_candidate
            )
            entry = class_totals.setdefault(
                class_name,
                Counter(
                    approved=0,
                    baseline_matches=0,
                    candidate_matches=0,
                    baseline_extras=0,
                    candidate_extras=0,
                ),
            )
            entry["approved"] += len(class_truths)
            entry["baseline_matches"] += len(baseline_matches)
            entry["candidate_matches"] += len(candidate_matches)
            entry["baseline_extras"] += (
                len(class_baseline) - len(baseline_prediction_matches)
            )
            entry["candidate_extras"] += (
                len(class_candidate) - len(candidate_prediction_matches)
            )
    return dict(totals), {
        name: dict(values) for name, values in class_totals.items()
    }, issues_by_drawing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--baseline-model", required=True, type=Path)
    parser.add_argument("--candidate-model", required=True, type=Path)
    parser.add_argument("--comparator", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--reference-confidence", type=float, default=0.60)
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=[0.20, 0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70],
    )
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    thresholds = sorted(set(args.thresholds + [args.reference_confidence]))
    if not thresholds or thresholds[0] <= 0 or thresholds[-1] >= 1:
        raise ValueError("Thresholds must be between 0 and 1")
    comparator = load_comparator(args.comparator.resolve())
    dataset = args.dataset.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    truths = comparator.load_truths(dataset, args.split)

    minimum = thresholds[0]
    print(f"Predicting baseline once at confidence {minimum:.2f}...", flush=True)
    baseline_raw = comparator.predict_tiles(
        args.baseline_model.resolve(),
        dataset,
        args.split,
        minimum,
        args.imgsz,
        args.device,
    )
    print(f"Predicting candidate once at confidence {minimum:.2f}...", flush=True)
    candidate_raw = comparator.predict_tiles(
        args.candidate_model.resolve(),
        dataset,
        args.split,
        minimum,
        args.imgsz,
        args.device,
    )
    (output / "prediction_cache.json").write_text(
        json.dumps(
            {
                "minimum_confidence": minimum,
                "baseline_model": str(args.baseline_model.resolve()),
                "candidate_model": str(args.candidate_model.resolve()),
                "baseline": baseline_raw,
                "candidate": candidate_raw,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    baseline_reference = filtered(baseline_raw, args.reference_confidence)
    rows = []
    details = {}
    for threshold in thresholds:
        baseline_same = filtered(baseline_raw, threshold)
        candidate = filtered(candidate_raw, threshold)
        same_totals, same_classes, _ = aggregate(
            comparator, truths, baseline_same, candidate
        )
        reference_totals, reference_classes, reference_issues = aggregate(
            comparator, truths, baseline_reference, candidate
        )
        row = {
            "candidate_threshold": threshold,
            "approved": reference_totals.get("approved", 0),
            "v3_reference_threshold": args.reference_confidence,
            "v3_reference_matches": reference_totals.get("baseline_matches", 0),
            "v3_reference_extras": reference_totals.get("baseline_extras", 0),
            "v7_matches": reference_totals.get("candidate_matches", 0),
            "v7_extras": reference_totals.get("candidate_extras", 0),
            "regressions_vs_v3_reference": reference_totals.get("regression", 0),
            "fixes_vs_v3_reference": reference_totals.get("fixed", 0),
            "missing_both": reference_totals.get("missing", 0),
            "box_reviews": reference_totals.get("box_review", 0),
            "same_threshold_v3_matches": same_totals.get("baseline_matches", 0),
            "same_threshold_v3_extras": same_totals.get("baseline_extras", 0),
            "eligible_for_review": (
                reference_totals.get("regression", 0) == 0
                and reference_totals.get("candidate_extras", 0)
                <= reference_totals.get("baseline_extras", 0)
                and reference_totals.get("candidate_matches", 0)
                >= reference_totals.get("baseline_matches", 0)
            ),
        }
        rows.append(row)
        details[f"{threshold:.2f}"] = {
            "summary_vs_v3_reference": reference_totals,
            "class_summary_vs_v3_reference": reference_classes,
            "issues_vs_v3_reference": reference_issues,
            "same_threshold_summary": same_totals,
            "same_threshold_class_summary": same_classes,
        }
        print(json.dumps(row), flush=True)

    with (output / "threshold_sweep.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "threshold_sweep.json").write_text(
        json.dumps(
            {
                "status": "review_only_production_unchanged",
                "reference_confidence": args.reference_confidence,
                "rows": rows,
                "details": details,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    eligible = [row for row in rows if row["eligible_for_review"]]
    lines = [
        "# Detector confidence sweep",
        "",
        "Production was not changed.",
        "",
        f"V3 is fixed at confidence {args.reference_confidence:.2f}; V7 is swept.",
        "",
        "| V7 threshold | V3 matches | V7 matches | Regressions | Fixes | V7 extras | Eligible |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['candidate_threshold']:.2f} | "
            f"{row['v3_reference_matches']} | {row['v7_matches']} | "
            f"{row['regressions_vs_v3_reference']} | "
            f"{row['fixes_vs_v3_reference']} | {row['v7_extras']} | "
            f"{'YES' if row['eligible_for_review'] else 'NO'} |"
        )
    lines.extend(
        [
            "",
            (
                "At least one threshold passed the numerical pre-check; visual "
                "review is still required."
                if eligible
                else "No threshold passed the no-regression/no-extra pre-check."
            ),
        ]
    )
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output_root": str(output), "eligible": eligible}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
