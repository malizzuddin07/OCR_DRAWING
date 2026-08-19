"""Evaluate a baseline-preserving detector ensemble from cached predictions.

Baseline boxes are always retained. Candidate boxes are added only when they do
not duplicate a same-class baseline or previously accepted candidate box. This
is review-only and never changes production weights or approved labels.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
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


def protected_union(comparator, baseline, candidate, duplicate_iou):
    combined = {}
    for drawing in sorted(set(baseline) | set(candidate)):
        baseline_items = list(baseline.get(drawing, []))
        additions = []
        ordered = sorted(
            candidate.get(drawing, []),
            key=lambda item: float(item["confidence"]),
            reverse=True,
        )
        for item in ordered:
            duplicates_baseline = any(
                item["class_name"] == existing["class_name"]
                and comparator.box_iou(item["box"], existing["box"])
                >= duplicate_iou
                for existing in baseline_items
            )
            if duplicates_baseline:
                continue
            duplicates_addition = any(
                item["class_name"] == existing["class_name"]
                and comparator.box_iou(item["box"], existing["box"])
                >= duplicate_iou
                for existing in additions
            )
            if not duplicates_addition:
                additions.append(item)
        combined[drawing] = baseline_items + additions
    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--comparator", required=True, type=Path)
    parser.add_argument("--sweep-module", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--baseline-confidence", type=float, default=0.60)
    parser.add_argument("--duplicate-iou", type=float, default=0.50)
    parser.add_argument(
        "--candidate-thresholds",
        type=float,
        nargs="+",
        default=[0.30, 0.40, 0.50, 0.55, 0.60],
    )
    args = parser.parse_args()

    comparator = load_module("detector_compare", args.comparator.resolve())
    sweep = load_module("detector_sweep", args.sweep_module.resolve())
    cache = json.loads(args.cache.read_text(encoding="utf-8"))
    minimum = float(cache["minimum_confidence"])
    if args.baseline_confidence < minimum:
        raise ValueError("Baseline threshold is below cached minimum")
    if any(value < minimum for value in args.candidate_thresholds):
        raise ValueError("Candidate threshold is below cached minimum")

    truths = comparator.load_truths(args.dataset.resolve(), args.split)
    baseline = filtered(cache["baseline"], args.baseline_confidence)
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    details = {}
    for threshold in sorted(set(args.candidate_thresholds)):
        candidate = filtered(cache["candidate"], threshold)
        ensemble = protected_union(
            comparator, baseline, candidate, args.duplicate_iou
        )
        totals, classes, issues = sweep.aggregate(
            comparator, truths, baseline, ensemble
        )
        row = {
            "v3_threshold": args.baseline_confidence,
            "v7_addition_threshold": threshold,
            "approved": totals.get("approved", 0),
            "v3_matches": totals.get("baseline_matches", 0),
            "ensemble_matches": totals.get("candidate_matches", 0),
            "fixes": totals.get("fixed", 0),
            "regressions": totals.get("regression", 0),
            "missing_both": totals.get("missing", 0),
            "ensemble_extras": totals.get("candidate_extras", 0),
            "box_reviews": totals.get("box_review", 0),
            "eligible_for_visual_review": (
                totals.get("regression", 0) == 0
                and totals.get("candidate_extras", 0) == 0
                and totals.get("candidate_matches", 0)
                > totals.get("baseline_matches", 0)
            ),
        }
        rows.append(row)
        details[f"{threshold:.2f}"] = {
            "summary": totals,
            "class_summary": classes,
            "issues": issues,
        }

    with (output / "ensemble_sweep.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "ensemble_sweep.json").write_text(
        json.dumps(
            {
                "status": "review_only_production_unchanged",
                "baseline_preserved": True,
                "duplicate_iou": args.duplicate_iou,
                "rows": rows,
                "details": details,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    eligible = [row for row in rows if row["eligible_for_visual_review"]]
    lines = [
        "# Baseline-preserving V3 plus V7 ensemble sweep",
        "",
        "Production was not changed.",
        "",
        "| V7 add threshold | V3 matches | Ensemble matches | Fixes | Regressions | Extras | Review eligible |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['v7_addition_threshold']:.2f} | {row['v3_matches']} | "
            f"{row['ensemble_matches']} | {row['fixes']} | "
            f"{row['regressions']} | {row['ensemble_extras']} | "
            f"{'YES' if row['eligible_for_visual_review'] else 'NO'} |"
        )
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output_root": str(output), "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
