"""Draw only newly recovered boxes from a cached ensemble sweep report."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path


def load_comparator(path: Path):
    spec = importlib.util.spec_from_file_location("detector_compare", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--comparator", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.50)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    comparator = load_comparator(args.comparator.resolve())
    report = json.loads(args.report.read_text(encoding="utf-8"))
    key = f"{args.threshold:.2f}"
    if key not in report.get("details", {}):
        raise KeyError(f"Threshold {key} is absent from the ensemble report")
    issues = report["details"][key]["issues"]
    output = args.output_root.resolve()
    map_dir = output / "review_maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    fix_count = 0
    for drawing, drawing_issues in sorted(issues.items()):
        fixes = [dict(issue) for issue in drawing_issues if issue["type"] == "fixed"]
        if not fixes:
            continue
        preview = args.dataset.resolve() / "previews" / f"{drawing}_labels.png"
        destination = map_dir / f"{drawing}_v3_v7_new_boxes.png"
        comparator.draw_issue_map(preview, destination, fixes)
        fix_count += len(fixes)
        for issue in fixes:
            rows.append(
                {
                    "Drawing": drawing,
                    "Review ID": issue["review_id"],
                    "Class": issue["class_name"],
                    "Approved Label": issue["label_id"],
                    "Candidate IoU": round(float(issue["candidate_iou"]), 4),
                    "Box": json.dumps([round(float(value), 2) for value in issue["box"]]),
                }
            )
    if fix_count == 0:
        raise ValueError("No newly recovered boxes were found")
    with (output / "NEW_BOXES_TO_REVIEW.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "HOW_TO_REVIEW.md").write_text(
        "# V3 plus V7 new-box review\n\n"
        f"Threshold: V3 0.60 plus V7 {args.threshold:.2f}.\n\n"
        "Only green FIXED boxes are shown. Check that every box contains one "
        "complete required dimension, is tight enough to avoid overlap, and is "
        "not drawing geometry or note text.\n\n"
        "Production has not changed.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_root": str(output),
                "fix_count": fix_count,
                "map_count": len(list(map_dir.glob("*.png"))),
                "production_changed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
