import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
from pdf2image import convert_from_path

from ai_parser import (
    empty_ai_data,
    get_structured_data_with_retries,
    has_gemini_client,
    save_ai_debug,
)
from config import (
    DATASET_CROPS_DIR,
    DATASET_IMAGES_DIR,
    DATASET_OCR_OUTPUT_DIR,
    DEBUG_FULL_PAGE_DIR,
    DEBUG_OCR_TEXT_DIR,
    DEBUG_TITLEBLOCK_CROP_DIR,
    EXTRACTED_DATA_OUTPUT_PATH,
    LEGACY_DRAWING_FOLDER,
    OCR_REVIEW_THRESHOLD,
    PDF_DPI,
    RAW_PDF_FOLDER,
    VERIFICATION_OUTPUT_PATH,
    ensure_directories,
    get_input_folder,
    setup_logging,
)
from exporter import create_verification_row, save_workbooks
from vision_tools import (
    create_paddle_ocr,
    get_yolo_titleblock_model,
    save_detection,
    select_title_block_with_ocr,
)


def safe_stem(filename):
    return Path(filename).stem.replace(" ", "_")


def save_text(path, text):
    path.write_text(text, encoding="utf-8")


def load_or_convert_first_page(file_path, stem):
    image_path = DATASET_IMAGES_DIR / f"{stem}.png"
    if image_path.exists():
        image = cv2.imread(str(image_path))
        if image is not None:
            return image, "cache"

    pages = convert_from_path(str(file_path), dpi=PDF_DPI, first_page=1, last_page=1)
    image = cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(image_path), image)
    return image, "pdf"


def main():
    parser = argparse.ArgumentParser(description="Extract title block OCR data from drawing PDFs.")
    parser.add_argument("--limit", type=int, help="Optional maximum number of PDFs to process.")
    parser.add_argument("--pdf", type=Path, help="Optional single PDF file to process.")
    parser.add_argument("--no-export", action="store_true", help="Run processing without writing Excel files.")
    parser.add_argument(
        "--refresh-images",
        action="store_true",
        help="Reconvert PDFs instead of using cached dataset/images PNG files.",
    )
    args = parser.parse_args()

    ensure_directories()
    setup_logging()

    if not has_gemini_client():
        logging.warning("GEMINI_API_KEY is not set. AI extraction will be skipped.")

    yolo_model = get_yolo_titleblock_model()
    if yolo_model is None:
        print("YOLO title-block model not available. Using crop-candidate fallback.\n")
    else:
        print("YOLO title-block model loaded. Using YOLO crop first.\n")

    ocr = create_paddle_ocr()
    all_rows = []
    failed_files = []
    ocr_times = []
    ai_times = []

    input_folder = get_input_folder()
    files = [args.pdf] if args.pdf else sorted(input_folder.glob("*.pdf"))
    if args.limit:
        files = files[:args.limit]

    if not files:
        print(f"No PDF files found in {RAW_PDF_FOLDER} or {LEGACY_DRAWING_FOLDER}")
        return

    print(f"Found {len(files)} drawings in {input_folder}. Starting...\n")
    logging.info("Batch started. Input folder: %s. File count: %s", input_folder, len(files))

    for file_path in files:
        filename = file_path.name
        stem = safe_stem(filename)
        print(f"Processing: {filename}")
        logging.info("Processing file: %s", filename)

        try:
            start_time = time.perf_counter()

            if args.refresh_images:
                cached_image = DATASET_IMAGES_DIR / f"{stem}.png"
                if cached_image.exists():
                    cached_image.unlink()

            img_cv, image_source = load_or_convert_first_page(file_path, stem)
            cv2.imwrite(str(DEBUG_FULL_PAGE_DIR / f"{stem}.png"), img_cv)

            ocr_start = time.perf_counter()
            crop, ocr_result, crop_diagnostics = select_title_block_with_ocr(ocr, img_cv)
            ocr_time = time.perf_counter() - ocr_start
            ocr_times.append(ocr_time)

            save_detection(
                DATASET_IMAGES_DIR / f"{stem}.png",
                img_cv,
                crop_diagnostics["regions"],
                crop_diagnostics["candidates"],
            )

            cv2.imwrite(str(DATASET_CROPS_DIR / f"{stem}.png"), crop)

            messy_text = ocr_result["text"]
            ocr_score = ocr_result["confidence"]
            status = "OK" if ocr_score >= OCR_REVIEW_THRESHOLD else "REVIEW"

            cv2.imwrite(str(DEBUG_TITLEBLOCK_CROP_DIR / f"{stem}.png"), ocr_result["debug_image"])
            save_text(DATASET_OCR_OUTPUT_DIR / f"{stem}.txt", messy_text)
            save_text(DEBUG_OCR_TEXT_DIR / f"{stem}.txt", messy_text)

            ai_start = time.perf_counter()
            ai_error = None
            raw_ai_text = ""
            if not has_gemini_client():
                data = empty_ai_data()
                ai_error = "GEMINI_API_KEY is not set."
            else:
                (data, raw_ai_text), ai_error = get_structured_data_with_retries(
                    messy_text,
                    filename,
                )
                if ai_error:
                    logging.error("AI extraction failed for %s: %s", filename, ai_error)

            ai_time = time.perf_counter() - ai_start
            ai_times.append(ai_time)
            save_ai_debug(stem, data, raw_ai_text, ai_error)

            row = create_verification_row(
                filename=filename,
                messy_text=messy_text,
                ocr_score=ocr_score,
                ocr_time=ocr_time,
                ai_time=ai_time,
                status=status,
                data=data,
                diagnostics={
                    **crop_diagnostics,
                    "ocr_variant": ocr_result["variant_name"],
                    "ocr_selection_score": ocr_result["selection_score"],
                    "ocr_line_count": ocr_result["line_count"],
                    "ocr_text_length": ocr_result["text_length"],
                },
            )
            all_rows.append(row)

            total_time = time.perf_counter() - start_time
            print(
                f"   OCR score: {ocr_score:.2f} | Status: {status} | "
                f"Crop: {crop_diagnostics['crop_method']} "
                f"({crop_diagnostics['crop_confidence']:.2f})"
            )
            print(
                f"   Crop source: {crop_diagnostics['crop_source']} | "
                f"Keywords: {crop_diagnostics['crop_keyword_hits']} | "
                f"IDs: {crop_diagnostics['crop_identifier_hits']}"
            )
            print(f"   OCR variant: {ocr_result['variant_name']}")
            print(f"   Image source: {image_source}")
            print(f"   OCR time: {ocr_time:.1f}s | AI time: {ai_time:.1f}s")
            print(f"   Done in {total_time:.1f}s\n")
            logging.info(
                "Processed %s | OCR score %.4f | Status %s | OCR %.2fs | AI %.2fs | Total %.2fs",
                filename,
                ocr_score,
                status,
                ocr_time,
                ai_time,
                total_time,
            )

        except Exception as exc:
            failed_files.append(filename)
            print(f"   Error: {exc}\n")
            logging.exception("Failed processing %s", filename)

    if all_rows and args.no_export:
        print("No Excel files written because --no-export was used.\n")
    elif all_rows:
        save_workbooks(all_rows)

        print(f"Saved verification workbook:\n{VERIFICATION_OUTPUT_PATH}")
        print(f"Saved extracted data workbook:\n{EXTRACTED_DATA_OUTPUT_PATH}\n")
    else:
        print("No data extracted.\n")

    total_files = len(files)
    success_count = len(all_rows)
    success_rate = (success_count / total_files) * 100 if total_files else 0
    avg_ocr_time = sum(ocr_times) / len(ocr_times) if ocr_times else 0
    avg_ai_time = sum(ai_times) / len(ai_times) if ai_times else 0

    print("Batch statistics")
    print(f"Total files processed: {total_files}")
    print(f"Successful files: {success_count}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Average OCR time: {avg_ocr_time:.1f}s")
    print(f"Average AI time: {avg_ai_time:.1f}s")
    print(f"Failed files: {', '.join(failed_files) if failed_files else 'None'}")

    logging.info(
        "Batch finished | Total %s | Success %s | Success rate %.1f%% | Avg OCR %.2fs | Avg AI %.2fs | Failed %s",
        total_files,
        success_count,
        success_rate,
        avg_ocr_time,
        avg_ai_time,
        failed_files,
    )


if __name__ == "__main__":
    main()
