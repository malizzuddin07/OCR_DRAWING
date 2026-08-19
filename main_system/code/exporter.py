import re
from pathlib import Path

import pandas as pd

from ai_parser import extract_filename_reference
from config import (
    BASE_DIR,
    EXTRACTED_DATA_OUTPUT_PATH,
    FIELD_NAMES,
    IMPORTANT_FIELD_NAMES,
    VERIFICATION_OUTPUT_PATH,
)


def sanitize_excel_text(value):
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)

    if text.startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


def sanitize_dataframe_for_excel(df):
    return df.map(sanitize_excel_text)


def normalize_identifier(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def compare_with_reference(ai_value, reference_value):
    ai_norm = normalize_identifier(ai_value)
    ref_norm = normalize_identifier(reference_value)

    if not ref_norm:
        return "NO FILENAME REF"

    if not ai_norm:
        return "AI BLANK"

    if ai_norm == ref_norm:
        return "OK"

    return "MISMATCH"


def choose_suggested_value(ai_value, filename_value):
    if filename_value:
        return filename_value

    return ai_value or ""


def create_verification_row(
    filename,
    messy_text,
    ocr_score,
    ocr_time,
    ai_time,
    status,
    data,
    diagnostics=None,
):
    diagnostics = diagnostics or {}
    filename_drawing_number, filename_revision = extract_filename_reference(filename)
    drawing_number_check = compare_with_reference(
        data.get("Drawing Number", ""),
        filename_drawing_number,
    )
    revision_check = compare_with_reference(
        data.get("Revision", ""),
        filename_revision,
    )

    suggested_drawing_number = choose_suggested_value(
        data.get("Drawing Number", ""),
        filename_drawing_number,
    )
    suggested_revision = choose_suggested_value(
        data.get("Revision", ""),
        filename_revision,
    )

    review_reasons = []
    if status == "REVIEW":
        review_reasons.append("Low OCR score")

    if drawing_number_check in {"AI BLANK", "MISMATCH"}:
        review_reasons.append(f"Drawing Number {drawing_number_check}")

    if revision_check in {"AI BLANK", "MISMATCH"}:
        review_reasons.append(f"Revision {revision_check}")

    for field in IMPORTANT_FIELD_NAMES:
        if not data.get(field, ""):
            review_reasons.append(f"{field} blank")

    row = {
        "Source File": filename,
        "OCR Score": round(ocr_score, 4),
        "Status": status,
        "Needs Review": "YES" if review_reasons else "NO",
        "Review Reason": "; ".join(review_reasons),
        "OCR Time (s)": round(ocr_time, 2),
        "AI Time (s)": round(ai_time, 2),
        "Crop Method": diagnostics.get("crop_method", ""),
        "Crop Source": diagnostics.get("crop_source", ""),
        "Crop Confidence": round(float(diagnostics.get("crop_confidence", 0) or 0), 4),
        "Crop Box": format_crop_box(diagnostics.get("crop_box", "")),
        "Crop Keyword Hits": diagnostics.get("crop_keyword_hits", ""),
        "Crop Identifier Hits": diagnostics.get("crop_identifier_hits", ""),
        "Crop Candidate Count": diagnostics.get("crop_candidate_count", ""),
        "Layout Candidate Count": diagnostics.get("layout_candidate_count", ""),
        "OCR Variant": diagnostics.get("ocr_variant", ""),
        "OCR Selection Score": round(float(diagnostics.get("ocr_selection_score", 0) or 0), 4),
        "OCR Line Count": diagnostics.get("ocr_line_count", ""),
        "OCR Text Length": diagnostics.get("ocr_text_length", ""),
        "Filename Drawing Number": filename_drawing_number,
        "Filename Revision": filename_revision,
        "Drawing Number Check": drawing_number_check,
        "Revision Check": revision_check,
        "Suggested Drawing Number": suggested_drawing_number,
        "Suggested Revision": suggested_revision,
        "Original OCR Text": messy_text,
    }

    for field in FIELD_NAMES:
        row[f"AI {field}"] = data.get(field, "")
        row[f"Human {field}"] = ""

    return row


def format_crop_box(crop_box):
    if not crop_box:
        return ""

    return ",".join(str(value) for value in crop_box)


def create_extracted_data_rows(verification_rows):
    extracted_rows = []

    for row in verification_rows:
        extracted_row = {}

        for field in FIELD_NAMES:
            human_value = row.get(f"Human {field}", "")
            ai_value = row.get(f"AI {field}", "")
            suggested_value = row.get(f"Suggested {field}", "")
            extracted_row[field] = human_value or suggested_value or ai_value

        extracted_row["Source File"] = row["Source File"]
        extracted_rows.append(extracted_row)

    return extracted_rows


def has_non_english_characters(value):
    text = str(value or "")
    return any(ord(character) > 127 for character in text)


def is_english_compatible(value):
    text = str(value or "").strip()
    return bool(text) and not has_non_english_characters(text)


def apply_legacy_english_fallback(extracted_rows):
    legacy_path = BASE_DIR / "extracted_data.xlsx"
    if not legacy_path.exists() or Path(EXTRACTED_DATA_OUTPUT_PATH) == legacy_path:
        return extracted_rows

    try:
        legacy_df = pd.read_excel(legacy_path, dtype=str).fillna("")
    except Exception:
        return extracted_rows

    if "Source File" not in legacy_df.columns:
        return extracted_rows

    legacy_by_source = legacy_df.set_index("Source File")

    for row in extracted_rows:
        source_file = row.get("Source File", "")
        if source_file not in legacy_by_source.index:
            continue

        for field in FIELD_NAMES:
            current_value = row.get(field, "")
            legacy_value = legacy_by_source.at[source_file, field] if field in legacy_by_source.columns else ""
            if has_non_english_characters(current_value) and is_english_compatible(legacy_value):
                row[field] = legacy_value

    return extracted_rows


def save_workbooks(verification_rows):
    verification_df = pd.DataFrame(verification_rows)
    extracted_rows = create_extracted_data_rows(verification_rows)
    extracted_rows = apply_legacy_english_fallback(extracted_rows)
    extracted_df = pd.DataFrame(extracted_rows)
    verification_df = sanitize_dataframe_for_excel(verification_df)
    extracted_df = sanitize_dataframe_for_excel(extracted_df)

    verification_df.to_excel(VERIFICATION_OUTPUT_PATH, index=False)
    extracted_df.to_excel(EXTRACTED_DATA_OUTPUT_PATH, index=False)
