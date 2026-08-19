import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import cv2


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "code"))

from auto_ballooning import (  # noqa: E402
    draw_balloons,
    parse_tolerance,
    save_fa_workbook,
    save_pdf_from_image,
)
from drawing_metadata import DrawingMetadata  # noqa: E402


EXPECTED_DRAWING_NUMBER = "W3-C111265901-03"


def balloon_text(row):
    return str(row.get("Balloon No", "")).strip()


def main_balloon(row):
    return balloon_text(row).split(".", 1)[0]


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
            "Operation": "Dimensional",
            "Equipment": "DC",
            "Review Reason": "",
        }
    )
    return row


def set_depth(row, value):
    row = set_plain_dimension(row, value)
    row.update(
        {
            "Dimension": f"DEPTH {value}",
            "Specification": f"DEPTH {value}",
            "Measurement Type": "hole_callout",
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


def set_counterbore(row, value):
    row = set_plain_dimension(row, value)
    row.update(
        {
            "Symbol": "CBORE",
            "Report Symbol": "CBORE",
            "Specification": f"CBORE{value}",
            "Measurement Type": "hole_callout",
        }
    )
    return row


def set_frame(row, x, y, width, height):
    row.update(
        {
            "X": int(x),
            "Y": int(y),
            "Width": int(width),
            "Height": int(height),
            "Manual Crop": "YES",
        }
    )
    return row


def add_frame_margin(row, image_width, image_height, pad=8):
    if str(row.get("Manual Crop", "")).strip().upper() == "YES":
        return row
    x = int(row.get("X", 0) or 0)
    y = int(row.get("Y", 0) or 0)
    width = int(row.get("Width", 0) or 0)
    height = int(row.get("Height", 0) or 0)
    if width <= 0 or height <= 0 or width > 360 or height > 160:
        return row
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(image_width - 1, x + width + pad)
    y2 = min(image_height - 1, y + height + pad)
    return set_frame(row, x1, y1, x2 - x1, y2 - y1)


def make_six_hole_rows(template):
    rows = []
    for index in range(1, 7):
        row = set_plain_dimension(deepcopy(template), "5.6")
        row.update(
            {
                "Symbol": "6X" if index == 1 else "",
                "Report Symbol": "6X" if index == 1 else "",
                "Specification": "6X 5.6 THRU",
                "Measurement Type": "hole_callout",
                "Multiplier Count": 6,
                "Multiplier Index": index,
                "Subrow Count": 1,
                "Subrow Index": "",
            }
        )
        set_frame(row, 2376, 2544, 180, 38)
        rows.append(row)
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

    # Keep the higher-quality complete detection for each duplicate pair.
    delete_main_balloons = {"20", "27", "46", "67", "72", "79"}
    grouped_rows = []
    image_height, image_width = original_image.shape[:2]

    for source_row in snapshot.get("original_items", []):
        row = deepcopy(source_row)
        balloon = main_balloon(row)
        if balloon in delete_main_balloons:
            continue

        # The section dimension sits before its associated GD&T frame.
        if balloon == "28":
            missing_one = set_plain_dimension(deepcopy(row), "1")
            set_frame(missing_one, 798, 1227, 34, 54)
            grouped_rows.append(("missing-section-dimension-1", missing_one))

        gdt_values = {
            "2": ("//", "0.05 Z"),
            "18": ("//", "0.05 Z"),
            "28": ("⊥", "0.01 Z"),
            "43": ("⊥", "0.01 Z"),
            "76": ("//", "0.01 Z"),
        }
        if balloon in gdt_values:
            symbol, value = gdt_values[balloon]
            row = set_gdt(row, symbol, value)

        # Keep each English thread and drill-depth line in its own frame.
        if balloon == "12":
            set_frame(row, 3071, 546, 176, 31)
        elif balloon == "13":
            set_frame(row, 3071, 509, 352, 37)
        elif balloon == "21":
            set_frame(row, 1478, 954, 178, 31)
        elif balloon == "22":
            set_frame(row, 1477, 917, 353, 37)
        elif balloon == "65":
            set_frame(row, 1585, 2174, 162, 31)
        elif balloon == "66":
            set_frame(row, 1582, 2137, 354, 37)
        elif balloon == "70":
            set_frame(row, 3293, 2274, 161, 31)
        elif balloon == "71":
            set_frame(row, 3293, 2237, 352, 37)
        elif balloon == "73":
            set_frame(row, 3974, 2277, 176, 31)
        elif balloon == "74":
            set_frame(row, 3974, 2240, 352, 37)
        elif balloon == "80":
            set_frame(row, 1363, 2542, 353, 44)

        if balloon == "81":
            for hole_row in make_six_hole_rows(row):
                grouped_rows.append(("compound-81-hole", hole_row))

            counterbore = set_counterbore(deepcopy(row), "12")
            set_frame(counterbore, 2376, 2582, 140, 38)
            grouped_rows.append(("compound-81-counterbore", counterbore))

            depth = set_depth(deepcopy(row), "10")
            set_frame(depth, 2518, 2582, 80, 38)
            grouped_rows.append(("compound-81-depth", depth))
            continue

        row = add_frame_margin(row, image_width, image_height)

        # Keep the angled 11 box separate from the adjacent dimension 10.
        if balloon == "69":
            set_frame(row, 2580, 2279, 58, 46)

        grouped_rows.append((balloon, row))

        if balloon == "42":
            missing_rotated_one = set_plain_dimension(deepcopy(row), "1")
            set_frame(missing_rotated_one, 2842, 1665, 52, 30)
            grouped_rows.append(("missing-rotated-dimension-1", missing_rotated_one))

        if balloon == "48":
            missing_nine = set_plain_dimension(deepcopy(row), "9")
            set_frame(missing_nine, 1629, 1730, 39, 36)
            grouped_rows.append(("missing-vertical-dimension-9", missing_nine))

        if balloon == "63":
            missing_six = set_plain_dimension(deepcopy(row), "6")
            set_frame(missing_six, 3372, 2043, 47, 39)
            grouped_rows.append(("missing-vertical-dimension-6", missing_six))

        if balloon == "60":
            missing_section_one = set_plain_dimension(deepcopy(row), "1")
            set_frame(missing_section_one, 408, 2151, 40, 32)
            grouped_rows.append(("missing-section-b-dimension-1", missing_section_one))

        if balloon == "11":
            missing_five = set_plain_dimension(deepcopy(row), "5")
            set_frame(missing_five, 2881, 544, 44, 53)
            grouped_rows.append(("missing-dimension-5", missing_five))

        if balloon == "17":
            missing_eight = set_plain_dimension(deepcopy(row), "8")
            set_frame(missing_eight, 3288, 841, 54, 48)
            grouped_rows.append(("missing-dimension-8", missing_eight))

        if balloon_text(source_row) == "80.2":
            missing_depth_fifteen = set_depth(deepcopy(row), "15")
            set_frame(missing_depth_fifteen, 1365, 2586, 176, 40)
            grouped_rows.append(("missing-bottom-depth-15", missing_depth_fifteen))

    return renumber_grouped_rows(grouped_rows)


def main():
    parser = argparse.ArgumentParser(description="Build the reviewed Golden Drawing 4 candidate outputs.")
    parser.add_argument("--job-id", default="3c8d91feac19")
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
    metadata_values = deepcopy(snapshot.get("original_metadata", {}))
    metadata_values["part_name"] = "PLATE, LTP4, BASE, (1)"
    metadata = DrawingMetadata(**metadata_values)
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
            "corrected_gdt_frames": 5,
            "removed_partial_or_duplicate_callouts": 5,
            "removed_note_false_positive": 1,
            "recovered_missing_dimensions": 7,
            "removed_drawing_line_false_positives": 3,
            "separated_overlapping_callout_frames": 5,
            "recovered_missing_depth_callouts": 1,
            "split_compound_hole_callout": 3,
            "expanded_tight_characteristic_frames": True,
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
