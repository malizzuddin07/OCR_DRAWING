import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

import cv2
from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parents[1]
WEBAPP_DIR = BASE_DIR / "webapp"
STORAGE_DIR = WEBAPP_DIR / "storage"
GENERATED_DIR = BASE_DIR / "generated_jobs"
JOBS_DIR = GENERATED_DIR / "jobs"
STATIC_DIR = WEBAPP_DIR / "static"
PRIVATE_DATA_DIR = BASE_DIR / "private_data"
JOB_SNAPSHOTS_DIR = PRIVATE_DATA_DIR / "job_snapshots"
APPROVALS_DIR = PRIVATE_DATA_DIR / "approvals"
GOLDEN_TESTS_DIR = BASE_DIR / "golden_tests"

sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "code"))

from api_bridge import process_single_drawing_for_web  # noqa: E402
from auto_ballooning import (  # noqa: E402
    build_balloon_layout_diagnostics,
    draw_balloons,
    extract_multiplier,
    infer_equipment,
    infer_operation,
    normalize_depth_display_text,
    normalize_fa_export_row,
    parse_counterbore_rows,
    parse_tolerance,
    save_fa_workbook,
    save_pdf_from_image,
    split_symbol_and_dimension,
)
from compare_golden_output import (  # noqa: E402
    compare_characteristic_geometry,
    compare_rows,
    load_characteristic_records,
    read_fa_document,
)
from drawing_metadata import DrawingMetadata, parse_metadata_from_filename  # noqa: E402
from measurement_extraction import classify_measurement, create_measurement_row, extract_ocr_items_with_boxes  # noqa: E402
from model_registry import load_registry  # noqa: E402
from vision_tools import create_paddle_ocr, create_paddle_text_recognizer  # noqa: E402
from webapp.approval_data import (  # noqa: E402
    approval_content_hash,
    change_counts,
    compare_characteristics,
    item_box,
    valid_identifier,
)


app = FastAPI(title="AI Engineering Drawing Extraction")

cors_origins = [
    origin.strip()
    for origin in os.getenv("OCR_DRAWING_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
JOB_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
APPROVALS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")

JOB_STATUS = {}
CANCEL_REQUESTS = set()


@app.get("/api/models/status")
async def model_status():
    registry = load_registry()
    models = registry.get("models", {})
    return {
        "status": "success",
        "active_model": registry.get("active_model", ""),
        "rollback_model": registry.get("rollback_model", ""),
        "candidate_models": sorted(
            model_id
            for model_id, record in models.items()
            if record.get("status") == "candidate"
        ),
        "successful_promotions": int(registry.get("successful_promotions", 0) or 0),
        "automatic_promotion_enabled": bool(registry.get("automatic_promotion_enabled", False)),
        "training_enabled": False,
        "training_note": "Automatic training remains disabled until a candidate passes the strict five-drawing promotion gate.",
    }


def url_for_path(path):
    path = Path(path).resolve()
    storage_root = STORAGE_DIR.resolve()
    generated_root = GENERATED_DIR.resolve()
    try:
        relative = path.relative_to(storage_root)
        return "/storage/" + relative.as_posix()
    except ValueError:
        relative = path.relative_to(generated_root)
        return "/generated/" + relative.as_posix()


def job_path(job_id):
    return JOBS_DIR / job_id


def json_safe(value):
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_path(job_id):
    return JOB_SNAPSHOTS_DIR / f"{job_id}.json"


def persist_job_snapshot(job_id, result):
    path = snapshot_path(job_id)
    if path.exists():
        return path
    current_job = job_path(job_id)
    source_file = source_upload_file(current_job)
    snapshot = {
        "job_id": job_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source_filename": source_file.name if source_file else "",
        "source_sha256": file_sha256(source_file) if source_file and source_file.exists() else "",
        "original_items": json_safe(result.get("preview_rows", [])),
        "original_metadata": json_safe(result.get("metadata", DrawingMetadata())),
        "detector_diagnostics": json_safe(result.get("detector_diagnostics", {})),
        "titleblock_diagnostics": json_safe(result.get("titleblock_diagnostics", {})),
        "processing_timings": json_safe(result.get("processing_timings", {})),
    }
    write_json_atomic(path, snapshot)
    return path


def load_job_snapshot(job_id):
    path = snapshot_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def approval_record_path(approval_id):
    return APPROVALS_DIR / approval_id / "approval.json"


def load_approval_record(approval_id):
    if not valid_identifier(approval_id, 16):
        return None
    path = approval_record_path(approval_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def approval_records_for_source(source_sha256):
    records = []
    for approval_dir in APPROVALS_DIR.iterdir():
        if not approval_dir.is_dir() or not valid_identifier(approval_dir.name, 16):
            continue
        record = load_approval_record(approval_dir.name)
        if record and str(record.get("source", {}).get("sha256", "")).lower() == str(source_sha256).lower():
            records.append(record)
    return sorted(
        records,
        key=lambda record: (
            int(record.get("approval_revision", 1) or 1),
            str(record.get("created_at", "")),
        ),
    )


def approval_response(record, duplicate=False):
    approval_id = record["approval_id"]
    return {
        "status": "approved",
        "duplicate": duplicate,
        "approval_id": approval_id,
        "approval_revision": int(record.get("approval_revision", 1) or 1),
        "supersedes_approval_id": record.get("supersedes_approval_id", ""),
        "message": (
            "This exact approval already exists."
            if duplicate
            else "Corrected approval revision saved; the earlier approval remains in history."
            if record.get("supersedes_approval_id")
            else "Drawing approved and saved."
        ),
        "change_counts": record.get("change_counts", {}),
        "learning_status": "approved_not_trained",
        "pdf_url": f"/api/approvals/{approval_id}/pdf",
        "excel_url": f"/api/approvals/{approval_id}/excel",
        "package_url": f"/api/approvals/{approval_id}/package",
        "package_filename": record.get("package_filename", "Approved_Drawing.zip"),
    }


def build_metadata(posted_metadata, current_job):
    posted_metadata = posted_metadata or {}
    upload_files = list((current_job / "upload").glob("*"))
    metadata = DrawingMetadata(
        part_number=str(posted_metadata.get("part_number", "") or ""),
        drawing_number=str(posted_metadata.get("drawing_number", "") or ""),
        revision=str(posted_metadata.get("revision", "") or ""),
        material=str(posted_metadata.get("material", "") or ""),
        part_name=str(posted_metadata.get("part_name", "") or ""),
        general_tolerances=dict(posted_metadata.get("general_tolerances", {}) or {}),
    )
    if upload_files:
        filename_metadata = parse_metadata_from_filename(upload_files[0])
        metadata = DrawingMetadata(
            part_number=metadata.part_number or filename_metadata.part_number,
            drawing_number=metadata.drawing_number or filename_metadata.drawing_number,
            revision=metadata.revision or filename_metadata.revision,
            material=metadata.material or filename_metadata.material,
            part_name=metadata.part_name or filename_metadata.part_name,
            general_tolerances=metadata.general_tolerances or filename_metadata.general_tolerances,
        )
    return metadata


def source_upload_file(current_job):
    upload_files = list((current_job / "upload").glob("*"))
    return upload_files[0] if upload_files else None


def normalise_corrected_items(items):
    normalised = []
    for index, item in enumerate(items or [], start=1):
        row = dict(item or {})
        row.setdefault("Source File", "")
        row.setdefault("Operation", "")
        row.setdefault("Specification", row.get("Dimension", row.get("VALUE", "")))
        row.setdefault("Symbol", row.get("SYMBOL", row.get("Report Symbol", row.get("Symbol", ""))))
        row.setdefault("Report Symbol", row.get("SYMBOL", row.get("Symbol", "")))
        row.setdefault("Dimension", row.get("VALUE", ""))
        row.setdefault("Nominal", row.get("Dimension", ""))
        row.setdefault("Tolerance -", "")
        row.setdefault("Tolerance +", "")
        row.setdefault("MIN", "")
        row.setdefault("MAX", "")
        row.setdefault("Equipment", "")
        row.setdefault("Measurement Type", "manual")
        row.setdefault("Needs Review", "")
        row.setdefault("Review Reason", row.get("REMARK", ""))
        row.setdefault("AI Confidence", "")
        row.setdefault("X", 0)
        row.setdefault("Y", 0)
        row.setdefault("Width", 0)
        row.setdefault("Height", 0)
        row.setdefault("Display Balloon No", display_balloon_number(row.get("Balloon No", str(index))))
        row.setdefault("Balloon Size", row.get("Balloon Size", "1"))
        row.setdefault("Balloon Rotation", row.get("Balloon Rotation", "0"))
        row["Dimension"] = normalize_depth_display_text(row.get("Dimension", ""))
        depth_match = re.fullmatch(
            r"\s*(?:DEPTH|DP)\s*(\d+(?:\.\d+)?)\s*",
            str(row.get("Dimension", "")),
            re.IGNORECASE,
        )
        if depth_match:
            depth_value = depth_match.group(1)
            parsed_nominal, parsed_minus, parsed_plus, parsed_minimum, parsed_maximum = parse_tolerance(
                depth_value,
                apply_general=True,
            )
            try:
                nominal_matches = float(row.get("Nominal", "")) == float(parsed_nominal)
            except (TypeError, ValueError):
                nominal_matches = False
            if not nominal_matches:
                # A reviewer may correct OCR text from, for example, "1" to
                # "DEPTH 15". Never retain derived limits from the stale OCR
                # value in the approved Excel record.
                row["Nominal"] = parsed_nominal
                row["Tolerance -"] = parsed_minus
                row["Tolerance +"] = parsed_plus
                row["MIN"] = parsed_minimum
                row["MAX"] = parsed_maximum
        if re.fullmatch(r"\s*(?:DEPTH|DP)\s*\d+(?:\.\d+)?\s*", str(row.get("Specification", "")), re.IGNORECASE):
            row["Specification"] = normalize_depth_display_text(row.get("Specification", ""))
        if not str(row.get("Balloon No", "")).strip():
            row["Balloon No"] = str(index)
            row["Display Balloon No"] = str(index)
        else:
            row["Display Balloon No"] = display_balloon_number(row.get("Balloon No", ""))
        normalised.append(row)
    normalise_multiplier_subrows(normalised)
    assign_compound_sub_balloon_numbers(normalised)
    return sorted(normalised, key=corrected_balloon_sort_key)


def normalise_multiplier_subrows(rows):
    """Keep multiplier subrows as repeated single characteristics.

    A drawing callout such as ``4X C1`` uses one physical balloon but four
    inspection rows.  The original callout stays in ``Specification`` for
    traceability; every subrow stores the single characteristic (``C``/``1``)
    plus explicit multiplier metadata.  This also repairs rows created with
    the browser's manual ``+ Sub-row`` fallback.
    """
    groups = {}
    for row in rows:
        balloon_text = str(row.get("Balloon No", "")).strip()
        match = re.fullmatch(r"(\d+)(?:\.(\d+))?", balloon_text)
        if not match:
            continue
        main = match.group(1)
        groups.setdefault(main, []).append(row)

    for group in groups.values():
        if len(group) <= 1:
            continue

        multiplier_count = 1
        clean_specification = ""
        multiplier_callout = ""
        template = None
        for row in group:
            for candidate in (
                row.get("Specification", ""),
                f"{row.get('Report Symbol', '')}{row.get('Dimension', '')}",
                f"{row.get('Symbol', '')}{row.get('Dimension', '')}",
            ):
                count, clean = extract_multiplier(candidate)
                if count > 1:
                    multiplier_count = count
                    clean_specification = clean
                    multiplier_callout = f"{count}X {clean}"
                    template = row
                    break
            if multiplier_count > 1:
                break

        # Do not silently change a reviewer-created group when its row count
        # does not agree with the multiplier printed on the drawing.
        if multiplier_count <= 1 or multiplier_count != len(group):
            continue

        measurement_type = str((template or {}).get("Measurement Type", "manual"))
        symbol, dimension = split_symbol_and_dimension(clean_specification, measurement_type)
        dimension = dimension or clean_specification
        original_specification = multiplier_callout

        for index, row in enumerate(group, start=1):
            row["Symbol"] = symbol
            row["Report Symbol"] = symbol
            row["Dimension"] = dimension
            row["Multiplier Count"] = multiplier_count
            row["Multiplier Index"] = index
            row["Subrow Count"] = multiplier_count
            row["Subrow Index"] = index
            if original_specification:
                row["Specification"] = original_specification


def assign_compound_sub_balloon_numbers(rows):
    """Give true multi-characteristic rows stable decimal suffixes.

    Compound rows share one physical balloon frame, but Excel and the review
    table need unique identities such as 11.1 and 11.2.  Only rows explicitly
    marked as compound, or rows sharing the same non-empty crop geometry, are
    converted.  Unrelated duplicate numbers remain visible for QC review.
    """
    groups = {}
    for row in rows:
        text = str(row.get("Balloon No", "")).strip()
        match = re.fullmatch(r"(\d+)", text)
        if match:
            groups.setdefault(match.group(1), []).append(row)

    for main, group in groups.items():
        if len(group) <= 1:
            continue
        explicitly_compound = any(int(row.get("Subrow Count", 1) or 1) > 1 for row in group)
        valid_boxes = [
            (
                int(row.get("X", 0) or 0),
                int(row.get("Y", 0) or 0),
                int(row.get("Width", 0) or 0),
                int(row.get("Height", 0) or 0),
            )
            for row in group
            if int(row.get("Width", 0) or 0) > 0 and int(row.get("Height", 0) or 0) > 0
        ]
        shares_one_crop = len(valid_boxes) == len(group) and len(set(valid_boxes)) == 1
        if not explicitly_compound and not shares_one_crop:
            continue

        for index, row in enumerate(group, start=1):
            row["Balloon No"] = f"{main}.{index}"
            row["Display Balloon No"] = main
            row["Subrow Count"] = len(group)
            row["Subrow Index"] = index


def corrected_balloon_sort_key(row):
    """Sort corrected rows by numeric balloon number, including subrows."""
    text = str(row.get("Balloon No", "")).strip()
    match = re.match(r"^(\d+)(?:\.(\d+))?$", text)
    if match:
        main = int(match.group(1))
        suffix = int(match.group(2) or 0)
        return 0, main, suffix
    return 1, float("inf"), text


def display_balloon_number(value):
    text = str(value or "").strip()
    match = re.match(r"^(\d+)(?:\.\d+)?$", text)
    return match.group(1) if match else text


def golden_manifest_for_source_hash(source_hash):
    """Return the approved manifest for an exact source drawing, if known."""
    wanted = str(source_hash or "").strip().upper()
    if not wanted or not GOLDEN_TESTS_DIR.is_dir():
        return None
    for manifest_path in GOLDEN_TESTS_DIR.glob("*_golden_manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        expected_hash = str((manifest.get("source_pdf") or {}).get("sha256", "")).strip().upper()
        if manifest.get("status") == "approved" and expected_hash == wanted:
            return manifest
    return None


def evaluate_job_quality(job_id, items):
    """Evaluate live corrected rows before calling a drawing approval-ready."""
    current_job = job_path(job_id)
    normalised_items = normalise_corrected_items(items)
    issues = []

    missing_boxes = []
    for row in normalised_items:
        balloon_no = str(row.get("Balloon No", "")).strip()
        if balloon_no.startswith("N"):
            continue
        if item_box(row) is None:
            missing_boxes.append(balloon_no or "?")
    if missing_boxes:
        issues.append(
            {
                "type": "missing_balloon_box",
                "count": len(missing_boxes),
                "balloons": missing_boxes[:20],
                "message": "Some characteristics do not have a valid balloon box.",
            }
        )

    original_image_path = current_job / "original.png"
    if original_image_path.is_file():
        image = cv2.imread(str(original_image_path))
        if image is not None:
            layout = build_balloon_layout_diagnostics(normalised_items, image.shape)
            layout_issues = list(layout.get("issues", []))
            if layout_issues:
                issues.append(
                    {
                        "type": "balloon_layout_overlap",
                        "count": len(layout_issues),
                        "examples": layout_issues[:10],
                        "message": "Balloon frames or circles still overlap.",
                    }
                )

    source_file = source_upload_file(current_job)
    source_hash = file_sha256(source_file) if source_file and source_file.is_file() else ""
    manifest = golden_manifest_for_source_hash(source_hash)
    golden_status = "not_applicable"
    if manifest is not None:
        golden_status = "passed"
        expected_path = GOLDEN_TESTS_DIR / str((manifest.get("expected_excel") or {}).get("path", ""))
        if not expected_path.is_file():
            golden_status = "error"
            issues.append(
                {
                    "type": "golden_reference_missing",
                    "message": "The approved golden Excel reference is missing.",
                }
            )
        else:
            expected = read_fa_document(expected_path)
            current_rows = [normalize_fa_export_row(row) for row in normalised_items]
            differences = compare_rows(expected["rows"], current_rows)
            geometry_differences = []
            expected_geometry_path = GOLDEN_TESTS_DIR / str(
                (manifest.get("expected_characteristics") or {}).get("path", "")
            )
            if expected_geometry_path.is_file():
                geometry_differences = compare_characteristic_geometry(
                    load_characteristic_records(expected_geometry_path),
                    normalised_items,
                )
            else:
                geometry_differences = [{"type": "missing_approved_geometry"}]
            expected_main = int(manifest.get("main_balloons", 0) or 0)
            current_main = {
                str(row.get("BALLOON NO", "")).split(".", 1)[0]
                for row in current_rows
                if str(row.get("BALLOON NO", "")).split(".", 1)[0].isdigit()
            }
            count_matches = len(current_rows) == len(expected["rows"])
            main_matches = not expected_main or len(current_main) == expected_main
            if differences or geometry_differences or not count_matches or not main_matches:
                golden_status = "failed"
                issues.append(
                    {
                        "type": "golden_output_mismatch",
                        "drawing_number": manifest.get("drawing_number", ""),
                        "expected_characteristics": len(expected["rows"]),
                        "current_characteristics": len(current_rows),
                        "expected_main_balloons": expected_main,
                        "current_main_balloons": len(current_main),
                        "difference_count": len(differences),
                        "difference_examples": differences[:10],
                        "geometry_difference_count": len(geometry_differences),
                        "geometry_difference_examples": geometry_differences[:10],
                        "message": "This known golden drawing does not match its approved result.",
                    }
                )

    return {
        "status": "passed" if not issues else "needs_review",
        "approval_ready": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "golden_status": golden_status,
    }


def renumber_corrected_items(items):
    for index, row in enumerate(items or [], start=1):
        row["Balloon No"] = str(index)
        row["Display Balloon No"] = str(index)
    return items


def parse_box_payload(data):
    box = data.get("box") or data
    x = int(float(box.get("x", box.get("X", 0)) or 0))
    y = int(float(box.get("y", box.get("Y", 0)) or 0))
    width = int(float(box.get("width", box.get("Width", 0)) or 0))
    height = int(float(box.get("height", box.get("Height", 0)) or 0))
    return x, y, width, height


def rotate_image_bound(image, angle):
    """Rotate a crop without cutting off diagonal engineering text."""
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cosine = abs(matrix[0, 0])
    sine = abs(matrix[0, 1])
    rotated_width = max(1, int(height * sine + width * cosine))
    rotated_height = max(1, int(height * cosine + width * sine))
    matrix[0, 2] += rotated_width / 2.0 - center[0]
    matrix[1, 2] += rotated_height / 2.0 - center[1]
    return cv2.warpAffine(
        image,
        matrix,
        (rotated_width, rotated_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def dominant_diagonal_angle(image):
    """Return the strongest diagonal guide/text-line angle in a manual crop."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(gray, 50, 150)
    height, width = gray.shape[:2]
    minimum_length = max(24, int(max(height, width) * 0.35))
    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=max(20, minimum_length // 3),
        minLineLength=minimum_length,
        maxLineGap=max(8, minimum_length // 10),
    )
    if lines is None:
        return None

    candidates = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        delta_x = float(x2 - x1)
        delta_y = float(y2 - y1)
        length = (delta_x * delta_x + delta_y * delta_y) ** 0.5
        angle = float(math.degrees(math.atan2(delta_y, delta_x)))
        if 20.0 <= abs(angle) <= 70.0:
            candidates.append((length, angle))
    return max(candidates, default=(0.0, None), key=lambda candidate: candidate[0])[1]


def normalise_manual_recognition_text(value):
    """Repair only verified, tightly-scoped engineering OCR ligatures.

    PP-OCRv5 can merge the adjacent glyphs ``X`` and ``C`` in a deskewed
    multiplier callout into U+8043.  Restrict the repair to the exact pattern
    ``count + ligature + numeric dimension`` so Japanese drawing text is not
    changed globally.
    """
    compact = re.sub(r"\s+", "", str(value or "")).upper().replace("×", "X")
    multiplier_chamfer = re.fullmatch(r"(\d{1,2})\u8043(\d+(?:\.\d+)?)", compact)
    if multiplier_chamfer:
        return f"{multiplier_chamfer.group(1)}XC{multiplier_chamfer.group(2)}"
    return compact


def is_meaningful_manual_ocr_text(value):
    """Reject OCR noise that contains no readable measurement character.

    A manual crop can include extension lines or part of a nearby symbol.  OCR
    may confidently return punctuation such as ``)`` for that line work.  Such
    punctuation is not a usable characteristic and must not outrank a lower
    confidence but valid numeric result such as ``25``.
    """
    text = normalise_manual_recognition_text(value)
    return bool(re.search(r"[A-Z0-9]", text))


def recognition_only_manual_candidate(image, crop_box, orientation):
    """Recognize a manually selected crop as one complete text line."""
    try:
        recognizer = create_paddle_text_recognizer()
    except Exception:
        return []

    x1, y1, x2, y2 = crop_box
    candidates = []
    variants = [(orientation, image)]
    # A dimension/extension line at the bottom of a tight manual crop can be
    # recognized as punctuation and hide otherwise clear digits (for example
    # ``25`` becoming ``)``). Keep the original pass, then add a conservative
    # bottom-line cleanup pass. This is local to user-drawn crops.
    trim_height = int(image.shape[0] * 0.82)
    if trim_height >= 8 and trim_height < image.shape[0]:
        variants.append((f"{orientation}_trim_bottom", image[:trim_height, :]))

    for variant_orientation, variant in variants:
        padded = cv2.copyMakeBorder(
            variant,
            30,
            30,
            30,
            30,
            cv2.BORDER_CONSTANT,
            value=(255, 255, 255),
        )
        for result in recognizer.predict(padded):
            text = normalise_manual_recognition_text(result.get("rec_text", ""))
            if not is_meaningful_manual_ocr_text(text):
                continue
            confidence = float(result.get("rec_score", 0) or 0)
            measurement_type, value = classify_measurement(text)
            if not measurement_type:
                continue
            multiplier_count, _ = extract_multiplier(value or text)
            item = {
                "text": text,
                "confidence": confidence,
                "box": (x1, y1, x2, y2),
                "orientation": variant_orientation,
            }
            candidates.append(
                (
                    confidence + (1.0 if multiplier_count > 1 else 0.0),
                    item,
                    measurement_type,
                    value,
                )
            )
    return candidates


def diagonal_manual_ocr_candidates(ocr, enlarged, crop_box, allow_angle_fallback=False):
    """Read a diagonal manual crop as complete horizontal text lines."""
    detected_angle = dominant_diagonal_angle(enlarged)
    angles = [detected_angle] if detected_angle is not None else []
    if not angles and allow_angle_fallback:
        # Very small crops may not contain a line long enough for Hough angle
        # detection. Test both common diagonal drawing orientations only when
        # the normal/full-line passes found no valid measurement.
        angles = [-45.0, 45.0]
    if not angles:
        return []

    try:
        recognizer = create_paddle_text_recognizer()
    except Exception:
        return []

    x1, y1, x2, y2 = crop_box
    candidates = []
    for angle in angles:
        rotated = rotate_image_bound(enlarged, angle)
        rotated_items = extract_ocr_items_with_boxes(ocr.predict(rotated))
        if not rotated_items:
            continue
        seen_bands = set()
        for detected in rotated_items:
            _, top, _, bottom = detected.get("box", (0, 0, 0, 0))
            line_height = max(1, int(bottom) - int(top))
            padding = max(8, int(line_height * 0.15))
            band_top = max(0, int(top) - padding)
            band_bottom = min(rotated.shape[0], int(bottom) + padding)
            band_key = (band_top, band_bottom)
            if band_bottom <= band_top or band_key in seen_bands:
                continue
            seen_bands.add(band_key)
            text_line = rotated[band_top:band_bottom, :]
            for result in recognizer.predict(text_line):
                text = normalise_manual_recognition_text(result.get("rec_text", ""))
                if not is_meaningful_manual_ocr_text(text):
                    continue
                confidence = float(result.get("rec_score", 0) or 0)
                measurement_type, value = classify_measurement(text)
                if not measurement_type:
                    continue
                multiplier_count, _ = extract_multiplier(value or text)
                completeness_bonus = 1.0 if multiplier_count > 1 else 0.0
                item = {
                    "text": text,
                    "confidence": confidence,
                    "box": (x1, y1, x2, y2),
                    "orientation": f"manual_crop_deskewed_{angle:.1f}",
                }
                candidates.append(
                    (confidence + completeness_bonus, item, measurement_type, value)
                )
    return candidates


def build_row_from_crop_ocr(job_id, original_image, crop_box, source_file):
    x, y, width, height = crop_box
    image_height, image_width = original_image.shape[:2]
    x1 = max(0, min(x, image_width - 1))
    y1 = max(0, min(y, image_height - 1))
    x2 = max(x1 + 1, min(x + width, image_width))
    y2 = max(y1 + 1, min(y + height, image_height))
    crop = original_image[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("Selected crop is empty.")

    scale = 2
    ocr = create_paddle_ocr()
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    raw_items = extract_ocr_items_with_boxes(ocr.predict(enlarged))

    candidates = []

    def joined_candidate(items, orientation):
        joined = " ".join(
            str(entry.get("text", "")).strip()
            for entry in sorted(
                items,
                key=lambda entry: (entry.get("box", (0, 0, 0, 0))[1], entry.get("box", (0, 0, 0, 0))[0]),
            )
            if entry.get("text")
        ).strip()
        if not is_meaningful_manual_ocr_text(joined):
            return None, joined
        joined_type, joined_value = classify_measurement(joined)
        if not joined_type:
            return None, joined
        confidence = max([float(entry.get("confidence", 0) or 0) for entry in items], default=0)
        return (
            confidence,
            {
                "text": joined,
                "confidence": confidence,
                "box": (x1, y1, x2, y2),
                "orientation": orientation,
            },
            joined_type,
            joined_value,
        ), joined

    joined_entry, joined_text = joined_candidate(raw_items, "manual_crop")
    if joined_entry:
        candidates.append(joined_entry)

    for item in raw_items:
        bx1, by1, bx2, by2 = item["box"]
        text = str(item.get("text", "")).strip()
        if not is_meaningful_manual_ocr_text(text):
            continue
        measurement_type, value = classify_measurement(text)
        if not measurement_type:
            continue
        mapped_item = {
            "text": text,
            "confidence": float(item.get("confidence", 0) or 0),
            "box": (
                int(x1 + bx1 / scale),
                int(y1 + by1 / scale),
                int(x1 + bx2 / scale),
                int(y1 + by2 / scale),
            ),
            "orientation": "manual_crop",
        }
        candidates.append((mapped_item["confidence"], mapped_item, measurement_type, value))

    # Detection can split or misread even a clean, tightly selected value.
    # Recognition-only OCR treats the complete selection as one text line and
    # reliably recovers examples such as a small horizontal "25".
    candidates.extend(
        recognition_only_manual_candidate(
            enlarged,
            (x1, y1, x2, y2),
            "manual_crop_full_line",
        )
    )

    # A valid partial token must not prevent diagonal full-callout OCR.  This
    # pass deskews the selected crop, recognizes complete text bands, and gives
    # a complete multiplier callout priority over a partial value such as C1.
    candidates.extend(
        diagonal_manual_ocr_candidates(
            ocr,
            enlarged,
            (x1, y1, x2, y2),
            allow_angle_fallback=not candidates,
        )
    )

    if not candidates:
        for orientation, rotated_crop in (
            ("manual_crop_rotated_cw", cv2.rotate(enlarged, cv2.ROTATE_90_CLOCKWISE)),
            ("manual_crop_rotated_ccw", cv2.rotate(enlarged, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ):
            rotated_items = extract_ocr_items_with_boxes(ocr.predict(rotated_crop))
            rotated_entry, rotated_text = joined_candidate(rotated_items, orientation)
            if rotated_text and not joined_text:
                joined_text = rotated_text
            if rotated_entry:
                candidates.append(rotated_entry)
                break

    if candidates:
        _, item, measurement_type, value = max(candidates, key=lambda entry: entry[0])
    else:
        if not is_meaningful_manual_ocr_text(joined_text):
            raise ValueError("No readable dimension or engineering symbol was found inside the selected box.")
        measurement_type, value = classify_measurement(joined_text)
        if not measurement_type:
            measurement_type = "manual"
            value = joined_text
        item = {
            "text": joined_text,
            "confidence": max([float(entry.get("confidence", 0) or 0) for entry in raw_items], default=0),
            "box": (x1, y1, x2, y2),
            "orientation": "manual_crop",
        }

    row = create_measurement_row(source_file, item, measurement_type, value, review_threshold=0.90)
    row["OCR Box"] = row.get("Box", "")
    row["X"] = x1
    row["Y"] = y1
    row["Width"] = x2 - x1
    row["Height"] = y2 - y1
    row["Box"] = f"{x1},{y1},{x2},{y2}"
    symbol, dimension = split_symbol_and_dimension(value or item["text"], measurement_type)
    nominal, minus, plus, min_value, max_value = parse_tolerance(value or item["text"], apply_general=True)
    row.update(
        {
            "Operation": infer_operation(measurement_type),
            "Specification": value or item["text"],
            "Symbol": symbol,
            "Report Symbol": symbol,
            "Dimension": dimension or nominal or value or item["text"],
            "Nominal": nominal,
            "Tolerance -": minus,
            "Tolerance +": plus,
            "MIN": min_value,
            "MAX": max_value,
            "Equipment": infer_equipment(measurement_type, value or item["text"]),
            "Needs Review": "YES",
            "Review Reason": "Manual crop OCR - verify before export",
            "Manual Crop": "YES",
            "Job ID": job_id,
        }
    )
    return row


def expand_manual_crop_row(row):
    """Expand one OCR crop into the characteristics contained in that crop.

    Every returned row keeps the same crop geometry so rendering produces one
    physical balloon.  The browser assigns the new main balloon number and
    decimal suffixes after the rows are inserted into the current review.
    """
    base = dict(row or {})
    specification = str(base.get("Specification") or base.get("Dimension") or "").strip()
    if not specification:
        return [base]

    counterbore_components = parse_counterbore_rows(specification)
    if len(counterbore_components) > 1:
        expanded = []
        for index, component in enumerate(counterbore_components, start=1):
            current = dict(base)
            dimension = str(component.get("dimension", "")).strip()
            numeric_match = re.search(r"\d+(?:\.\d+)?", dimension)
            tolerance_input = numeric_match.group(0) if numeric_match else dimension
            nominal, minus, plus, minimum, maximum = parse_tolerance(tolerance_input, apply_general=True)
            current.update(
                {
                    "Specification": component.get("specification", specification),
                    "Symbol": component.get("symbol", ""),
                    "Report Symbol": component.get("symbol", ""),
                    "Dimension": dimension,
                    "Nominal": nominal,
                    "Tolerance -": minus,
                    "Tolerance +": plus,
                    "MIN": minimum,
                    "MAX": maximum,
                    "Equipment": component.get("equipment") or base.get("Equipment", ""),
                    "Subrow Count": len(counterbore_components),
                    "Subrow Index": index,
                    "Multiplier Count": 1,
                    "Multiplier Index": "",
                    "Needs Review": "YES",
                    "Review Reason": "Manual crop compound OCR - verify every sub-row",
                }
            )
            expanded.append(current)
        return expanded

    multiplier_count, clean_specification = extract_multiplier(specification)
    if multiplier_count > 1:
        measurement_type = str(base.get("Measurement Type", "manual"))
        symbol, dimension = split_symbol_and_dimension(clean_specification, measurement_type)
        dimension = dimension or clean_specification
        nominal, minus, plus, minimum, maximum = parse_tolerance(dimension, apply_general=True)
        expanded = []
        for index in range(1, multiplier_count + 1):
            current = dict(base)
            current.update(
                {
                    "Specification": specification,
                    "Symbol": symbol,
                    "Report Symbol": symbol,
                    "Dimension": dimension,
                    "Nominal": nominal,
                    "Tolerance -": minus,
                    "Tolerance +": plus,
                    "MIN": minimum,
                    "MAX": maximum,
                    "Multiplier Count": multiplier_count,
                    "Multiplier Index": index,
                    "Subrow Count": 1,
                    "Subrow Index": "",
                    "Needs Review": "YES",
                    "Review Reason": "Manual crop multiplier OCR - verify every repeated characteristic",
                }
            )
            expanded.append(current)
        return expanded

    return [base]


def render_corrected_outputs(job_id, items, metadata, include_pdf=True):
    current_job = job_path(job_id)
    original_image = current_job / "original.png"
    if not original_image.exists():
        raise FileNotFoundError("Original drawing image not found.")

    image = cv2.imread(str(original_image))
    if image is None:
        raise ValueError("Could not read original drawing image.")

    output_image = current_job / "ballooned_corrected.png"
    output_pdf = current_job / "ballooned_corrected.pdf"
    ballooned = draw_balloons(image, items, metadata)
    cv2.imwrite(str(output_image), ballooned)
    if include_pdf:
        save_pdf_from_image(output_image, output_pdf)
    return output_image, output_pdf


def save_approval_crops(original_image_path, items, approval_dir):
    image = cv2.imread(str(original_image_path))
    if image is None:
        return []
    crop_dir = Path(approval_dir) / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    image_height, image_width = image.shape[:2]
    saved = []

    for index, row in enumerate(items or [], start=1):
        box = item_box(row)
        if box is None:
            saved.append(
                {
                    "balloon_no": row.get("Balloon No", ""),
                    "crop_file": "",
                    "detector_training_eligible": False,
                    "reason": "No valid box was supplied.",
                }
            )
            continue
        x1 = max(0, min(box["x"], image_width - 1))
        y1 = max(0, min(box["y"], image_height - 1))
        x2 = max(x1 + 1, min(box["x"] + box["width"], image_width))
        y2 = max(y1 + 1, min(box["y"] + box["height"], image_height))
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        safe_balloon = re.sub(r"[^0-9A-Za-z_-]+", "_", str(row.get("Balloon No", index)))
        crop_name = f"{index:03d}_{safe_balloon}.png"
        crop_path = crop_dir / crop_name
        cv2.imwrite(str(crop_path), crop)
        saved.append(
            {
                "balloon_no": row.get("Balloon No", ""),
                "crop_file": f"crops/{crop_name}",
                "detector_training_eligible": True,
                "box": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
            }
        )
    return saved


def result_payload(job_id, result):
    preview_rows = normalise_corrected_items(result.get("preview_rows", []))
    snapshot_result = dict(result)
    snapshot_result["preview_rows"] = preview_rows
    persist_job_snapshot(job_id, snapshot_result)
    quality = evaluate_job_quality(job_id, preview_rows)
    return {
        "status": "success" if quality["approval_ready"] else "needs_review",
        "job_id": job_id,
        "ballooned_image": url_for_path(result["ballooned_image"]),
        "ballooned_pdf": url_for_path(result["ballooned_pdf"]),
        "fa_excel": url_for_path(result["fa_excel"]),
        "measurement_results": url_for_path(result["measurement_results"]),
        "rejected_candidates": url_for_path(result["rejected_candidates"]),
        "symbol_detections": url_for_path(result["symbol_detections"]),
        "roboflow_detections": url_for_path(result["roboflow_detections"]),
        "detector_diagnostics": json_safe(result.get("detector_diagnostics", {})),
        "detector_diagnostics_url": url_for_path(result["detector_diagnostics_path"])
        if result.get("detector_diagnostics_path")
        else "",
        "extracted_data": preview_rows,
        "rejected_data": json_safe(result.get("rejected_rows", [])),
        "metadata": json_safe(result.get("metadata", DrawingMetadata())),
        "titleblock_diagnostics": json_safe(result.get("titleblock_diagnostics", {})),
        "processing_timings": json_safe(result.get("processing_timings", {})),
        "processing_timings_url": url_for_path(result["processing_timings_path"])
        if result.get("processing_timings_path")
        else "",
        "quality": quality,
    }


def process_job_background(job_id, file_path, current_job):
    JOB_STATUS[job_id] = {
        "status": "processing",
        "message": "Running OCR extraction.",
    }
    try:
        if job_id in CANCEL_REQUESTS:
            JOB_STATUS[job_id] = {"status": "cancelled", "message": "Processing cancelled before OCR started."}
            return
        result = process_single_drawing_for_web(
            pdf_file_path=file_path,
            job_dir=current_job,
        )
        if job_id in CANCEL_REQUESTS:
            JOB_STATUS[job_id] = {
                "status": "cancelled",
                "message": "Cancel requested. Processing finished but result was not applied.",
            }
            return
        payload = result_payload(job_id, result)
        total_seconds = float(result.get("processing_timings", {}).get("seconds", {}).get("total", 0) or 0)
        quality_issue_count = int(payload.get("quality", {}).get("issue_count", 0) or 0)
        completed_status = "success" if not quality_issue_count else "needs_review"
        timing_message = (
            f"Processing complete in {total_seconds / 60:.1f} minutes."
            if total_seconds
            else "Processing complete."
        )
        if quality_issue_count:
            timing_message += f" QC required: {quality_issue_count} quality check(s) failed."
        JOB_STATUS[job_id] = {
            "status": completed_status,
            "message": timing_message,
            "result": payload,
        }
    except Exception as exc:
        JOB_STATUS[job_id] = {
            "status": "error",
            "message": f"Processing failed: {exc}",
        }
    finally:
        CANCEL_REQUESTS.discard(job_id)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/upload")
async def upload_drawing(file: UploadFile = File(...)):
    job_id = uuid.uuid4().hex[:12]
    current_job = job_path(job_id)
    upload_dir = current_job / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "drawing.pdf").name
    if Path(filename).suffix.lower() != ".pdf":
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Please upload a PDF drawing.",
            },
        )

    file_path = upload_dir / filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = process_single_drawing_for_web(
            pdf_file_path=file_path,
            job_dir=current_job,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Processing failed: {exc}",
            },
        )

    return JSONResponse(content=result_payload(job_id, result))


@app.post("/api/upload-async")
async def upload_drawing_async(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = uuid.uuid4().hex[:12]
    current_job = job_path(job_id)
    upload_dir = current_job / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "drawing.pdf").name
    if Path(filename).suffix.lower() != ".pdf":
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Please upload a PDF drawing.",
            },
        )

    file_path = upload_dir / filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    JOB_STATUS[job_id] = {
        "status": "queued",
        "message": "Drawing uploaded. Waiting to start OCR.",
    }
    background_tasks.add_task(process_job_background, job_id, file_path, current_job)

    return JSONResponse(
        content={
            "status": "queued",
            "job_id": job_id,
            "message": "Drawing uploaded. Processing has started in the background.",
        }
    )


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    status = JOB_STATUS.get(job_id)
    if not status:
        current_job = job_path(job_id)
        if current_job.exists() and (current_job / "fa_inspection_report.xlsx").exists():
            layout_path = current_job / "balloon_layout.json"
            layout_issue_count = 0
            if layout_path.is_file():
                try:
                    layout_issue_count = len(json.loads(layout_path.read_text(encoding="utf-8")).get("issues", []))
                except (OSError, json.JSONDecodeError):
                    layout_issue_count = 1
            return {
                "status": "needs_review" if layout_issue_count else "success",
                "job_id": job_id,
                "message": (
                    f"Job files exist, but {layout_issue_count} unresolved layout issue(s) require review."
                    if layout_issue_count
                    else "Job files exist, but in-memory status was not found. Refresh by reprocessing if data is missing."
                ),
            }
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})
    return json_safe(status)


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    status = JOB_STATUS.get(job_id)
    if not status:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})

    if status.get("status") in {"success", "needs_review", "error", "cancelled"}:
        return {"status": status.get("status"), "message": "Job is already finished."}

    CANCEL_REQUESTS.add(job_id)
    JOB_STATUS[job_id] = {
        "status": "cancel_requested",
        "message": "Cancel requested. The current OCR step will stop when it reaches a safe checkpoint.",
    }
    return JOB_STATUS[job_id]


@app.post("/api/ocr-crop")
async def ocr_crop(request: Request):
    data = await request.json()
    job_id = str(data.get("job_id", "")).strip()
    if not job_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing job_id"})

    current_job = job_path(job_id)
    original_image_path = current_job / "original.png"
    if not original_image_path.exists():
        return JSONResponse(status_code=404, content={"status": "error", "message": "Original drawing image not found"})

    try:
        crop_box = parse_box_payload(data)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Invalid crop box: {exc}"})

    if crop_box[2] < 8 or crop_box[3] < 8:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Draw a larger box around the dimension."})

    image = cv2.imread(str(original_image_path))
    if image is None:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Could not read original drawing image"})

    source_file = source_upload_file(current_job)
    try:
        row = build_row_from_crop_ocr(job_id, image, crop_box, str(source_file.name if source_file else "manual"))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Manual crop OCR failed: {exc}"})

    rows = expand_manual_crop_row(row)
    return JSONResponse(
        content={
            "status": "success",
            # Keep `row` for backward compatibility with older browser builds.
            "row": json_safe(rows[0]),
            "rows": json_safe(rows),
            "subrow_count": len(rows),
        }
    )


@app.post("/api/render-preview")
async def render_preview(request: Request):
    data = await request.json()
    job_id = str(data.get("job_id", "")).strip()
    if not job_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing job_id"})

    current_job = job_path(job_id)
    if not current_job.exists():
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})

    posted_metadata = data.get("metadata") or {}
    metadata = build_metadata(posted_metadata, current_job)
    corrected_items = normalise_corrected_items(data.get("items", []))
    include_pdf = bool(data.get("include_pdf", False))

    try:
        output_image, output_pdf = render_corrected_outputs(job_id, corrected_items, metadata, include_pdf=include_pdf)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Preview render failed: {exc}"})

    return JSONResponse(
        content={
            "status": "success",
            "ballooned_image": url_for_path(output_image),
            "ballooned_pdf": url_for_path(output_pdf) if include_pdf else "",
            "items": json_safe(corrected_items),
        }
    )


@app.post("/api/export-excel")
async def export_to_excel(request: Request):
    data = await request.json()
    job_id = str(data.get("job_id", "")).strip()
    corrected_items = data.get("items", [])
    posted_metadata = data.get("metadata") or {}

    if not job_id:
        return JSONResponse(status_code=400, content={"message": "Missing job_id"})

    current_job = job_path(job_id)
    if not current_job.exists():
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    metadata = build_metadata(posted_metadata, current_job)
    corrected_items = normalise_corrected_items(corrected_items)

    output_filename = current_job / "fa_inspection_report_corrected.xlsx"
    save_fa_workbook(corrected_items, output_filename, metadata=metadata)

    return FileResponse(
        path=output_filename,
        filename="FA_Inspection_Report.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/export-corrected-pdf")
async def export_corrected_pdf(request: Request):
    data = await request.json()
    job_id = str(data.get("job_id", "")).strip()
    corrected_items = normalise_corrected_items(data.get("items", []))
    posted_metadata = data.get("metadata") or {}

    if not job_id:
        return JSONResponse(status_code=400, content={"message": "Missing job_id"})

    current_job = job_path(job_id)
    if not current_job.exists():
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    metadata = build_metadata(posted_metadata, current_job)
    try:
        _output_image, output_pdf = render_corrected_outputs(job_id, corrected_items, metadata)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"message": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"message": str(exc)})

    return FileResponse(
        path=output_pdf,
        filename="Ballooned_Drawing.pdf",
        media_type="application/pdf",
    )


@app.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: str, request: Request):
    if not valid_identifier(job_id, 12):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid job ID."})

    current_job = job_path(job_id)
    if not current_job.exists():
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found."})

    data = await request.json()
    if data.get("confirmed_complete") is not True:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Confirm that the complete drawing was checked before approval."},
        )

    corrected_items = normalise_corrected_items(data.get("items", []))
    if not corrected_items:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Approval requires at least one checked characteristic."},
        )

    snapshot = load_job_snapshot(job_id)
    if snapshot is None:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "message": "The original result snapshot is missing. Reprocess this drawing before approval.",
            },
        )

    source_file = source_upload_file(current_job)
    original_image = current_job / "original.png"
    if source_file is None or not source_file.exists() or not original_image.exists():
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": "The source drawing files are incomplete. Reprocess the drawing."},
        )

    metadata = build_metadata(data.get("metadata") or {}, current_job)
    metadata_payload = json_safe(metadata)
    source_hash = file_sha256(source_file)
    quality = evaluate_job_quality(job_id, corrected_items)
    if not quality["approval_ready"]:
        return JSONResponse(
            status_code=409,
            content={
                "status": "needs_review",
                "message": (
                    "Approval blocked. Correct the missing balloons, golden-output differences, "
                    "or balloon overlaps listed in the quality checks first."
                ),
                "quality": quality,
            },
        )
    content_hash = approval_content_hash(job_id, source_hash, corrected_items, metadata_payload)
    source_approvals = approval_records_for_source(source_hash)
    for existing_record in source_approvals:
        if existing_record.get("content_hash") == content_hash:
            return JSONResponse(content=approval_response(existing_record, duplicate=True))

    previous_approval = source_approvals[-1] if source_approvals else None
    if previous_approval is None:
        approval_id = hashlib.sha256(source_hash.encode("ascii")).hexdigest()[:16]
    else:
        approval_id = hashlib.sha256(f"{source_hash}:{content_hash}".encode("ascii")).hexdigest()[:16]
    final_dir = APPROVALS_DIR / approval_id

    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{approval_id}.", dir=str(APPROVALS_DIR)))
    try:
        _job_image, job_pdf = render_corrected_outputs(job_id, corrected_items, metadata, include_pdf=True)
        job_excel = current_job / "fa_inspection_report_corrected.xlsx"
        save_fa_workbook(corrected_items, job_excel, metadata=metadata)

        approved_pdf = temporary_dir / "approved_ballooned_drawing.pdf"
        approved_excel = temporary_dir / "approved_fa_inspection_report.xlsx"
        approved_source = temporary_dir / f"source_{source_file.name}"
        shutil.copy2(job_pdf, approved_pdf)
        shutil.copy2(job_excel, approved_excel)
        shutil.copy2(source_file, approved_source)

        changes = compare_characteristics(snapshot.get("original_items", []), corrected_items)
        crop_records = save_approval_crops(original_image, corrected_items, temporary_dir)
        drawing_name = metadata.drawing_number or source_file.stem
        safe_drawing_name = re.sub(r"[^0-9A-Za-z._-]+", "_", drawing_name).strip("_") or "Drawing"
        package_filename = f"Approved_{safe_drawing_name}.zip"
        record = {
            "schema_version": 1,
            "approval_id": approval_id,
            "job_id": job_id,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "confirmed_complete": True,
            "immutable": True,
            "approval_revision": len(source_approvals) + 1,
            "supersedes_approval_id": previous_approval.get("approval_id", "") if previous_approval else "",
            "content_hash": content_hash,
            "source": {
                "filename": source_file.name,
                "sha256": source_hash,
                "saved_file": approved_source.name,
            },
            "original_metadata": snapshot.get("original_metadata", {}),
            "corrected_metadata": metadata_payload,
            "original_items": snapshot.get("original_items", []),
            "corrected_items": json_safe(corrected_items),
            "changes": changes,
            "change_counts": change_counts(changes),
            "crops": crop_records,
            "model_context": snapshot.get("detector_diagnostics", {}),
            "training_status": "not_started",
            "training_note": "Approval captured only. Roboflow retraining is intentionally disabled.",
            "approved_pdf": approved_pdf.name,
            "approved_excel": approved_excel.name,
            "package_filename": package_filename,
            "package_file": "approved_package.zip",
        }
        write_json_atomic(temporary_dir / "approval.json", record)

        package_path = temporary_dir / record["package_file"]
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(approved_pdf, approved_pdf.name)
            archive.write(approved_excel, approved_excel.name)
            archive.write(approved_source, approved_source.name)
            archive.write(temporary_dir / "approval.json", "approval.json")
            for crop in crop_records:
                crop_file = crop.get("crop_file")
                if crop_file:
                    archive.write(temporary_dir / crop_file, crop_file)

        try:
            temporary_dir.rename(final_dir)
        except FileExistsError:
            existing_record = load_approval_record(approval_id)
            if existing_record and existing_record.get("content_hash") == content_hash:
                return JSONResponse(content=approval_response(existing_record, duplicate=True))
            raise
    except Exception as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Approval could not be saved: {exc}"},
        )

    return JSONResponse(content=approval_response(record))


def approval_file_response(approval_id, record_key, filename, media_type):
    record = load_approval_record(approval_id)
    if record is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Approval not found."})
    file_path = APPROVALS_DIR / approval_id / record.get(record_key, "")
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse(status_code=404, content={"status": "error", "message": "Approved file not found."})
    return FileResponse(path=file_path, filename=filename(record), media_type=media_type)


@app.get("/api/approvals/{approval_id}/pdf")
async def download_approved_pdf(approval_id: str):
    return approval_file_response(
        approval_id,
        "approved_pdf",
        lambda _record: "Approved_Ballooned_Drawing.pdf",
        "application/pdf",
    )


@app.get("/api/approvals/{approval_id}/excel")
async def download_approved_excel(approval_id: str):
    return approval_file_response(
        approval_id,
        "approved_excel",
        lambda _record: "Approved_FA_Inspection_Report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/approvals/{approval_id}/package")
async def download_approved_package(approval_id: str):
    return approval_file_response(
        approval_id,
        "package_file",
        lambda record: record.get("package_filename", "Approved_Drawing.zip"),
        "application/zip",
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "storage": str(STORAGE_DIR),
        "generated_jobs": str(JOBS_DIR),
        "cors_origins": cors_origins or ["*"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("OCR_DRAWING_HOST", "127.0.0.1"),
        port=int(os.getenv("OCR_DRAWING_PORT", "8001")),
        reload=False,
    )
