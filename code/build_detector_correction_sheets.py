"""Build compact correction sheets from an unapproved detector review batch.

The generated sheets never approve labels. They reduce the human review work
to suspicious proposals plus zoomed page tiles for finding missed boxes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import textwrap
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


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

SCARCE_CLASSES = {"diameter", "surface_finish", "gdt_frame"}
CALL_OUT_CLASSES = {"thread_callout", "hole_callout"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def box_key(box):
    return tuple(round(float(value), 2) for value in box)


def item_box(row):
    return (
        float(row["X"]),
        float(row["Y"]),
        float(row["Width"]),
        float(row["Height"]),
    )


def box_iou(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def proposal_risks(proposal, rows, proposals):
    reasons = []
    class_name = proposal["class_name"]
    box = tuple(proposal["box"])
    if class_name in SCARCE_CLASSES:
        reasons.append("scarce class - verify class and complete box")
    if class_name in CALL_OUT_CLASSES:
        reasons.append("verify English callout only; exclude duplicate Japanese text")
    if any(clean(row.get("Needs Review")).upper() == "YES" for row in rows):
        reasons.append("OCR marked needs review")
    confidence = [float(row.get("AI Confidence", 1.0) or 0.0) for row in rows]
    if confidence and min(confidence) < 0.75:
        reasons.append("low OCR confidence")
    _, _, width, height = box
    if width > 900 or height > 600 or width * height > 400_000:
        reasons.append("large box - verify it is not covering notes")
    overlaps = [
        int(other["proposal_id"])
        for other in proposals
        if other["proposal_id"] != proposal["proposal_id"]
        and box_iou(box, tuple(other["box"])) >= 0.12
    ]
    if overlaps:
        reasons.append("overlaps proposal " + ", ".join(map(str, overlaps)))
    return reasons


def fit_image(image, width, height):
    if image.size == 0:
        return np.full((height, width, 3), 245, dtype=np.uint8)
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def crop_with_box(image, box, padding=90):
    x, y, width, height = map(float, box)
    x1 = max(0, int(math.floor(x - padding)))
    y1 = max(0, int(math.floor(y - padding)))
    x2 = min(image.shape[1], int(math.ceil(x + width + padding)))
    y2 = min(image.shape[0], int(math.ceil(y + height + padding)))
    crop = image[y1:y2, x1:x2].copy()
    color = (0, 80, 255)
    cv2.rectangle(
        crop,
        (max(0, round(x - x1)), max(0, round(y - y1))),
        (min(crop.shape[1] - 1, round(x + width - x1)), min(crop.shape[0] - 1, round(y + height - y1))),
        color,
        max(3, round(max(image.shape[:2]) / 1800)),
    )
    return crop


def draw_text(canvas, text, origin, scale=0.48, color=(20, 20, 20), thickness=1):
    x, y = origin
    cv2.putText(canvas, clean(text), (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def make_review_cards(drawing, image, records, output_dir):
    columns, rows_per_sheet = 3, 4
    card_width, card_height = 600, 330
    margin, title_height = 30, 70
    per_sheet = columns * rows_per_sheet
    files = []
    for sheet_index, start in enumerate(range(0, len(records), per_sheet), start=1):
        subset = records[start : start + per_sheet]
        canvas = np.full(
            (title_height + rows_per_sheet * card_height + margin, columns * card_width + margin * 2, 3),
            255,
            dtype=np.uint8,
        )
        draw_text(canvas, f"{drawing} - correction checks {sheet_index}", (margin, 35), 0.8, thickness=2)
        draw_text(canvas, "Orange box = current proposal. Write KEEP, FIX, or DELETE in the review CSV.", (margin, 60), 0.52)
        for local_index, record in enumerate(subset):
            row, column = divmod(local_index, columns)
            x0 = margin + column * card_width
            y0 = title_height + row * card_height
            cv2.rectangle(canvas, (x0, y0), (x0 + card_width - 8, y0 + card_height - 8), (190, 190, 190), 1)
            header = f"ID {record['proposal_id']} | {record['class_name']} | balloons {record['balloons']}"
            draw_text(canvas, header, (x0 + 10, y0 + 24), 0.5, thickness=1)
            crop = crop_with_box(image, record["box"])
            fitted = fit_image(crop, card_width - 28, 205)
            canvas[y0 + 34 : y0 + 239, x0 + 10 : x0 + card_width - 18] = fitted
            specification = " | ".join(record["specifications"]) or "(no OCR value)"
            draw_text(canvas, "Value: " + specification[:82], (x0 + 10, y0 + 262), 0.44)
            reason_lines = textwrap.wrap("; ".join(record["risk_reasons"]), width=72)[:2]
            for line_index, line in enumerate(reason_lines):
                draw_text(canvas, line, (x0 + 10, y0 + 286 + line_index * 19), 0.40, (0, 0, 170))
        output_path = output_dir / f"{drawing}_corrections_{sheet_index:02d}.png"
        if not cv2.imwrite(str(output_path), canvas):
            raise OSError(f"Could not write {output_path}")
        files.append(output_path.name)
    return files


def make_missing_tiles(drawing, image, proposals, output_dir):
    rows, columns = 2, 3
    tile_width, tile_height = 900, 700
    files = []
    overview_tiles = []
    page = image.copy()
    thickness = max(2, round(max(image.shape[:2]) / 2400))
    for proposal in proposals:
        x, y, width, height = map(int, map(round, proposal["box"]))
        color = CLASS_COLORS.get(proposal["class_name"], (0, 120, 255))
        cv2.rectangle(page, (x, y), (x + width, y + height), color, thickness)
        cv2.putText(
            page,
            str(proposal["proposal_id"]),
            (x, max(18, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.45, max(image.shape[:2]) / 9000),
            color,
            thickness,
            cv2.LINE_AA,
        )
    height, width = page.shape[:2]
    for row in range(rows):
        for column in range(columns):
            x1 = round(column * width / columns)
            x2 = round((column + 1) * width / columns)
            y1 = round(row * height / rows)
            y2 = round((row + 1) * height / rows)
            tile = fit_image(page[y1:y2, x1:x2], tile_width, tile_height)
            header = np.full((55, tile_width, 3), 255, dtype=np.uint8)
            draw_text(
                header,
                f"{drawing} - missing-box check R{row + 1} C{column + 1}",
                (15, 25),
                0.58,
                thickness=1,
            )
            draw_text(header, "Find dimensions or GD&T with no colored box.", (15, 48), 0.48, (0, 0, 180))
            output = np.vstack([header, tile])
            overview_tiles.append(output)
            output_path = output_dir / f"{drawing}_missing_R{row + 1}C{column + 1}.png"
            if not cv2.imwrite(str(output_path), output):
                raise OSError(f"Could not write {output_path}")
            files.append(output_path.name)
    overview = np.vstack(
        [
            np.hstack(overview_tiles[0:3]),
            np.hstack(overview_tiles[3:6]),
        ]
    )
    overview_path = output_dir / f"{drawing}_missing_overview.png"
    if not cv2.imwrite(str(overview_path), overview):
        raise OSError(f"Could not write {overview_path}")
    return files, overview_path.name


def build_batch(batch_root: Path, output_dir: Path):
    status = load_json(batch_root / "batch_status.json")
    if status.get("status") != "complete":
        raise ValueError("Review batch must be complete before building correction sheets.")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "source_batch": str(batch_root),
        "status": "human_review_required",
        "training_allowed": False,
        "drawings": [],
    }
    csv_rows = []
    for entry in status["drawings"]:
        drawing = entry["drawing"]
        drawing_dir = batch_root / drawing
        image = cv2.imread(str(drawing_dir / "original.png"))
        if image is None:
            raise FileNotFoundError(drawing_dir / "original.png")
        payload = load_json(drawing_dir / "label_proposals.json")
        proposals = payload["proposals"]
        characteristic_rows = load_json(drawing_dir / "characteristics.json")
        by_box = defaultdict(list)
        for row in characteristic_rows:
            by_box[box_key(item_box(row))].append(row)
        flagged = []
        for proposal in proposals:
            rows = by_box.get(box_key(proposal["box"]), [])
            reasons = proposal_risks(proposal, rows, proposals)
            if not reasons:
                continue
            specifications = [clean(row.get("Specification")) for row in rows if clean(row.get("Specification"))]
            record = {
                "drawing": drawing,
                "proposal_id": int(proposal["proposal_id"]),
                "class_name": proposal["class_name"],
                "balloons": ", ".join(map(str, proposal.get("balloon_numbers", []))),
                "box": proposal["box"],
                "specifications": specifications,
                "risk_reasons": reasons,
            }
            flagged.append(record)
            csv_rows.append(
                {
                    "Drawing": drawing,
                    "Proposal ID": record["proposal_id"],
                    "Class": record["class_name"],
                    "Balloons": record["balloons"],
                    "Specification": " | ".join(specifications),
                    "Why Check": "; ".join(reasons),
                    "Decision (KEEP/FIX/DELETE)": "",
                    "Correct Class": "",
                    "Correct Box or Notes": "",
                }
            )
        drawing_output = output_dir / drawing
        drawing_output.mkdir(parents=True, exist_ok=True)
        correction_files = make_review_cards(drawing, image, flagged, drawing_output)
        missing_files, missing_overview = make_missing_tiles(drawing, image, proposals, drawing_output)
        summary["drawings"].append(
            {
                "drawing": drawing,
                "proposal_count": len(proposals),
                "flagged_count": len(flagged),
                "correction_sheets": correction_files,
                "missing_box_overview": missing_overview,
                "missing_box_tiles": missing_files,
            }
        )
    csv_path = output_dir / "correction_decisions.csv"
    fieldnames = list(csv_rows[0]) if csv_rows else [
        "Drawing",
        "Proposal ID",
        "Class",
        "Balloons",
        "Specification",
        "Why Check",
        "Decision (KEEP/FIX/DELETE)",
        "Correct Class",
        "Correct Box or Notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    (output_dir / "correction_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    readme = [
        "# Detector correction sheets",
        "",
        "Status: HUMAN REVIEW REQUIRED. These files are not training labels.",
        "",
        "1. Open each `*_corrections_*.png` sheet and check only the listed boxes.",
        "2. Open each `*_missing_overview.png` and look for a dimension or GD&T frame with no colored box.",
        "3. Record KEEP, FIX, or DELETE in `correction_decisions.csv`.",
        "4. Put missing-box descriptions in the last CSV column or send screenshots.",
        "5. Do not retrain until the corrected labels are rebuilt and validated.",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = build_batch(args.batch_root.resolve(), args.output_dir.resolve())
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
