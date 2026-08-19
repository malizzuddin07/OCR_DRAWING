import argparse
import os
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATASET_IMAGES_DIR,
    DEBUG_MEASUREMENT_DETECTION_DIR,
    MEASUREMENT_DETECTION_OUTPUT_PATH,
    MEASUREMENT_OCR_CONFIDENCE,
    MEASUREMENT_REVIEW_THRESHOLD,
    ensure_directories,
)
from exporter import sanitize_dataframe_for_excel
from layout_regions import MEASUREMENT_EXCLUSION_REGIONS, exclusion_region_label
from vision_tools import create_paddle_ocr


MEASUREMENT_PATTERNS = [
    ("surface_finish", re.compile(r"\bR\s*a\s*[0-9]+(?:\.[0-9]+)?\b", re.IGNORECASE)),
    ("thickness", re.compile(r"\bt\s*[0-9]+(?:\.[0-9]+)?\b", re.IGNORECASE)),
    ("hole_callout", re.compile(r"(?:[Ø⌀]|DIA\.?|DIAMETER)?\s*[0-9]+(?:\.[0-9]+)?\s*(?:DEPTH|DP|深さ|深)\s*[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)),
    ("diameter", re.compile(r"(?:[Ø⌀φΦ]|DIA\.?|DIAMETER)\s*[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)),
    ("radius", re.compile(r"(?:[0-9]+\s*[xX×]\s*)?R\s*[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)),
    ("chamfer", re.compile(r"(?:\bC\s*[O0-9]{1,2}(?:\.[0-9]+)?\b|[0-9]+(?:\.[0-9]+)?\s*[xX]\s*C\s*[O0-9]{1,2}(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("metric_thread", re.compile(r"\b[0-9]*\s*[xX]?\s*M\s*[0-9]+(?:\.[0-9]+)?(?:\s*[xX]\s*[0-9]+(?:\.[0-9]+)?)?\b", re.IGNORECASE)),
    ("tolerance", re.compile(r"(?:±|\+-|\+/-)\s*[0-9]+(?:\.[0-9]+)?|[+-]\s*[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)),
    ("angle", re.compile(r"\b[0-9]+(?:\.[0-9]+)?\s*(?:°|deg\b)", re.IGNORECASE)),
    ("hole_callout", re.compile(r"\b(?:THRU|THROUGH|DRILL|CBORE|COUNTERBORE|CSINK|COUNTERSINK|DEPTH|DP)\b|(?:キリ|貫通|深さ|深)", re.IGNORECASE)),
]

PLAIN_DIMENSION_PATTERN = re.compile(
    r"^[tT]?\s*\(?\s*[0-9]{1,4}(?:\.[0-9]+)?\s*\)?(?:\s*(?:±|\+-|\+/-)\s*[0-9]+(?:\.[0-9]+)?)?$"
)
REFERENCE_DIMENSION_PATTERN = re.compile(r"^\(\s*[0-9]{1,4}(?:\.[0-9]+)?\s*\)$")
DATE_OR_FRACTION_PATTERN = re.compile(
    r"(?:\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b|\d+\s*/\s*\d+)"
)
NOISE_PATTERN = re.compile(r"^[\W_]+$")
REVISION_OR_DATE_CODE_PATTERN = re.compile(r"^\s*\d{1,2}(?:[./-]\d{1,2}){1,2}\s*$")

DRAWING_ROI = {
    "left": 0.05,
    "top": 0.12,
    "right": 0.95,
    "bottom": 0.88,
}

FULL_PAGE_OCR_ORIENTATIONS = {
    value.strip().lower()
    for value in os.getenv("FULL_PAGE_OCR_ORIENTATIONS", "normal,cw").split(",")
    if value.strip()
}

ANGLE_RESCUE_ENABLED = os.getenv("ANGLE_RESCUE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
ANGLE_RESCUE_MAX_CROPS = int(os.getenv("ANGLE_RESCUE_MAX_CROPS", "48"))
SMALL_TEXT_RESCUE_ENABLED = os.getenv("SMALL_TEXT_RESCUE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
SMALL_TEXT_RESCUE_MAX_TILES = int(os.getenv("SMALL_TEXT_RESCUE_MAX_TILES", "12"))
SMALL_TEXT_RESCUE_SCALE = float(os.getenv("SMALL_TEXT_RESCUE_SCALE", "2.4"))
FULL_PAGE_OCR_MAX_SIDE = int(os.getenv("FULL_PAGE_OCR_MAX_SIDE", "3200"))
VERTICAL_DECIMAL_RESCUE_ENABLED = os.getenv("VERTICAL_DECIMAL_RESCUE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
VERTICAL_DECIMAL_RESCUE_MAX_CROPS = int(os.getenv("VERTICAL_DECIMAL_RESCUE_MAX_CROPS", "12"))

JUNK_NOTE_WORDS = (
    "NOTE",
    "DEBURR",
    "UNSPECIFIED",
    "EDGES",
    "ANODIZED",
    "ANODIZING",
    "ISOPROPYL",
    "ALCOHOL",
    "BUFFING",
    "MATERIAL",
    "SURFACE TO",
    "DIMENSIONS AFTER",
    "INTERPRET DRAWING",
    "INSERT HELICOILS",
    "CLEAN PART",
    "FARSIDE",
    "REV",
    "REVISION",
    "HISTORY",
    "APPROVED",
    "CHECKED",
    "DRAWN",
    "DATE",
    "SCALE",
    "SHEET",
    "PROJ",
    "PART NUMBER",
    "DRAWING NUMBER",
)

ENGINEERING_SIGNAL_PATTERN = re.compile(
    r"(\d{2,}|M\s*\d|C\s*\d|R\s*\d|RA\s*\d|T\s*\d|"
    r"DIAM|DIA|DRILL|THRU|THROUGH|DEPTH|DP|CBORE|CSINK|"
    r"\+/-|\+-|[+-]\s*\d|//)", re.IGNORECASE
)

FULL_TOLERANCE_CALLOUT_PATTERN = re.compile(
    r"^[tT]?\s*\(?\s*[0-9]{1,4}(?:\.[0-9]+)?\s*(?:Â±|\+-|\+/-|±)\s*[0-9]+(?:\.[0-9]+)?\s*\)?$"
)


def get_image_paths(image_path=None, limit=None):
    paths = [Path(image_path)] if image_path else sorted(DATASET_IMAGES_DIR.glob("*.png"))
    return paths[:limit] if limit else paths


def normalize_text(text):
    text = str(text or "").strip()
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ø", "Ø").replace("φ", "Ø").replace("Φ", "Ø").replace("o/", "Ø").replace("O/", "Ø")
    text = text.replace("⌀", "Ø").replace("∅", "Ø")
    text = text.replace("×", "X")
    text = text.replace("±", "+/-").replace("ą", "+/-")
    text = text.replace("(", "(").replace(")", ")")
    text = re.sub(r"\bC\s*[Oo](?=\.)", "C0", text)
    text = re.sub(r"\bDrill\s*Thru\b", "DRILL THRU", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCounter\s*bore\b", "COUNTERBORE", text, flags=re.IGNORECASE)
    text = re.sub(r"深\s*さ", "DEPTH", text)
    text = text.replace("深", "DEPTH")
    text = text.replace("キリ貫通", "DRILL THRU").replace("貫通", "THRU")
    # Support real Japanese Unicode in addition to older mojibake replacements.
    text = re.sub(r"\u6df1\s*[\u3055\u30b5]", "DEPTH", text)
    text = text.replace("\u6df1", "DEPTH")
    text = text.replace("\u30ad\u30ea\u8cab\u901a", "DRILL THRU").replace("\u8cab\u901a", "THRU")
    text = text.replace("\u4e0b\u30ad\u30ea", "DRILL")
    text = re.sub(r"DEPTH\s*[\u3055\u30b5]?\s*(\d+(?:\.\d+)?)", r"DEPTH \1", text, flags=re.IGNORECASE)
    text = text.strip("'` ")
    text = re.sub(r"\s+", " ", text)
    return text


def repair_spaced_nominal_tolerance_text(text):
    """Join OCR-split nominal digits only in a complete tolerance callout."""
    normalized = normalize_text(text)
    match = re.fullmatch(
        r"\s*((?:\d\s+){1,3}\d)"
        r"(\s*(?:\+/-|\+-|±|Â±)\s*\d+(?:\.\d+)?)\s*",
        normalized,
    )
    if not match:
        return ""
    nominal = re.sub(r"\s+", "", match.group(1))
    tolerance = re.sub(r"\s+", "", match.group(2))
    return f"{nominal}{tolerance}"


def polygon_to_box(points):
    if points is None:
        return None

    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None

    if not xs or not ys:
        return None

    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def result_box_at(result_dict, index):
    for key in ("rec_boxes", "dt_boxes", "text_det_boxes"):
        boxes = result_dict.get(key)
        if boxes is None:
            boxes = []
        if index < len(boxes):
            box = boxes[index]
            if len(box) == 4 and not isinstance(box[0], (list, tuple)):
                x1, y1, x2, y2 = [int(float(value)) for value in box]
                return x1, y1, x2, y2
            polygon_box = polygon_to_box(box)
            if polygon_box:
                return polygon_box

    for key in ("rec_polys", "dt_polys", "text_det_polys"):
        polys = result_dict.get(key)
        if polys is None:
            polys = []
        if index < len(polys):
            polygon_box = polygon_to_box(polys[index])
            if polygon_box:
                return polygon_box

    return None


def extract_ocr_items_with_boxes(ocr_result):
    if not ocr_result:
        return []

    first_result = ocr_result[0]
    items = []

    if isinstance(first_result, dict):
        texts = first_result.get("rec_texts", []) or []
        scores = first_result.get("rec_scores", []) or []
        for index, text in enumerate(texts):
            box = result_box_at(first_result, index)
            if not box:
                continue
            score = scores[index] if index < len(scores) else 0.0
            items.append({"text": normalize_text(text), "confidence": float(score or 0), "box": box})
        return items

    for line in first_result or []:
        try:
            box = polygon_to_box(line[0])
            text = normalize_text(line[1][0])
            score = float(line[1][1])
        except (IndexError, TypeError, ValueError):
            continue
        if box:
            items.append({"text": text, "confidence": score, "box": box})

    return items


def predict_full_page_ocr_items(ocr, image):
    if FULL_PAGE_OCR_MAX_SIDE <= 0:
        return extract_ocr_items_with_boxes(ocr.predict(image))

    height, width = image.shape[:2]
    longest_side = max(width, height)
    if longest_side <= FULL_PAGE_OCR_MAX_SIDE:
        return extract_ocr_items_with_boxes(ocr.predict(image))

    scale = FULL_PAGE_OCR_MAX_SIDE / longest_side
    resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    items = extract_ocr_items_with_boxes(ocr.predict(resized))
    for item in items:
        x1, y1, x2, y2 = item["box"]
        item["box"] = (
            int(x1 / scale),
            int(y1 / scale),
            int(x2 / scale),
            int(y2 / scale),
        )
    return items


def transform_rotated_cw_box_to_original(box, original_width, original_height):
    rx1, ry1, rx2, ry2 = box
    rotated_corners = [
        (rx1, ry1),
        (rx2, ry1),
        (rx2, ry2),
        (rx1, ry2),
    ]
    original_points = [
        (ry, original_height - rx)
        for rx, ry in rotated_corners
    ]
    xs = [point[0] for point in original_points]
    ys = [point[1] for point in original_points]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def transform_rotated_ccw_box_to_original(box, original_width, original_height):
    rx1, ry1, rx2, ry2 = box
    rotated_corners = [
        (rx1, ry1),
        (rx2, ry1),
        (rx2, ry2),
        (rx1, ry2),
    ]
    original_points = [
        (original_width - ry, rx)
        for rx, ry in rotated_corners
    ]
    xs = [point[0] for point in original_points]
    ys = [point[1] for point in original_points]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def transform_rotated_180_box_to_original(box, original_width, original_height):
    rx1, ry1, rx2, ry2 = box
    rotated_corners = [
        (rx1, ry1),
        (rx2, ry1),
        (rx2, ry2),
        (rx1, ry2),
    ]
    original_points = [
        (original_width - rx, original_height - ry)
        for rx, ry in rotated_corners
    ]
    xs = [point[0] for point in original_points]
    ys = [point[1] for point in original_points]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def clamp_box(box, image_width, image_height):
    x1, y1, x2, y2 = box
    return (
        max(0, min(int(x1), image_width - 1)),
        max(0, min(int(y1), image_height - 1)),
        max(0, min(int(x2), image_width - 1)),
        max(0, min(int(y2), image_height - 1)),
    )


def rotate_image_bound(image, angle_degrees):
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle_degrees, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))
    matrix[0, 2] += (new_width / 2) - center[0]
    matrix[1, 2] += (new_height / 2) - center[1]
    rotated = cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, matrix


def transform_deskewed_crop_box_to_original(box, inverse_matrix, offset_x, offset_y, image_width, image_height):
    x1, y1, x2, y2 = box
    corners = np.array(
        [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]],
        dtype=np.float32,
    )
    mapped = cv2.transform(corners, inverse_matrix)[0]
    xs = mapped[:, 0] + offset_x
    ys = mapped[:, 1] + offset_y
    return clamp_box((xs.min(), ys.min(), xs.max(), ys.max()), image_width, image_height)


def box_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    if inter_area == 0:
        return 0.0

    a_area = max(1, (ax2 - ax1) * (ay2 - ay1))
    b_area = max(1, (bx2 - bx1) * (by2 - by1))
    return inter_area / (a_area + b_area - inter_area)


def is_duplicate_item(item, existing_items):
    for existing in existing_items:
        if box_iou(item["box"], existing["box"]) > 0.45:
            if item["text"] == existing["text"]:
                return True
    return False


def is_near_existing_text(item, existing_items, max_distance=55):
    item_x, item_y = box_center(item["box"])
    for existing in existing_items:
        existing_x, existing_y = box_center(existing["box"])
        if abs(item_x - existing_x) <= max_distance and abs(item_y - existing_y) <= max_distance:
            return True
    return False


def box_center(box):
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def box_size(item):
    x1, y1, x2, y2 = item["box"]
    return x2 - x1, y2 - y1


def merge_item_boxes(items):
    x1 = min(item["box"][0] for item in items)
    y1 = min(item["box"][1] for item in items)
    x2 = max(item["box"][2] for item in items)
    y2 = max(item["box"][3] for item in items)
    return x1, y1, x2, y2


def is_note_or_junk_text(text):
    normalized = normalize_text(text)
    upper = normalized.upper()
    if not normalized:
        return True
    if len(normalized) > 90:
        return True
    if any(word in upper for word in JUNK_NOTE_WORDS):
        return True
    if REVISION_OR_DATE_CODE_PATTERN.match(normalized):
        return True
    if NOISE_PATTERN.match(normalized):
        return True
    return not ENGINEERING_SIGNAL_PATTERN.search(normalized)


def filter_junk_and_notes(raw_ocr_items):
    return [
        item
        for item in raw_ocr_items
        if (
            not is_note_or_junk_text(item.get("text", ""))
            or (
                item.get("orientation") == "vertical_decimal_rescue"
                and re.fullmatch(
                    r"(?:[\u00d8\u2300\u2205\u03c6\u03a6])?\d{1,3}\.\d{1,3}",
                    normalize_text(item.get("text", "")),
                )
                and float(item.get("confidence", 0) or 0) >= 0.85
            )
            or (
                item.get("orientation") == "rescue_crop"
                and re.fullmatch(r"\d", normalize_text(item.get("text", "")))
                and float(item.get("confidence", 0) or 0) >= 0.98
            )
        )
    ]


def is_inside_table(item, image_width, image_height, yolo_tables=None, buffer=20):
    center_x, center_y = box_center(item["box"])

    for table in yolo_tables or []:
        class_name = table.get("class_name", "").lower()
        x1 = table.get("x_min", table.get("X", 0)) - buffer
        y1 = table.get("y_min", table.get("Y", 0)) - buffer
        x2 = table.get("x_max", table.get("X", 0) + table.get("Width", 0)) + buffer
        y2 = table.get("y_max", table.get("Y", 0) + table.get("Height", 0)) + buffer
        if x1 <= center_x <= x2 and y1 <= center_y <= y2:
            return True

    x_ratio = center_x / max(1, image_width)
    y_ratio = center_y / max(1, image_height)
    return any(
        left <= x_ratio <= right and top <= y_ratio <= bottom
        for left, top, right, bottom, _label in MEASUREMENT_EXCLUSION_REGIONS
    )

def should_merge_ocr_neighbors(left, right, y_tolerance=15, x_max_gap=45):
    if left.get("orientation") != right.get("orientation"):
        return False

    left_center_x, left_center_y = box_center(left["box"])
    right_center_x, right_center_y = box_center(right["box"])
    _, left_height = box_size(left)
    _, right_height = box_size(right)
    same_line = abs(left_center_y - right_center_y) <= max(y_tolerance, (left_height + right_height) * 0.25)
    if not same_line:
        return False

    gap = right["box"][0] - left["box"][2]
    if gap < -5 or gap > x_max_gap:
        return False

    left_text = normalize_text(left.get("text", ""))
    right_text = normalize_text(right.get("text", ""))
    if is_note_or_junk_text(left_text) or is_note_or_junk_text(right_text):
        return False

    if "+/-" in left_text and "+/-" in right_text:
        return False

    if re.search(r"^(?:\+/-|\+-|Â±|±|[+-])", right_text):
        return True
    if re.fullmatch(r"[tTrRcC]|Ra", left_text) and re.search(r"\d", right_text):
        return True
    if re.search(r"\d$", left_text) and re.search(r"^(?:Â±|±|\+/-|\+-|[+-])", right_text):
        return True
    if re.search(r"\b(?:DRILL|THRU|THROUGH|DEPTH|DP|CBORE|CSINK)\b", left_text, re.IGNORECASE):
        return re.search(r"\b(?:DRILL|THRU|THROUGH|DEPTH|DP|CBORE|CSINK)\b", right_text, re.IGNORECASE)

    return False


def merge_nearby_boxes(raw_ocr_items, y_tolerance=15, x_max_gap=45):
    sorted_items = sorted(raw_ocr_items, key=lambda item: (item.get("orientation", ""), item["box"][1], item["box"][0]))
    merged = []

    for item in sorted_items:
        if not merged:
            merged.append(item)
            continue

        previous = merged[-1]
        if should_merge_ocr_neighbors(previous, item, y_tolerance=y_tolerance, x_max_gap=x_max_gap):
            merged_item = dict(previous)
            merged_item["text"] = normalize_text(f"{previous['text']} {item['text']}")
            merged_item["confidence"] = min(float(previous.get("confidence", 0)), float(item.get("confidence", 0)))
            merged_item["box"] = merge_item_boxes([previous, item])
            merged.append(merged_item)
            merged.pop(-2)
        else:
            merged.append(item)

    return merged


def merge_incomplete_below_limit_decimals(raw_ocr_items):
    """Join angled values split as `2XR0.` and `2以下` by PaddleOCR."""
    merged_items = [dict(item) for item in raw_ocr_items]
    consumed = set()
    for index, item in enumerate(merged_items):
        text = normalize_text(item.get("text", ""))
        if not re.search(r"(?:R|C)\s*0\.$", text, re.IGNORECASE):
            continue
        item_x, item_y = box_center(item["box"])
        best = None
        for suffix_index, suffix in enumerate(merged_items):
            if suffix_index == index or suffix_index in consumed:
                continue
            suffix_text = normalize_text(suffix.get("text", ""))
            suffix_match = re.fullmatch(r"(\d)\s*(?:\u4ee5\u4e0b|BELOW)", suffix_text, re.IGNORECASE)
            if not suffix_match:
                continue
            suffix_x, suffix_y = box_center(suffix["box"])
            distance = abs(item_x - suffix_x) + abs(item_y - suffix_y)
            if distance > 420:
                continue
            if best is None or distance < best[0]:
                best = (distance, suffix_index, suffix, suffix_match.group(1))
        if best is None:
            continue
        _, suffix_index, suffix, final_digit = best
        item["text"] = re.sub(r"\.$", f".0{final_digit}", text)
        item["confidence"] = min(
            float(item.get("confidence", 0) or 0),
            float(suffix.get("confidence", 0) or 0),
        )
        item["box"] = merge_item_boxes([item, suffix])
        consumed.add(suffix_index)
    return [item for index, item in enumerate(merged_items) if index not in consumed]


def clean_ocr_results(raw_ocr_items, image_width, image_height, yolo_tables=None):
    repaired_items = merge_incomplete_below_limit_decimals(raw_ocr_items)
    step1_items = filter_junk_and_notes(repaired_items)
    step2_items = [
        item
        for item in step1_items
        if not is_inside_table(item, image_width, image_height, yolo_tables=yolo_tables, buffer=20)
    ]
    return merge_nearby_boxes(step2_items, y_tolerance=15, x_max_gap=45)


def crop_has_dimension_lines(crop):
    if crop.size == 0:
        return False

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=3.14159265 / 180,
        threshold=35,
        minLineLength=max(35, min(crop.shape[:2]) // 5),
        maxLineGap=8,
    )
    return lines is not None and len(lines) >= 2


def rescue_single_digit_dimensions(ocr, image, existing_items):
    image_height, image_width = image.shape[:2]
    rescue_regions = [
        # Focused top-center drawing band for small one-digit dimensions.
        # Avoid the right notes/title area to prevent revision triangle numbers.
        # Start slightly above the nominal band. On approved drawings a tiny
        # dimension can sit directly on the old 0.16 boundary, causing its top
        # edge to be clipped before OCR (for example y=528 on a 3306px page).
        (0.48, 0.14, 0.66, 0.34),
    ]
    scale = 3
    rescued = []

    for left, top, right, bottom in rescue_regions:
        x = int(image_width * left)
        y = int(image_height * top)
        x2 = int(image_width * right)
        y2 = int(image_height * bottom)
        crop = image[y:y2, x:x2]
        if not crop_has_dimension_lines(crop):
            continue

        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for item in extract_ocr_items_with_boxes(ocr.predict(enlarged)):
            text = normalize_text(item["text"])
            if not re.fullmatch(r"\d", text):
                continue
            if float(item.get("confidence", 0) or 0) < 0.98:
                continue

            bx1, by1, bx2, by2 = item["box"]
            mapped = {
                "text": text,
                "confidence": float(item.get("confidence", 0) or 0),
                "box": (
                    int(x + bx1 / scale),
                    int(y + by1 / scale),
                    int(x + bx2 / scale),
                    int(y + by2 / scale),
                ),
                "orientation": "rescue_crop",
            }
            box_width, box_height = box_size(mapped)
            if box_width < 12 or box_height < 14:
                continue
            if is_duplicate_item(mapped, existing_items + rescued):
                continue
            rescued.append(mapped)

    return rescued


def normalized_line_angle(x1, y1, x2, y2):
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while angle <= -90:
        angle += 180
    while angle > 90:
        angle -= 180
    return angle


def is_similar_angle_crop(candidate, selected):
    cx = (candidate["x1"] + candidate["x2"]) / 2
    cy = (candidate["y1"] + candidate["y2"]) / 2
    for existing in selected:
        ex = (existing["x1"] + existing["x2"]) / 2
        ey = (existing["y1"] + existing["y2"]) / 2
        if abs(cx - ex) <= 90 and abs(cy - ey) <= 90 and abs(candidate["angle"] - existing["angle"]) <= 12:
            return True
    return False


def find_angled_dimension_crops(image):
    if not ANGLE_RESCUE_ENABLED:
        return []

    image_height, image_width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 180)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=42,
        minLineLength=max(38, min(image_width, image_height) // 65),
        maxLineGap=12,
    )
    if lines is None:
        return []

    candidates = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = [int(value) for value in line]
        angle = normalized_line_angle(x1, y1, x2, y2)
        if abs(angle) < 15 or abs(angle) > 75:
            continue

        length = math.hypot(x2 - x1, y2 - y1)
        if length < 45 or length > 650:
            continue

        pad = max(70, min(150, int(length * 0.45)))
        crop_x1 = max(0, min(x1, x2) - pad)
        crop_y1 = max(0, min(y1, y2) - pad)
        crop_x2 = min(image_width, max(x1, x2) + pad)
        crop_y2 = min(image_height, max(y1, y2) + pad)
        crop_width = crop_x2 - crop_x1
        crop_height = crop_y2 - crop_y1
        if crop_width < 40 or crop_height < 40:
            continue
        if crop_width > 950 or crop_height > 950:
            continue

        candidate = {
            "x1": crop_x1,
            "y1": crop_y1,
            "x2": crop_x2,
            "y2": crop_y2,
            "angle": angle,
            "length": length,
        }
        candidates.append(candidate)

    candidates.sort(key=lambda item: (-item["length"], item["y1"], item["x1"]))
    selected = []
    for candidate in candidates:
        if is_similar_angle_crop(candidate, selected):
            continue
        selected.append(candidate)
        if len(selected) >= ANGLE_RESCUE_MAX_CROPS:
            break
    return selected


def rescue_angled_dimensions(ocr, image, existing_items):
    image_height, image_width = image.shape[:2]
    rescued = []
    for crop_info in find_angled_dimension_crops(image):
        crop = image[crop_info["y1"] : crop_info["y2"], crop_info["x1"] : crop_info["x2"]]
        if crop.size == 0:
            continue

        rotation_variants = [
            (crop, crop_info["x1"], crop_info["y1"], -crop_info["angle"]),
        ]
        # Degree callouts are often placed on short arc/chord geometry. The
        # detected line can be near 20-30 degrees while the text is at 45
        # degrees, so try one canonical rotation only for these small crops.
        if (
            15 <= abs(crop_info["angle"]) <= 30
            and crop_info["length"] <= 200
        ):
            extra_pad = 260
            extended_x1 = max(0, crop_info["x1"] - extra_pad)
            extended_y1 = max(0, crop_info["y1"] - extra_pad)
            extended_x2 = min(image_width, crop_info["x2"] + extra_pad)
            extended_y2 = min(image_height, crop_info["y2"] + extra_pad)
            extended_crop = image[extended_y1:extended_y2, extended_x1:extended_x2]
            if extended_crop.size:
                rotation_variants.append(
                    (
                        extended_crop,
                        extended_x1,
                        extended_y1,
                        45 if crop_info["angle"] > 0 else -45,
                    )
                )

        seen_rotations = set()
        for variant_crop, origin_x, origin_y, rotation_angle in rotation_variants:
            rotation_key = (origin_x, origin_y, round(rotation_angle, 3))
            if rotation_key in seen_rotations:
                continue
            seen_rotations.add(rotation_key)
            deskewed, matrix = rotate_image_bound(variant_crop, rotation_angle)
            inverse_matrix = cv2.invertAffineTransform(matrix)

            try:
                local_items = extract_ocr_items_with_boxes(ocr.predict(deskewed))
            except Exception:
                continue

            for item in local_items:
                text = normalize_text(item.get("text", ""))
                if is_note_or_junk_text(text):
                    continue
                if float(item.get("confidence", 0) or 0) < 0.62:
                    continue

                mapped = {
                    "text": text,
                    "confidence": float(item.get("confidence", 0) or 0),
                    "box": transform_deskewed_crop_box_to_original(
                        item["box"],
                        inverse_matrix,
                        origin_x,
                        origin_y,
                        image_width,
                        image_height,
                    ),
                    "orientation": f"angled_{round(-rotation_angle)}",
                }
                box_width, box_height = box_size(mapped)
                if box_width < 12 or box_height < 12:
                    continue
                if is_duplicate_item(mapped, existing_items + rescued):
                    continue
                rescued.append(mapped)

    return rescued


def remove_dimension_lines_for_text(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    height, width = binary.shape[:2]
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(28, width // 3), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(28, height // 3)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    text_mask = cv2.bitwise_and(binary, cv2.bitwise_not(cv2.bitwise_or(horizontal, vertical)))
    return cv2.cvtColor(255 - text_mask, cv2.COLOR_GRAY2BGR), text_mask


def find_vertical_decimal_text_crops(image):
    if not VERTICAL_DECIMAL_RESCUE_ENABLED:
        return []

    image_height, image_width = image.shape[:2]
    left = int(image_width * DRAWING_ROI["left"])
    top = int(image_height * DRAWING_ROI["top"])
    right = int(image_width * DRAWING_ROI["right"])
    bottom = int(image_height * DRAWING_ROI["bottom"])
    roi = image[top:bottom, left:right]
    if roi.size == 0:
        return []

    _, text_mask = remove_dimension_lines_for_text(roi)
    group_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (24, 80))
    grouped = cv2.dilate(text_mask, group_kernel, iterations=1)
    contours, _ = cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # A narrower horizontal grouping pass keeps vertical diameter characters
    # separate from adjacent extension graphics. Both passes are still
    # validated by rotated OCR and deduplicated below.
    narrow_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 70))
    narrow_grouped = cv2.dilate(text_mask, narrow_kernel, iterations=1)
    narrow_contours, _ = cv2.findContours(
        narrow_grouped,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    contours = list(contours) + list(narrow_contours)

    crops = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if height < 80 or width < 14:
            continue
        # Vertical callouts can touch a nearby extension/leader graphic after
        # dilation. Keep moderately wider groups when they are still clearly
        # tall; the later rotated OCR must validate the actual text.
        if height > 720 or width > 340:
            continue
        if height < width * 1.35:
            continue

        x1 = max(0, left + x - 30)
        y1 = max(0, top + y - 30)
        x2 = min(image_width, left + x + width + 30)
        y2 = min(image_height, top + y + height + 30)
        crop_width = x2 - x1
        crop_height = y2 - y1
        if crop_width < 35 or crop_height < 90:
            continue
        center_x = ((x1 + x2) / 2) / max(1, image_width)
        center_y = ((y1 + y2) / 2) / max(1, image_height)
        if exclusion_region_label(center_x, center_y, MEASUREMENT_EXCLUSION_REGIONS):
            continue
        crops.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "area": crop_width * crop_height,
            }
        )

    selected = []

    def add_crop_if_new(crop):
        duplicate = False
        for existing in selected:
            if (
                abs((crop["x1"] + crop["x2"]) / 2 - (existing["x1"] + existing["x2"]) / 2) <= 80
                and abs((crop["y1"] + crop["y2"]) / 2 - (existing["y1"] + existing["y2"]) / 2) <= 120
            ):
                duplicate = True
                break
        if duplicate:
            return
        selected.append(crop)

    crops.sort(key=lambda item: (-(item["y2"] - item["y1"]), item["y1"], item["x1"]))
    for crop in crops:
        add_crop_if_new(crop)
        if len(selected) >= VERTICAL_DECIMAL_RESCUE_MAX_CROPS:
            break

    # Always inspect the lower-middle section-view band. Contour-generated
    # candidates often fill the normal crop budget before this fallback is
    # reached, which previously made a valid vertical diameter (for example
    # `Ø21.0`) impossible to recover during the full pipeline.
    mandatory_fallback_regions = [
        (0.38, 0.66, 0.48, 0.83),
    ]
    for left_ratio, top_ratio, right_ratio, bottom_ratio in mandatory_fallback_regions:
        mandatory_crop = {
            "x1": int(image_width * left_ratio),
            "y1": int(image_height * top_ratio),
            "x2": int(image_width * right_ratio),
            "y2": int(image_height * bottom_ratio),
            "area": int(image_width * (right_ratio - left_ratio))
            * int(image_height * (bottom_ratio - top_ratio)),
            "mandatory": True,
        }
        # A nearby contour crop is not equivalent: it can clip the leading
        # diameter glyph or decimal text. Suppress only the exact same box.
        if not any(
            all(existing[key] == mandatory_crop[key] for key in ("x1", "y1", "x2", "y2"))
            for existing in selected
        ):
            # Run this stable, approved section crop before differently sized
            # contour crops. Paddle detection on CPU can otherwise vary after
            # a long mixed-shape sequence.
            selected.insert(0, mandatory_crop)

    fallback_regions = [
        # Split main-view crops keep separate vertical labels from being merged.
        (0.09, 0.29, 0.15, 0.46),
        (0.09, 0.43, 0.15, 0.61),
        (0.58, 0.27, 0.65, 0.44),
        (0.58, 0.40, 0.65, 0.58),
        (0.73, 0.29, 0.80, 0.46),
        (0.73, 0.43, 0.80, 0.61),
        # Section-view vertical dimensions in the lower drawing area.
        (0.23, 0.66, 0.31, 0.88),
        (0.49, 0.66, 0.57, 0.88),
    ]
    for left_ratio, top_ratio, right_ratio, bottom_ratio in fallback_regions:
        crop = {
            "x1": int(image_width * left_ratio),
            "y1": int(image_height * top_ratio),
            "x2": int(image_width * right_ratio),
            "y2": int(image_height * bottom_ratio),
            "area": int(image_width * (right_ratio - left_ratio)) * int(image_height * (bottom_ratio - top_ratio)),
        }
        duplicate = False
        for existing in selected:
            if (
                abs((crop["x1"] + crop["x2"]) / 2 - (existing["x1"] + existing["x2"]) / 2) <= 80
                and abs((crop["y1"] + crop["y2"]) / 2 - (existing["y1"] + existing["y2"]) / 2) <= 120
            ):
                duplicate = True
                break
        if not duplicate:
            selected.append(crop)
        if len(selected) >= VERTICAL_DECIMAL_RESCUE_MAX_CROPS:
            break
    return selected


def transform_rotated_cw_crop_box_to_original(box, crop_x, crop_y, crop_width, crop_height):
    x1, y1, x2, y2 = transform_rotated_cw_box_to_original(box, crop_width, crop_height)
    return crop_x + x1, crop_y + y1, crop_x + x2, crop_y + y2


def merge_decimal_ocr_fragments(items):
    candidates = []
    for item in items:
        text = normalize_text(item.get("text", ""))
        raw_text = text
        text = text.replace("O", "0").replace("o", "0")
        text = re.sub(r"^[CS]$", "5", text, flags=re.IGNORECASE)
        text = re.sub(r"[^0-9.]", "", text)
        if not text or not re.search(r"\d", text):
            continue
        confidence = float(item.get("confidence", 0) or 0)
        minimum_confidence = 0.10 if re.fullmatch(r"[CS]", raw_text, re.IGNORECASE) else 0.35
        if confidence < minimum_confidence:
            continue
        candidates.append({**item, "text": text})

    if not candidates:
        return []

    rows = []
    for item in sorted(candidates, key=lambda value: (value["box"][1], value["box"][0])):
        x1, y1, x2, y2 = item["box"]
        center_y = (y1 + y2) / 2
        placed = False
        for row in rows:
            if abs(center_y - row["center_y"]) <= max(32, (y2 - y1) * 0.45):
                row["items"].append(item)
                row["center_y"] = sum((entry["box"][1] + entry["box"][3]) / 2 for entry in row["items"]) / len(row["items"])
                placed = True
                break
        if not placed:
            rows.append({"center_y": center_y, "items": [item]})

    merged = []
    for row in rows:
        row_items = sorted(row["items"], key=lambda value: value["box"][0])
        text = "".join(item["text"] for item in row_items)
        text = re.sub(r"\.{2,}", ".", text)
        if "." not in text:
            dot_source = next((item for item in row_items if item["text"].endswith(".")), None)
            if dot_source and len(text) >= 2:
                text = text[:-1] + "." + text[-1]
        if not re.fullmatch(r"\d{1,3}\.\d{1,3}", text):
            continue
        if re.fullmatch(r"0\d{2,3}\.\d{1,3}", text):
            text = f"\u00d8{text[1:]}"
        boxes = [item["box"] for item in row_items]
        merged.append(
            {
                "text": text,
                "confidence": min(float(item.get("confidence", 0) or 0) for item in row_items),
                "box": (
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ),
            }
        )
    return merged


def rescue_vertical_decimal_dimensions(ocr, image, existing_items, crop_infos=None):
    image_height, image_width = image.shape[:2]
    rescued = []
    # Do not let a broad-OCR fragment block a focused vertical rescue when
    # that broad row will itself be removed as date/revision-like noise during
    # cleanup. This was discarding both copies of a valid `21.0` dimension.
    viable_existing_items = filter_junk_and_notes(existing_items)

    selected_crop_infos = (
        list(crop_infos)
        if crop_infos is not None
        else find_vertical_decimal_text_crops(image)
    )
    for crop_info in selected_crop_infos:
        crop_x1 = crop_info["x1"]
        crop_y1 = crop_info["y1"]
        crop_x2 = crop_info["x2"]
        crop_y2 = crop_info["y2"]
        crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            continue

        cleaned, _ = remove_dimension_lines_for_text(crop)
        # Preserve the original pixels first. Removing dimension/extension
        # lines can also erase the decimal point or part of a leading diameter
        # glyph. Use the cleaned crop only when the original crop yields no
        # valid decimal, which keeps the common path fast.
        variants = [
            ("original_cw", cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE), 2),
        ]
        if crop_info.get("mandatory"):
            variants.append(
                ("original_cw_3x", cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE), 3)
            )
        variants.append(
            ("cleaned_cw", cv2.rotate(cleaned, cv2.ROTATE_90_CLOCKWISE), 3)
        )
        for _, rotated, scale in variants:
            enlarged = cv2.resize(rotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

            try:
                local_items = extract_ocr_items_with_boxes(ocr.predict(enlarged))
            except Exception:
                continue

            scaled_items = []
            for item in local_items:
                bx1, by1, bx2, by2 = item["box"]
                scaled_items.append(
                    {
                        "text": item.get("text", ""),
                        "confidence": float(item.get("confidence", 0) or 0),
                        "box": (
                            int(bx1 / scale),
                            int(by1 / scale),
                            int(bx2 / scale),
                            int(by2 / scale),
                        ),
                    }
                )

            merged_items = merge_decimal_ocr_fragments(scaled_items)
            for merged in merged_items:
                mapped_box = transform_rotated_cw_crop_box_to_original(
                    merged["box"],
                    crop_x1,
                    crop_y1,
                    crop_x2 - crop_x1,
                    crop_y2 - crop_y1,
                )
                mapped = {
                    "text": merged["text"],
                    "confidence": merged["confidence"],
                    "box": mapped_box,
                    "orientation": "vertical_decimal_rescue",
                }
                if not is_inside_drawing_roi(mapped, image_width, image_height):
                    continue
                if is_duplicate_item(mapped, viable_existing_items + rescued):
                    continue
                rescued.append(mapped)
            if merged_items:
                break

    return rescued


def small_text_tile_regions(image_width, image_height):
    if not SMALL_TEXT_RESCUE_ENABLED:
        return []

    left = int(image_width * DRAWING_ROI["left"])
    top = int(image_height * DRAWING_ROI["top"])
    right = int(image_width * DRAWING_ROI["right"])
    bottom = int(image_height * DRAWING_ROI["bottom"])
    roi_width = max(1, right - left)
    roi_height = max(1, bottom - top)
    columns = 4
    rows = 3
    overlap = 0.12
    tile_width = roi_width / columns
    tile_height = roi_height / rows
    regions = []

    for row_index in range(rows):
        for column_index in range(columns):
            x1 = left + int(max(0, column_index * tile_width - tile_width * overlap))
            y1 = top + int(max(0, row_index * tile_height - tile_height * overlap))
            x2 = left + int(min(roi_width, (column_index + 1) * tile_width + tile_width * overlap))
            y2 = top + int(min(roi_height, (row_index + 1) * tile_height + tile_height * overlap))
            regions.append((x1, y1, x2, y2))

    return regions[:SMALL_TEXT_RESCUE_MAX_TILES]


def is_plausible_small_rescue_item(mapped):
    text = normalize_text(mapped.get("text", ""))
    if is_note_or_junk_text(text):
        return False
    if not ENGINEERING_SIGNAL_PATTERN.search(text):
        return False
    if float(mapped.get("confidence", 0) or 0) < 0.70:
        return False

    box_width, box_height = box_size(mapped)
    if box_width < 7 or box_height < 7:
        return False
    if box_width > 260 or box_height > 90:
        return False
    if len(text) > 28:
        return False
    return True


def should_suppress_nearby_small_rescue(mapped, existing_items):
    return (
        is_near_existing_text(mapped, existing_items, max_distance=24)
        and len(normalize_text(mapped.get("text", ""))) <= 4
        and float(mapped.get("confidence", 0) or 0) < 0.90
    )


def rescue_small_text_dimensions(ocr, image, existing_items):
    image_height, image_width = image.shape[:2]
    rescued = []
    scale = max(1.5, SMALL_TEXT_RESCUE_SCALE)

    for x1, y1, x2, y2 in small_text_tile_regions(image_width, image_height):
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        if not crop_has_dimension_lines(crop):
            continue

        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        try:
            local_items = extract_ocr_items_with_boxes(ocr.predict(enlarged))
        except Exception:
            continue

        for item in local_items:
            bx1, by1, bx2, by2 = item["box"]
            mapped = {
                "text": normalize_text(item.get("text", "")),
                "confidence": float(item.get("confidence", 0) or 0),
                "box": (
                    int(x1 + bx1 / scale),
                    int(y1 + by1 / scale),
                    int(x1 + bx2 / scale),
                    int(y1 + by2 / scale),
                ),
                "orientation": "small_text_rescue",
            }
            if not is_plausible_small_rescue_item(mapped):
                continue
            if is_duplicate_item(mapped, existing_items + rescued):
                continue
            if should_suppress_nearby_small_rescue(mapped, existing_items + rescued):
                # A lower-resolution full-page pass can leave an incorrect
                # nearby fragment. Do not let that fragment suppress a clear,
                # high-confidence result from the dedicated small-text tile
                # (for example a recovered `31`). Exact duplicates are already
                # handled by is_duplicate_item() above.
                continue
            rescued.append(mapped)

    return rescued


def is_inside_drawing_roi(item, image_width, image_height):
    center_x, center_y = box_center(item["box"])
    return (
        image_width * DRAWING_ROI["left"] <= center_x <= image_width * DRAWING_ROI["right"]
        and image_height * DRAWING_ROI["top"] <= center_y <= image_height * DRAWING_ROI["bottom"]
    )


def passes_dynamic_confidence(item, image_width, image_height, base_confidence):
    if is_inside_drawing_roi(item, image_width, image_height):
        return item["confidence"] >= min(base_confidence, 0.65)
    return item["confidence"] >= max(base_confidence, 0.95)


def extract_measurement_ocr_items(ocr, image):
    image_height, image_width = image.shape[:2]
    all_variants = [
        ("normal", image, None),
        ("rotated_cw", cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), "cw"),
        ("rotated_ccw", cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), "ccw"),
        ("rotated_180", cv2.rotate(image, cv2.ROTATE_180), "180"),
    ]
    orientation_aliases = {
        "normal": {"normal", "0"},
        "rotated_cw": {"cw", "rotated_cw", "90"},
        "rotated_ccw": {"ccw", "rotated_ccw", "270"},
        "rotated_180": {"180", "rotated_180"},
    }
    variants = [
        variant
        for variant in all_variants
        if orientation_aliases[variant[0]] & FULL_PAGE_OCR_ORIENTATIONS
    ]
    if not variants:
        variants = all_variants[:2]
    items = []

    for orientation, variant_image, rotation in variants:
        for item in predict_full_page_ocr_items(ocr, variant_image):
            if rotation == "cw":
                item["box"] = transform_rotated_cw_box_to_original(
                    item["box"],
                    image_width,
                    image_height,
                )
            elif rotation == "ccw":
                item["box"] = transform_rotated_ccw_box_to_original(
                    item["box"],
                    image_width,
                    image_height,
                )
            elif rotation == "180":
                item["box"] = transform_rotated_180_box_to_original(
                    item["box"],
                    image_width,
                    image_height,
                )
            item["orientation"] = orientation
            if not is_duplicate_item(item, items):
                items.append(item)

    items.extend(rescue_angled_dimensions(ocr, image, items))
    items.extend(rescue_vertical_decimal_dimensions(ocr, image, items))

    # Clean the broad full-page OCR results before using them as blockers for
    # the focused small-text passes.  The broad pass can contain a nearby
    # low-resolution fragment (for example `11`) which should not suppress a
    # clearer tile result (`31`).  Focused rescue rows are already screened by
    # their own plausibility and duplicate checks, so keep them separate from
    # merge_nearby_boxes; merging them back into the broad rows can destroy a
    # valid small dimension.
    cleaned_items = clean_ocr_results(items, image_width=image_width, image_height=image_height)
    small_text_items = rescue_small_text_dimensions(ocr, image, cleaned_items)
    single_digit_items = rescue_single_digit_dimensions(
        ocr,
        image,
        cleaned_items + small_text_items,
    )

    rescued_items = []
    for item in small_text_items + single_digit_items:
        if not filter_junk_and_notes([item]):
            continue
        if is_inside_table(item, image_width, image_height, buffer=20):
            continue
        if is_duplicate_item(item, cleaned_items + rescued_items):
            continue
        rescued_items.append(item)

    return cleaned_items + rescued_items


def classify_measurement(text):
    if not text or len(text) < 1 or NOISE_PATTERN.match(text):
        return None, None

    text = repair_spaced_nominal_tolerance_text(text) or text
    engineering_marker = re.search(
        r"[\u00d8\u2300\u2205\u03c6\u03a6]|(?:^|[^A-Z])(?:M|R|C|T)\s*\d|[+-]\s*\d|\+/-|\+-|\u00b0",
        text,
        re.IGNORECASE,
    )
    if DATE_OR_FRACTION_PATTERN.search(text) and not engineering_marker:
        return None, None

    if FULL_TOLERANCE_CALLOUT_PATTERN.fullmatch(text):
        return "plain_dimension", text

    if re.fullmatch(
        r"(?:\d+\s*[xX]\s*)?(?:[\u00d8\u2300\u2205\u03c6\u03a6]|DIA\.?|DIAMETER)\s*\d+(?:\.\d+)?\s*[+-]\s*\d+(?:\.\d+)?(?:\s*0(?:\.0+)?)?",
        text,
        re.IGNORECASE,
    ):
        return "diameter", text
    if re.fullmatch(
        r"(?:\d+\s*[xX]\s*)?R\s*\d+(?:\.\d+)?\s*[+-]\s*\d+(?:\.\d+)?(?:\s*0(?:\.0+)?)?",
        text,
        re.IGNORECASE,
    ):
        return "radius", text
    if re.fullmatch(
        r"\d+(?:\.\d+)?\s*[+-]\s*\d+(?:\.\d+)?(?:\s*0(?:\.0+)?)?",
        text,
        re.IGNORECASE,
    ):
        return "plain_dimension", text

    for measurement_type, pattern in MEASUREMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(0).strip()
            if measurement_type == "metric_thread":
                return measurement_type, text
            if measurement_type == "hole_callout":
                return measurement_type, text
            if measurement_type == "tolerance":
                numeric = re.search(r"[0-9]+(?:\.[0-9]+)?", value)
                if numeric and float(numeric.group(0)) > 1:
                    return None, None
            return measurement_type, value

    if REFERENCE_DIMENSION_PATTERN.fullmatch(text):
        return "reference_dimension", text

    plain_match = PLAIN_DIMENSION_PATTERN.fullmatch(text)
    if plain_match:
        value = re.sub(r"^[tT]\s*", "", plain_match.group(0)).strip()
        value = re.sub(r"^\(\s*|\s*\)$", "", value)
        if value in {"0", "00", "000", "01"}:
            return None, None
        return "plain_dimension", value

    return None, None


def should_skip_text(text):
    upper = text.upper()
    if len(text) > 80:
        return True
    title_noise = (
        "DRAWING", "MATERIAL", "SCALE", "DATE", "CHECK", "APPROVED", "SHEET",
        "REV", "REVISION", "HISTORY", "LOT", "PART", "PROJ", "CAD",
    )
    if any(word in upper for word in title_noise):
        return True
    return bool(REVISION_OR_DATE_CODE_PATTERN.match(text))


def create_measurement_row(source_file, item, measurement_type, value, review_threshold):
    x1, y1, x2, y2 = item["box"]
    confidence = float(item.get("confidence") or 0.0)
    reasons = []
    if confidence < review_threshold:
        reasons.append("Low OCR confidence")
    if measurement_type in {"plain_dimension", "reference_dimension"}:
        reasons.append("Plain number needs human check")

    return {
        "Source File": source_file,
        "Measurement Type": measurement_type,
        "Extracted Value": value,
        "OCR Text": item["text"],
        "OCR Confidence": round(confidence, 4),
        "X": x1,
        "Y": y1,
        "Width": x2 - x1,
        "Height": y2 - y1,
        "Box": f"{x1},{y1},{x2},{y2}",
        "OCR Orientation": item.get("orientation", "normal"),
        "Needs Review": "YES" if reasons else "NO",
        "Review Reason": "; ".join(reasons),
        "Human Correction": "",
    }


def draw_measurement(image, row):
    x1 = int(row["X"])
    y1 = int(row["Y"])
    x2 = x1 + int(row["Width"])
    y2 = y1 + int(row["Height"])
    color = (0, 130, 255) if row["Needs Review"] == "NO" else (0, 0, 255)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    label = f"{row['Measurement Type']} {row['OCR Confidence']:.2f}"
    cv2.putText(
        image,
        label,
        (x1, max(18, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
        cv2.LINE_AA,
    )


def save_measurement_workbook(rows, output_path):
    columns = [
        "Source File",
        "Measurement Type",
        "Extracted Value",
        "OCR Text",
        "OCR Confidence",
        "X",
        "Y",
        "Width",
        "Height",
        "Box",
        "OCR Orientation",
        "Needs Review",
        "Review Reason",
        "Human Correction",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df = sanitize_dataframe_for_excel(df)
    df.to_excel(output_path, index=False)


def run_measurement_extraction(
    image_paths,
    confidence,
    review_threshold,
    output_path,
    existing_rows=None,
    save_after_each=False,
):
    ocr = create_paddle_ocr()
    rows = list(existing_rows or [])
    failed = []
    DEBUG_MEASUREMENT_DETECTION_DIR.mkdir(parents=True, exist_ok=True)

    for image_path in image_paths:
        start = time.perf_counter()
        image = cv2.imread(str(image_path))
        if image is None:
            failed.append(str(image_path))
            print(f"{image_path.name}: could not read image")
            continue

        try:
            ocr_items = extract_measurement_ocr_items(ocr, image)
        except Exception as exc:
            failed.append(str(image_path))
            print(f"{image_path.name}: OCR failed: {exc}")
            continue

        debug_image = image.copy()
        image_height, image_width = image.shape[:2]
        count = 0
        for item in ocr_items:
            if not passes_dynamic_confidence(item, image_width, image_height, confidence):
                continue
            if should_skip_text(item["text"]):
                continue

            measurement_type, value = classify_measurement(item["text"])
            if not measurement_type:
                continue

            row = create_measurement_row(
                source_file=image_path.name,
                item=item,
                measurement_type=measurement_type,
                value=value,
                review_threshold=review_threshold,
            )
            rows.append(row)
            draw_measurement(debug_image, row)
            count += 1

        cv2.imwrite(str(DEBUG_MEASUREMENT_DETECTION_DIR / image_path.name), debug_image)
        elapsed = time.perf_counter() - start
        print(f"{image_path.name}: {count} measurement candidates in {elapsed:.1f}s")
        if save_after_each:
            save_measurement_workbook(rows, output_path)
            print(f"  progress saved: {output_path}")

    save_measurement_workbook(rows, output_path)
    return rows, failed


def main():
    parser = argparse.ArgumentParser(description="Extract measurement-like OCR rows from drawing images.")
    parser.add_argument("--image", type=Path, help="Optional single PNG/JPG image to process.")
    parser.add_argument("--limit", type=int, help="Optional number of images to process.")
    parser.add_argument("--conf", type=float, default=MEASUREMENT_OCR_CONFIDENCE, help="Minimum OCR confidence.")
    parser.add_argument(
        "--review-threshold",
        type=float,
        default=MEASUREMENT_REVIEW_THRESHOLD,
        help="Rows below this confidence are marked Needs Review.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip drawings already present in the output workbook and save progress after each drawing.",
    )
    parser.add_argument("--output", type=Path, default=MEASUREMENT_DETECTION_OUTPUT_PATH)
    args = parser.parse_args()

    ensure_directories()
    image_paths = get_image_paths(args.image, args.limit)
    if not image_paths:
        print(f"No images found in {DATASET_IMAGES_DIR}")
        return

    existing_rows = []
    if args.resume and args.output.exists():
        existing_df = pd.read_excel(args.output)
        existing_rows = sanitize_dataframe_for_excel(existing_df).to_dict("records")
        done_files = set(existing_df.get("Source File", pd.Series(dtype=str)).dropna().astype(str))
        image_paths = [path for path in image_paths if path.name not in done_files]
        print(f"Resume mode: {len(done_files)} drawings already OCR'd")

    print(f"Images to OCR: {len(image_paths)}")
    print(f"OCR confidence: {args.conf}")
    print()

    if not image_paths:
        print(f"No new drawings to OCR. Existing rows kept: {len(existing_rows)}")
        return

    rows, failed = run_measurement_extraction(
        image_paths=image_paths,
        confidence=args.conf,
        review_threshold=args.review_threshold,
        output_path=args.output,
        existing_rows=existing_rows,
        save_after_each=args.resume,
    )

    print()
    print(f"Saved measurement workbook: {args.output}")
    print(f"Saved debug images: {DEBUG_MEASUREMENT_DETECTION_DIR}")
    print(f"Total measurement candidates: {len(rows)}")
    print(f"Failed images: {', '.join(failed) if failed else 'None'}")


if __name__ == "__main__":
    main()
