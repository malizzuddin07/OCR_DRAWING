"""Build a human-review preview for detector hard examples from an issue map."""

from __future__ import annotations

import argparse
import csv
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

EXPECTED_TYPE_TO_CLASS = {
    "plain_dimension": "dimension",
    "reference_dimension": "dimension",
    "thickness": "dimension",
    "diameter": "diameter",
    "radius": "radius",
    "chamfer": "chamfer_callout",
    "metric_thread": "thread_callout",
    "hole_callout": "hole_callout",
    "surface_finish": "surface_finish",
    "gdt": "gdt_frame",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest_rows(path: Path, drawing: str):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [row for row in rows if row["Drawing"] == drawing]


def find_approved_label(rows, issue):
    expected_balloon = str(issue["Expected Balloon"]).strip()
    matches = [row for row in rows if str(row["Balloons"]).strip() == expected_balloon]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one approved label for balloon {expected_balloon}, "
            f"found {len(matches)}"
        )
    label = matches[0]
    expected_class = EXPECTED_TYPE_TO_CLASS.get(str(issue["Expected Type"]))
    if expected_class is None:
        raise ValueError(f"Unsupported expected type: {issue['Expected Type']}")
    if label["Class"] != expected_class:
        raise ValueError(
            f"Balloon {expected_balloon}: issue expects {expected_class}, "
            f"approved label is {label['Class']}"
        )
    return label


def build_hard_labels(issue_payload, manifest_rows, drawing):
    result = next(
        (item for item in issue_payload["results"] if item["drawing"] == drawing),
        None,
    )
    if result is None:
        raise ValueError(f"Issue report does not contain {drawing}")

    hard_issues = [
        issue
        for issue in result["issues"]
        if issue["Issue"] in {"MISSING", "INCORRECT"}
    ]
    labels = []
    seen = set()
    for index, issue in enumerate(hard_issues, start=1):
        approved = find_approved_label(manifest_rows, issue)
        balloon = str(approved["Balloons"]).strip()
        if balloon in seen:
            raise ValueError(f"Duplicate hard-example balloon: {balloon}")
        seen.add(balloon)
        labels.append(
            {
                "hard_id": f"H{index:02d}",
                "drawing": drawing,
                "issue": issue["Issue"],
                "severity": issue["Severity"],
                "class_name": approved["Class"],
                "balloons": balloon,
                "expected_value": issue["Expected Value"],
                "box": [
                    float(approved["X"]),
                    float(approved["Y"]),
                    float(approved["Width"]),
                    float(approved["Height"]),
                ],
                "source": "approved_detector_dataset_manifest",
            }
        )
    return labels


def validate_labels(labels, image):
    for label in labels:
        x, y, width, height = label["box"]
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid box: {label}")
        if x < 0 or y < 0 or x + width > image.shape[1] or y + height > image.shape[0]:
            raise ValueError(f"Out-of-bounds box: {label}")
        if label["class_name"] not in CLASS_COLORS:
            raise ValueError(f"Unsupported class: {label['class_name']}")


def draw_preview(image, labels):
    preview = image.copy()
    thickness = max(2, round(max(image.shape[:2]) / 2200))
    font_scale = max(0.55, max(image.shape[:2]) / 7800)
    for label in labels:
        x, y, width, height = (round(value) for value in label["box"])
        color = CLASS_COLORS[label["class_name"]]
        cv2.rectangle(preview, (x, y), (x + width, y + height), color, thickness)
        tag = f"{label['hard_id']} B{label['balloons']}"
        (text_width, text_height), baseline = cv2.getTextSize(
            tag,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness,
        )
        tag_x = x
        tag_y = max(text_height + baseline + 4, y - 4)
        cv2.rectangle(
            preview,
            (tag_x, tag_y - text_height - baseline - 4),
            (tag_x + text_width + 8, tag_y + 3),
            color,
            -1,
        )
        cv2.putText(
            preview,
            tag,
            (tag_x + 4, tag_y - baseline),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
    return preview


def build_review(
    issue_report: Path,
    labels_manifest: Path,
    image_path: Path,
    full_approved_preview: Path,
    drawing: str,
    output_dir: Path,
):
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {output_dir}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)

    issue_payload = load_json(issue_report)
    manifest_rows = load_manifest_rows(labels_manifest, drawing)
    hard_labels = build_hard_labels(issue_payload, manifest_rows, drawing)
    validate_labels(hard_labels, image)
    if len(hard_labels) != 20:
        raise ValueError(f"Expected 20 confirmed hard examples, found {len(hard_labels)}")

    output_dir.mkdir(parents=True)
    focused_preview = output_dir / f"{drawing}_hard_labels.png"
    if not cv2.imwrite(str(focused_preview), draw_preview(image, hard_labels)):
        raise OSError(f"Could not write {focused_preview}")

    all_labels_preview = output_dir / f"{drawing}_all_approved_labels.png"
    shutil.copy2(full_approved_preview, all_labels_preview)

    labels_path = output_dir / f"{drawing}_hard_labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "human_visual_review_required",
                "training_allowed": False,
                "production_model_change_authorized": False,
                "drawing": drawing,
                "label_count": len(hard_labels),
                "missing_issue_labels": sum(
                    item["issue"] == "MISSING" for item in hard_labels
                ),
                "incorrect_issue_labels": sum(
                    item["issue"] == "INCORRECT" for item in hard_labels
                ),
                "labels": hard_labels,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    instructions = output_dir / "REVIEW_INSTRUCTIONS.md"
    instructions.write_text(
        f"""# {drawing} hard-example label review

Review `{focused_preview.name}` first.

- Confirm every coloured box tightly contains the complete dimension or callout.
- Confirm no box contains drawing lines, revision triangles, notes, or duplicate Japanese text.
- Confirm H01-H20 are all required.
- The full approved reference is `{all_labels_preview.name}`.

Nothing in this folder is approved for training yet.
Reply with corrections, or reply: `Hard-example labels approved.`
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "status": "human_visual_review_required",
        "training_allowed": False,
        "production_model_change_authorized": False,
        "drawing": drawing,
        "hard_label_count": len(hard_labels),
        "focused_preview": focused_preview.name,
        "full_approved_preview": all_labels_preview.name,
        "labels": labels_path.name,
        "instructions": instructions.name,
        "source_issue_report": str(issue_report),
        "source_labels_manifest": str(labels_manifest),
    }
    (output_dir / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-report", required=True, type=Path)
    parser.add_argument("--labels-manifest", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--full-approved-preview", required=True, type=Path)
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_review(
        args.issue_report.resolve(),
        args.labels_manifest.resolve(),
        args.image.resolve(),
        args.full_approved_preview.resolve(),
        args.drawing,
        args.output_dir.resolve(),
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
