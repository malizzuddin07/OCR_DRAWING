"""Build draft full-page MISSING/WRONG/EXTRA detector issue previews.

Proposal-based issues use exact current boxes. Possible missing regions are
human-review hints, not approved ground truth, and are labeled accordingly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


COLORS = {
    "missing": (0, 0, 255),
    "wrong": (0, 165, 255),
    "extra": (255, 0, 255),
    "check": (255, 180, 0),
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def integer_box(box, image):
    x, y, width, height = (round(float(value)) for value in box)
    x = max(0, min(image.shape[1] - 1, x))
    y = max(0, min(image.shape[0] - 1, y))
    width = max(1, min(image.shape[1] - x, width))
    height = max(1, min(image.shape[0] - y, height))
    return x, y, width, height


def draw_issue(image, box, issue_type, label):
    color = COLORS[issue_type]
    x, y, width, height = integer_box(box, image)
    max_side = max(image.shape[:2])
    thickness = max(4, round(max_side / 1500))
    font_scale = max(0.7, max_side / 6500)
    font_thickness = max(2, round(thickness * 0.75))
    cv2.rectangle(image, (x, y), (x + width, y + height), color, thickness)
    (text_width, text_height), baseline = cv2.getTextSize(
        label,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        font_thickness,
    )
    padding = max(5, thickness)
    label_width = text_width + padding * 2
    label_height = text_height + baseline + padding * 2
    label_x = max(0, min(image.shape[1] - label_width, x))
    label_y2 = max(label_height, y - max(2, thickness))
    label_y1 = label_y2 - label_height
    if label_y2 > y and y + height + label_height < image.shape[0]:
        label_y1 = y + height + max(2, thickness)
        label_y2 = label_y1 + label_height
    cv2.rectangle(
        image,
        (label_x, label_y1),
        (label_x + label_width, label_y2),
        color,
        -1,
    )
    cv2.putText(
        image,
        label,
        (label_x + padding, label_y2 - baseline - padding),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        font_thickness,
        cv2.LINE_AA,
    )


def build_issue_previews(batch_root: Path, plan_path: Path, output_dir: Path):
    status = load_json(batch_root / "batch_status.json")
    plan = load_json(plan_path)
    entries = {entry["drawing"]: entry for entry in status["drawings"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for drawing, drawing_plan in plan["drawings"].items():
        if drawing not in entries:
            raise KeyError(f"Drawing is not in review batch: {drawing}")
        source_dir = batch_root / drawing
        image = cv2.imread(str(source_dir / "original.png"))
        if image is None:
            raise FileNotFoundError(source_dir / "original.png")
        proposal_payload = load_json(source_dir / "label_proposals.json")
        proposals = {
            int(proposal["proposal_id"]): proposal
            for proposal in proposal_payload["proposals"]
        }
        issue_count = 0
        for issue in drawing_plan.get("proposal_issues", []):
            proposal_id = int(issue["proposal_id"])
            if proposal_id not in proposals:
                raise KeyError(f"{drawing}: proposal ID {proposal_id} does not exist")
            issue_type = issue["type"]
            label = f"{issue_type.upper()} ID {proposal_id}"
            draw_issue(image, proposals[proposal_id]["box"], issue_type, label)
            issue_count += 1
        for index, issue in enumerate(drawing_plan.get("possible_missing", []), start=1):
            base_label = issue.get("label") or "POSSIBLE MISSING"
            review_id = issue.get("review_id") or f"M{index}"
            if drawing_plan.get("compact_labels"):
                label = f"MISSING {review_id}"
            else:
                label = f"{base_label} {review_id}"
            draw_issue(image, issue["box"], "missing", label)
            issue_count += 1
        output_path = output_dir / f"{drawing}_issues.png"
        if not cv2.imwrite(str(output_path), image):
            raise OSError(f"Could not write {output_path}")
        outputs.append(
            {
                "drawing": drawing,
                "issue_count": issue_count,
                "preview": output_path.name,
            }
        )
    manifest = {
        "schema_version": 1,
        "status": "stage_1_issues_human_confirmation_required",
        "review_stage": 1,
        "training_allowed": False,
        "stage_2_labels_allowed": False,
        "source_batch": str(batch_root),
        "issue_plan": str(plan_path),
        "drawings": outputs,
    }
    (output_dir / "draft_issue_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = build_issue_previews(
        args.batch_root.resolve(),
        args.plan.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
