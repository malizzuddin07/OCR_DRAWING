import re
from pathlib import Path

import cv2

from config import DATASET_IMAGES_DIR
from measurement_extraction import extract_ocr_items_with_boxes


DIAMETER_LIKE_PATTERN = re.compile(r"(?:Ø|Ã˜|0)?\s*(\d{1,3}(?:\.\d+)?)", re.IGNORECASE)
TOLERANCE_PATTERN = re.compile(r"([+\-±Â±]\s*\d+(?:\.\d+)?)")
GDT_DATUM_PATTERN = re.compile(r"\b([A-Z])\b")
THREAD_PATTERN = re.compile(r"\b(M\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?)\b", re.IGNORECASE)
DEPTH_PATTERN = re.compile(
    r"(?:DEPTH|DP|DPT|深さ|▽|⌵|[-\s][TV])\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


def clean_text(text):
    text = str(text or "")
    text = text.replace("Ã˜", "Ø").replace("Â±", "±")
    text = text.replace("'", "").replace("`", "")
    return " ".join(text.split())


def clamp(value, low, high):
    return max(low, min(high, int(value)))


def crop_around_item(image, item):
    image_height, image_width = image.shape[:2]
    x = int(item["X"])
    y = int(item["Y"])
    width = int(item["Width"])
    height = int(item["Height"])

    item_type = str(item.get("Type", item.get("Item Type", "")))
    operation = str(item.get("Operation", ""))
    spec = str(item.get("Specification", ""))

    if "Thread" in item_type or "M" in spec:
        pad_left, pad_right, pad_top, pad_bottom = 180, 260, 80, 90
    elif "GDT" in item_type or "GD&T" in operation:
        pad_left, pad_right, pad_top, pad_bottom = 130, 220, 70, 70
    elif height > width * 1.4:
        pad_left, pad_right, pad_top, pad_bottom = 90, 90, 150, 150
    else:
        pad_left, pad_right, pad_top, pad_bottom = 100, 150, 80, 80

    x1 = clamp(x - pad_left, 0, image_width)
    y1 = clamp(y - pad_top, 0, image_height)
    x2 = clamp(x + width + pad_right, 0, image_width)
    y2 = clamp(y + height + pad_bottom, 0, image_height)
    return image[y1:y2, x1:x2], (x1, y1, x2, y2)


def ocr_crop_variants(ocr, crop, item):
    variants = [("normal", crop)]
    if int(item.get("Height", 0)) > int(item.get("Width", 0)) * 1.2 or should_try_diameter_refine(item):
        variants.extend(
            [
                ("rotated_cw", cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)),
                ("rotated_ccw", cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)),
            ]
        )
    texts = []

    for orientation, variant in variants:
        enlarged = cv2.resize(variant, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        try:
            result = ocr.predict(enlarged)
        except Exception:
            continue
        items = extract_ocr_items_with_boxes(result)
        for item in items:
            text = clean_text(item.get("text", ""))
            if text:
                texts.append({"text": text, "confidence": item.get("confidence", 0), "orientation": orientation})

    return texts


def joined_text(ocr_items):
    return " ".join(item["text"] for item in ocr_items if item.get("text"))


def unique_parts(parts):
    output = []
    for part in parts:
        part = clean_text(part)
        if part and part not in output:
            output.append(part)
    return output


def refine_diameter_spec(current_spec, text):
    current_spec = clean_text(current_spec)
    text = clean_text(text)
    search_text = f"{current_spec} {text}"

    number_matches = DIAMETER_LIKE_PATTERN.findall(current_spec)
    if not number_matches:
        number_matches = DIAMETER_LIKE_PATTERN.findall(search_text)
    number = None
    for candidate in number_matches:
        try:
            value = float(candidate)
        except ValueError:
            continue
        if value >= 1:
            number = candidate
            break

    if not number:
        return current_spec

    current_tolerances = unique_parts(TOLERANCE_PATTERN.findall(current_spec))
    tolerance_source = current_tolerances or unique_parts(TOLERANCE_PATTERN.findall(search_text))

    tolerances = []
    for tolerance in tolerance_source:
        numeric = re.search(r"\d+(?:\.\d+)?", tolerance)
        if not numeric:
            continue
        try:
            numeric_value = float(numeric.group(0))
        except ValueError:
            continue
        if numeric_value == 0 or numeric_value > 0.5:
            continue
        tolerances.append(tolerance)

    lower_zero = bool(re.search(r"(?:^|\s)0(?:\s|$)", search_text))
    spec = f"Ø{number}"
    if tolerances:
        spec += " " + " ".join(tolerances[:2])
    if lower_zero and "/ 0" not in spec and len(tolerances) == 1:
        spec += " / 0"
    return spec


def infer_vertical_diameter_spec(current_spec, item):
    spec = clean_text(current_spec)
    if spec.startswith("Ø"):
        return spec

    orientation = str(item.get("Orientation", ""))
    if not orientation.startswith("rotated"):
        return spec

    match = re.match(r"^(\d{1,3}(?:\.\d+)?)\s*\+\s*(0?\.\d+)(?:\s*/\s*0)?$", spec)
    if not match:
        return spec

    nominal = match.group(1)
    upper_tolerance = match.group(2)
    try:
        nominal_value = float(nominal)
    except ValueError:
        return spec
    if nominal_value < 10:
        return spec
    return f"Ø{nominal} +{upper_tolerance} / 0"


def refine_gdt_spec(current_spec, text):
    current_spec = clean_text(current_spec)
    text = clean_text(text)
    combined = f"{current_spec} {text}"

    datum_candidates = [match for match in GDT_DATUM_PATTERN.findall(combined) if match in {"X", "Y", "Z"}]
    tolerances = unique_parts(re.findall(r"\b0\.\d+\b", combined))

    if "⊥" in current_spec or "âŠ¥" in current_spec:
        symbol = "⊥"
    elif "//" in current_spec:
        symbol = "//"
    else:
        symbol = current_spec.split()[0] if current_spec else ""

    parts = [symbol]
    if tolerances:
        parts.append(tolerances[0])
    if "Y" in datum_candidates:
        parts.append("Y")
    elif "X" in datum_candidates:
        parts.append("X")
    elif "Z" in datum_candidates:
        parts.append("Z")
    return " ".join(part for part in parts if part) or current_spec


def refine_thread_spec(current_spec, text):
    current_spec = clean_text(current_spec)
    text = clean_text(text)
    combined = f"{current_spec} {text}"

    thread_match = THREAD_PATTERN.search(combined)
    thread = clean_text(thread_match.group(1)) if thread_match else current_spec
    depth_match = DEPTH_PATTERN.search(combined)
    if depth_match:
        return f"{thread} depth {depth_match.group(1)}"
    return thread


def should_try_diameter_refine(item):
    spec = clean_text(item.get("Specification", ""))
    item_type = str(item.get("Type", item.get("Item Type", "")))
    orientation = str(item.get("Orientation", ""))
    nominal_match = re.match(r"^(\d{1,3}(?:\.\d+)?)\s*\+", spec)
    nominal_value = None
    if nominal_match:
        try:
            nominal_value = float(nominal_match.group(1))
        except ValueError:
            nominal_value = None
    return (
        spec.startswith("Ø")
        or spec.startswith("0")
        or item_type.startswith("Diameter")
        or (
            item_type == "Nom + Tol"
            and orientation.startswith("rotated")
            and "+" in spec
            and nominal_value is not None
            and nominal_value >= 10
        )
    )


def should_refine_item(item):
    item_type = str(item.get("Type", item.get("Item Type", "")))
    operation = str(item.get("Operation", ""))
    spec = clean_text(item.get("Specification", ""))
    return (
        "GDT" in item_type
        or "GD&T" in operation
        or "Thread" in item_type
        or "M" in spec
        or should_try_diameter_refine(item)
    )


def refine_item(item, ocr, image):
    if not should_refine_item(item):
        return item

    crop, _ = crop_around_item(image, item)
    if crop.size == 0:
        return item

    ocr_items = ocr_crop_variants(ocr, crop, item)
    text = joined_text(ocr_items)
    refined = dict(item)
    current_spec = refined.get("Specification", "")
    item_type = str(refined.get("Type", refined.get("Item Type", "")))
    operation = str(refined.get("Operation", ""))

    if not text:
        pass
    elif "GDT" in item_type or "GD&T" in operation:
        refined["Specification"] = refine_gdt_spec(current_spec, text)
    elif "Thread" in item_type or "M" in str(current_spec):
        refined["Specification"] = refine_thread_spec(current_spec, text)
    elif re.search(r"\b0\.\d+\b", str(current_spec)) and re.search(r"\b[XYZ]\b", text):
        refined["Operation"] = "GD&T"
        refined["Item Type"] = "GDT Frame"
        refined["Specification"] = refine_gdt_spec(f"// {current_spec}", text)
    elif should_try_diameter_refine(refined):
        refined_spec = refine_diameter_spec(current_spec, text)
        if refined_spec.startswith("Ø"):
            refined["Specification"] = refined_spec
            has_tolerance = any(token in refined_spec for token in ["+", "-", "±"])
            refined["Item Type"] = "Diameter Nom + Tol" if has_tolerance else "Diameter"

    inferred_diameter = infer_vertical_diameter_spec(refined.get("Specification", ""), refined)
    if inferred_diameter != refined.get("Specification", ""):
        refined["Specification"] = inferred_diameter
        refined["Item Type"] = "Diameter Nom + Tol"
        refined["Needs Review"] = "YES"
        reason = clean_text(refined.get("Review Reason", ""))
        inferred_reason = "Inferred diameter symbol/lower zero from rotated tolerance callout"
        refined["Review Reason"] = "; ".join(unique_parts([reason, inferred_reason]))

    refined["Local OCR Text"] = text
    return refined


def refine_callouts(items, ocr):
    image_cache = {}
    refined_items = []

    for item in items:
        source_file = item["Source File"]
        if source_file not in image_cache:
            image_cache[source_file] = cv2.imread(str(DATASET_IMAGES_DIR / source_file))

        image = image_cache[source_file]
        if image is None:
            refined_items.append(item)
            continue

        refined_items.append(refine_item(item, ocr, image))

    return refined_items

