import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

import cv2


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "code"))

from auto_ballooning import (  # noqa: E402
    draw_balloons,
    infer_gdt_frame_symbol,
    normalize_depth_display_text,
    parse_tolerance,
    save_fa_workbook,
    save_pdf_from_image,
)
from drawing_metadata import DrawingMetadata  # noqa: E402


EXPECTED_DRAWING_NUMBER = "W3-C111262801-2A"


def balloon_text(row):
    return str(row.get("Balloon No", "")).strip()


def set_depth(row, value):
    nominal, minus, plus, minimum, maximum = parse_tolerance(str(value), apply_general=True)
    row.update(
        {
            "Symbol": "",
            "Report Symbol": "",
            "Dimension": f"DEPTH {value}",
            "Specification": f"DEPTH {value}",
            "Nominal": nominal,
            "Tolerance -": minus,
            "Tolerance +": plus,
            "MIN": minimum,
            "MAX": maximum,
            "Measurement Type": "hole_callout",
            "Equipment": "DC",
            "Review Reason": "",
        }
    )
    return row


def set_plain_dimension(row, value):
    nominal, minus, plus, minimum, maximum = parse_tolerance(str(value), apply_general=True)
    row.update(
        {
            "Symbol": "",
            "Report Symbol": "",
            "Dimension": str(value),
            "Specification": str(value),
            "Nominal": nominal,
            "Tolerance -": minus,
            "Tolerance +": plus,
            "MIN": minimum,
            "MAX": maximum,
            "Measurement Type": "plain_dimension",
            "Review Reason": "",
        }
    )
    return row


def set_gdt(row, symbol, value):
    row.update(
        {
            "Symbol": symbol,
            "Report Symbol": symbol,
            "Dimension": value,
            "Specification": f"{symbol} {value}",
            "Nominal": value,
            "Tolerance -": "",
            "Tolerance +": "",
            "MIN": "",
            "MAX": "",
            "Measurement Type": "gdt",
            "Equipment": "V",
            "Review Reason": "",
        }
    )
    return row


def expand_radius(row, count):
    rows = []
    for index in range(1, count + 1):
        current = deepcopy(row)
        current["Symbol"] = f"{count}X R" if index == 1 else "R"
        current["Report Symbol"] = current["Symbol"]
        current["Multiplier Count"] = count
        current["Multiplier Index"] = index
        current["Review Reason"] = ""
        rows.append(current)
    return rows


def renumber_grouped_rows(grouped_rows):
    output = []
    next_main = 1
    index = 0
    while index < len(grouped_rows):
        group_key = grouped_rows[index][0]
        group = []
        while index < len(grouped_rows) and grouped_rows[index][0] == group_key:
            group.append(grouped_rows[index][1])
            index += 1

        for suffix, row in enumerate(group, start=1):
            row["Balloon No"] = str(next_main) if len(group) == 1 else f"{next_main}.{suffix}"
            row["Display Balloon No"] = str(next_main)
            row["Review Reason"] = ""
            output.append(row)
        next_main += 1
    return output


def build_candidate(snapshot, original_image):
    metadata = snapshot.get("original_metadata", {})
    if str(metadata.get("drawing_number", "")).strip() != EXPECTED_DRAWING_NUMBER:
        raise ValueError(
            f"This correction profile is only for {EXPECTED_DRAWING_NUMBER}; "
            f"received {metadata.get('drawing_number', '') or 'unknown'}."
        )

    delete_balloons = {"8", "21", "24", "31", "34", "36", "42", "44", "61"}
    grouped_rows = []
    missing_vertical_6 = None

    for source_row in snapshot.get("original_items", []):
        row = deepcopy(source_row)
        balloon = balloon_text(row)
        base_group = balloon.split(".", 1)[0]
        if balloon in delete_balloons:
            continue

        if balloon == "2":
            row = set_plain_dimension(row, "198.5")
            row.update(
                {
                    "X": 2095,
                    "Y": 387,
                    "Width": 115,
                    "Height": 38,
                    "Manual Crop": "YES",
                }
            )

        if balloon == "4":
            first = set_plain_dimension(deepcopy(row), "9.8")
            first.update(
                {
                    "X": 1952,
                    "Y": 464,
                    "Width": 62,
                    "Height": 36,
                    "Manual Crop": "YES",
                }
            )
            second = set_plain_dimension(deepcopy(row), "9.8")
            second.update(
                {
                    "X": 2027,
                    "Y": 464,
                    "Width": 62,
                    "Height": 36,
                    "Manual Crop": "YES",
                }
            )
            grouped_rows.append(("4-left", first))
            grouped_rows.append(("4-right", second))
            continue

        # The third vertical pitch dimension below the two 16 mm dimensions
        # was completely missed by OCR. Insert it directly after those related
        # dimensions so the final balloon order follows the drawing sequence.
        if balloon == "50":
            missing_vertical_6 = set_plain_dimension(deepcopy(row), "6")
            missing_vertical_6.update(
                {
                    "X": 3292,
                    "Y": 1895,
                    "Width": 55,
                    "Height": 75,
                    "Manual Crop": "YES",
                }
            )

        if balloon in {"41", "43", "45", "46", "54"}:
            row["Manual Crop"] = "YES"

        # Keep the full vertical surface-finish text inside the visible frame.
        # The detector boxes were correct, but the generic compact-frame logic
        # made these two callouts touch or cross the blue border.
        if balloon == "51":
            row.update(
                {
                    "X": 4125,
                    "Y": 1722,
                    "Width": 49,
                    "Height": 125,
                    "Manual Crop": "YES",
                }
            )

        if balloon == "74":
            row = set_plain_dimension(row, "191.5")
            row.update(
                {
                    "X": 2122,
                    "Y": 2438,
                    "Width": 114,
                    "Height": 42,
                    "Manual Crop": "YES",
                }
            )

        if balloon == "77":
            row.update(
                {
                    "X": 2975,
                    "Y": 2432,
                    "Width": 49,
                    "Height": 128,
                    "Manual Crop": "YES",
                }
            )

        if balloon == "53":
            row = set_plain_dimension(row, "66")

        if balloon in {"37", "55"}:
            for expanded in expand_radius(row, 2):
                grouped_rows.append((base_group, expanded))
            continue

        if balloon.startswith("62."):
            row.update(
                {
                    "X": 765,
                    "Y": 2323,
                    "Width": 336,
                    "Height": 34,
                    "Manual Crop": "YES",
                }
            )
            grouped_rows.append((base_group, row))
            if balloon == "62.4":
                depth_row = set_depth(deepcopy(row), "15")
                depth_row.update(
                    {
                        "X": 765,
                        "Y": 2356,
                        "Width": 162,
                        "Height": 28,
                        "Manual Crop": "YES",
                    }
                )
                grouped_rows.append(("62-english-depth", depth_row))
            continue

        display_value = normalize_depth_display_text(row.get("Dimension", ""))
        depth_match = re.search(r"DEPTH\s*(\d+(?:\.\d+)?)\b", display_value, re.IGNORECASE)
        if depth_match:
            row = set_depth(row, depth_match.group(1))

        if balloon == "35":
            row = set_gdt(row, "⊥", "0.1 Z")
        elif balloon == "70":
            row = set_gdt(row, "⊥", "0.1 Z")
        elif balloon == "78":
            row = set_gdt(row, "//", "0.05 Z")
        elif str(row.get("Report Symbol", "")) == "GD&T":
            inferred = infer_gdt_frame_symbol(original_image, row)
            if inferred:
                value = re.sub(r"(?<=\d)([XYZ])$", r" \1", str(row.get("Dimension", "")).strip())
                row = set_gdt(row, inferred, value)

        grouped_rows.append((base_group, row))
        if balloon == "50" and missing_vertical_6 is not None:
            grouped_rows.append(("missing-vertical-6", missing_vertical_6))

    return renumber_grouped_rows(grouped_rows)


def main():
    parser = argparse.ArgumentParser(description="Build the reviewed Golden Drawing 3 candidate outputs.")
    parser.add_argument("--job-id", default="94413779e086")
    args = parser.parse_args()

    job_id = str(args.job_id).strip()
    job_dir = BASE_DIR / "generated_jobs" / "jobs" / job_id
    snapshot_path = BASE_DIR / "private_data" / "job_snapshots" / f"{job_id}.json"
    original_path = job_dir / "original.png"
    if not snapshot_path.exists() or not original_path.exists():
        raise FileNotFoundError("The saved job snapshot or original image is missing.")

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    original_image = cv2.imread(str(original_path))
    if original_image is None:
        raise ValueError("Could not read the saved original drawing image.")

    corrected_items = build_candidate(snapshot, original_image)
    metadata = DrawingMetadata(**snapshot.get("original_metadata", {}))
    output_dir = job_dir / "golden_candidate"
    output_dir.mkdir(parents=True, exist_ok=True)

    image_path = output_dir / "ballooned_candidate.png"
    pdf_path = output_dir / "ballooned_candidate.pdf"
    excel_path = output_dir / "fa_inspection_report_candidate.xlsx"
    items_path = output_dir / "corrected_items.json"
    summary_path = output_dir / "candidate_summary.json"

    ballooned = draw_balloons(original_image, corrected_items, metadata)
    cv2.imwrite(str(image_path), ballooned)
    save_pdf_from_image(image_path, pdf_path)
    save_fa_workbook(corrected_items, excel_path, metadata=metadata)
    items_path.write_text(json.dumps(corrected_items, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "status": "candidate_not_approved",
        "job_id": job_id,
        "drawing_number": metadata.drawing_number,
        "characteristics": len(corrected_items),
        "main_balloons": len({str(row.get("Display Balloon No", "")) for row in corrected_items}),
        "automatic_corrections": {
            "removed_false_or_duplicate_rows": 9,
            "corrected_partial_198_5_dimension": True,
            "corrected_66_dimension": True,
            "recovered_missing_vertical_6_dimension": True,
            "split_repeated_9_8_dimensions": 2,
            "expanded_two_radius_callouts": 2,
            "corrected_gdt_frames": 4,
            "normalized_remaining_depth_callout": 1,
            "removed_customer_internal_remarks": True,
            "removed_generated_header_overlay": True,
        },
        "files": {
            "pdf": str(pdf_path),
            "excel": str(excel_path),
            "image": str(image_path),
            "items": str(items_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
