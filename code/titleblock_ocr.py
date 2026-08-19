from pathlib import Path

import cv2

from drawing_metadata import merge_metadata, parse_metadata_from_titleblock_text
from vision_tools import create_paddle_ocr, get_yolo_titleblock_model, select_title_block_with_ocr


def extract_titleblock_metadata(image, base_metadata, debug_dir=None):
    if image is None:
        return base_metadata, {"status": "skipped", "reason": "missing image"}

    try:
        # Load YOLO before PaddleOCR on Windows to avoid Torch/Paddle DLL load-order issues.
        get_yolo_titleblock_model()
        ocr = create_paddle_ocr()
        crop, ocr_result, diagnostics = select_title_block_with_ocr(ocr, image)
    except Exception as exc:
        return base_metadata, {"status": "failed", "reason": str(exc)}

    text = ocr_result.get("text", "") if isinstance(ocr_result, dict) else ""
    titleblock_metadata = parse_metadata_from_titleblock_text(text)
    merged_metadata = merge_metadata(base_metadata, titleblock_metadata)

    diagnostics = dict(diagnostics)
    diagnostics.update(
        {
            "status": "ok",
            "ocr_text": text,
            "ocr_confidence": ocr_result.get("confidence", ""),
            "ocr_variant": ocr_result.get("variant_name", ""),
        }
    )

    if debug_dir:
        save_titleblock_debug(debug_dir, crop, text, diagnostics)

    return merged_metadata, diagnostics


def save_titleblock_debug(debug_dir, crop, text, diagnostics):
    debug_path = Path(debug_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    if crop is not None:
        cv2.imwrite(str(debug_path / "titleblock_crop.png"), crop)

    (debug_path / "titleblock_ocr.txt").write_text(str(text or ""), encoding="utf-8")

    summary_lines = [
        f"status: {diagnostics.get('status', '')}",
        f"crop_method: {diagnostics.get('crop_method', '')}",
        f"crop_source: {diagnostics.get('crop_source', '')}",
        f"crop_confidence: {diagnostics.get('crop_confidence', '')}",
        f"ocr_confidence: {diagnostics.get('ocr_confidence', '')}",
        f"ocr_variant: {diagnostics.get('ocr_variant', '')}",
        f"crop_box: {diagnostics.get('crop_box', '')}",
    ]
    (debug_path / "titleblock_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
