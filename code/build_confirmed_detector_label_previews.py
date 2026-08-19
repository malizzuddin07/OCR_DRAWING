"""Build Stage 2 detector label previews from human-confirmed Stage 1 findings."""

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


def normalized_box(box):
    values = tuple(round(float(value), 2) for value in box)
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        raise ValueError(f"Invalid box: {box}")
    return values


def apply_corrections(proposals, drawing_plan):
    by_id = {int(item["proposal_id"]): dict(item) for item in proposals}
    affected = set()
    delete_ids = {int(value) for value in drawing_plan.get("delete_ids", [])}
    affected.update(delete_ids)

    corrected = []
    for index, replacement in enumerate(drawing_plan.get("replace", []), start=1):
        source_ids = {int(value) for value in replacement["source_ids"]}
        missing = source_ids - set(by_id)
        if missing:
            raise KeyError(f"Replacement refers to missing proposal IDs: {sorted(missing)}")
        overlap = affected & source_ids
        if overlap:
            raise ValueError(f"Proposal IDs have more than one correction: {sorted(overlap)}")
        affected.update(source_ids)
        item = {
            "label_id": f"R{index}",
            "class_name": replacement["class_name"],
            "box": normalized_box(replacement["box"]),
            "source": "human_confirmed_replacement",
            "source_proposal_ids": sorted(source_ids),
            "reason": replacement["reason"],
        }
        for key in ("expected_text", "sub_balloon", "source_language", "use_as_fallback"):
            if key in replacement:
                item[key] = replacement[key]
        corrected.append(item)

    kept = []
    for proposal_id, proposal in sorted(by_id.items()):
        if proposal_id in affected:
            continue
        kept.append(
            {
                "label_id": f"P{proposal_id}",
                "class_name": proposal["class_name"],
                "box": normalized_box(proposal["box"]),
                "source": "confirmed_current_proposal",
                "source_proposal_ids": [proposal_id],
                "reason": "No Stage 1 issue found",
            }
        )

    additions = []
    for index, addition in enumerate(drawing_plan.get("add", []), start=1):
        item = {
            "label_id": f"A{index}",
            "class_name": addition["class_name"],
            "box": normalized_box(addition["box"]),
            "source": "human_confirmed_missing_addition",
            "source_proposal_ids": [],
            "reason": addition["reason"],
        }
        for key in ("expected_text", "sub_balloon", "source_language", "use_as_fallback"):
            if key in addition:
                item[key] = addition[key]
        additions.append(item)
    return kept + corrected + additions


def validate_labels(labels, image, drawing):
    seen_boxes = set()
    for label in labels:
        if label["class_name"] not in CLASS_COLORS:
            raise ValueError(f"{drawing}: unsupported class {label['class_name']}")
        x, y, width, height = label["box"]
        if x < 0 or y < 0 or x + width > image.shape[1] or y + height > image.shape[0]:
            raise ValueError(f"{drawing}: out-of-bounds box {label['box']}")
        box_key = tuple(label["box"])
        if box_key in seen_boxes:
            raise ValueError(f"{drawing}: duplicate box {box_key}")
        seen_boxes.add(box_key)


def draw_preview(image, labels):
    preview = image.copy()
    thickness = max(2, round(max(image.shape[:2]) / 2200))
    for label in labels:
        x, y, width, height = (round(value) for value in label["box"])
        color = CLASS_COLORS[label["class_name"]]
        cv2.rectangle(preview, (x, y), (x + width, y + height), color, thickness)
    return preview


def build_previews(batch_root: Path, plan_path: Path, approval_path: Path, output_dir: Path):
    approval = load_json(approval_path)
    if approval.get("status") != "stage_1_issues_human_approved":
        raise ValueError("Stage 1 has not been explicitly approved")
    if approval.get("training_allowed") is not False:
        raise ValueError("Stage 1 approval must not authorize training")

    batch = load_json(batch_root / "batch_status.json")
    plan = load_json(plan_path)
    batch_drawings = {entry["drawing"] for entry in batch["drawings"]}
    if set(plan["drawings"]) != set(approval["scope"]):
        raise ValueError("Correction-plan drawings do not match Stage 1 approval scope")
    if set(plan["drawings"]) - batch_drawings:
        raise ValueError("Correction plan contains drawings outside the source batch")

    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for drawing in approval["scope"]:
        source_dir = batch_root / drawing
        image = cv2.imread(str(source_dir / "original.png"))
        if image is None:
            raise FileNotFoundError(source_dir / "original.png")
        payload = load_json(source_dir / "label_proposals.json")
        labels = apply_corrections(payload["proposals"], plan["drawings"][drawing])
        validate_labels(labels, image, drawing)

        preview_path = output_dir / f"{drawing}_labels.png"
        preview = draw_preview(image, labels)
        if not cv2.imwrite(str(preview_path), preview):
            raise OSError(f"Could not write {preview_path}")
        labels_path = output_dir / f"{drawing}_corrected_labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "drawing": drawing,
                    "status": "stage_2_human_visual_review_required",
                    "training_allowed": False,
                    "labels": labels,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        summaries.append(
            {
                "drawing": drawing,
                "label_count": len(labels),
                "kept_count": sum(item["source"] == "confirmed_current_proposal" for item in labels),
                "replacement_count": sum(item["source"] == "human_confirmed_replacement" for item in labels),
                "addition_count": sum(item["source"] == "human_confirmed_missing_addition" for item in labels),
                "preview": preview_path.name,
                "labels": labels_path.name,
            }
        )

    manifest = {
        "schema_version": 1,
        "status": "stage_2_labels_human_visual_review_required",
        "review_stage": 2,
        "training_allowed": False,
        "production_model_change_authorized": False,
        "stage_1_approval": str(approval_path),
        "correction_plan": str(plan_path),
        "source_batch": str(batch_root),
        "drawings": summaries,
    }
    (output_dir / "stage_2_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_previews(
        args.batch_root.resolve(),
        args.plan.resolve(),
        args.approval.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
