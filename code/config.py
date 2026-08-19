import logging
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

DATASET_DIR = BASE_DIR / "dataset"
RAW_PDF_FOLDER = DATASET_DIR / "raw_pdfs"
LEGACY_DRAWING_FOLDER = BASE_DIR / "drawing"

DATASET_IMAGES_DIR = DATASET_DIR / "images"
DATASET_CROPS_DIR = DATASET_DIR / "crops"
DATASET_OCR_OUTPUT_DIR = DATASET_DIR / "ocr_output"
LAYOUT_REGIONS_DIR = DATASET_DIR / "layout_regions"
VERIFIED_EXCEL_DIR = DATASET_DIR / "verified_excel"

DEBUG_DIR = BASE_DIR / "debug"
DEBUG_FULL_PAGE_DIR = DEBUG_DIR / "full_page"
DEBUG_TITLEBLOCK_CROP_DIR = DEBUG_DIR / "titleblock_crop"
DEBUG_OCR_TEXT_DIR = DEBUG_DIR / "ocr_text"
DEBUG_AI_JSON_DIR = DEBUG_DIR / "ai_json"
DEBUG_LAYOUT_DIR = DEBUG_DIR / "layout_detection"
DEBUG_SYMBOL_DETECTION_DIR = DEBUG_DIR / "symbol_detection"
DEBUG_MEASUREMENT_DETECTION_DIR = DEBUG_DIR / "measurement_detection"
DEBUG_BALLOONING_DIR = DEBUG_DIR / "ballooning"

LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "process.log"
VERIFICATION_OUTPUT_PATH = VERIFIED_EXCEL_DIR / "titleblock_verification_v2.xlsx"
EXTRACTED_DATA_OUTPUT_PATH = BASE_DIR / "extracted_data.xlsx"
SYMBOL_DETECTION_OUTPUT_PATH = BASE_DIR / "symbol_detection_results.xlsx"
MEASUREMENT_DETECTION_OUTPUT_PATH = BASE_DIR / "measurement_detection_results.xlsx"
INSPECTION_PLAN_OUTPUT_PATH = BASE_DIR / "inspection_plan.xlsx"

YOLO_TITLEBLOCK_MODEL_CANDIDATES = [
    BASE_DIR / "runs" / "titleblock" / "yolo_titleblock" / "weights" / "best.pt",
    BASE_DIR / "runs" / "detect" / "runs" / "titleblock" / "yolo_titleblock" / "weights" / "best.pt",
]
YOLO_TITLEBLOCK_CONFIDENCE = float(os.getenv("YOLO_TITLEBLOCK_CONFIDENCE", "0.60"))
YOLO_SYMBOL_MODEL_OVERRIDE = os.getenv("YOLO_SYMBOL_MODEL_PATH", "").strip()
YOLO_SYMBOL_MODEL_CANDIDATES = (
    [Path(YOLO_SYMBOL_MODEL_OVERRIDE).expanduser()]
    if YOLO_SYMBOL_MODEL_OVERRIDE
    else []
) + [
    BASE_DIR
    / "runs"
    / "detect"
    / "runs"
    / "symbols_training"
    / "yolo_symbols"
    / "weights"
    / "best.pt",
    BASE_DIR
    / "runs"
    / "detect"
    / "runs"
    / "symbols_training"
    / "yolo_symbols_v4"
    / "weights"
    / "best.pt",
    BASE_DIR
    / "runs"
    / "detect"
    / "runs"
    / "symbolss_training"
    / "yolo11s_symbols_v4"
    / "weights"
    / "best.pt",
]
YOLO_SYMBOL_CONFIDENCE = float(os.getenv("YOLO_SYMBOL_CONFIDENCE", "0.60"))
YOLO_SYMBOL_REVIEW_THRESHOLD = float(os.getenv("YOLO_SYMBOL_REVIEW_THRESHOLD", "0.75"))
YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE = min(
    1.0,
    max(0.0, float(os.getenv("YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE", "0.58"))),
)
YOLO_GDT_OCR_MIN_DETECTOR_CONFIDENCE = min(
    1.0,
    max(0.0, float(os.getenv("YOLO_GDT_OCR_MIN_DETECTOR_CONFIDENCE", "0.70"))),
)
YOLO_SYMBOL_TILING_ENABLED = os.getenv(
    "YOLO_SYMBOL_TILING_ENABLED", "0"
).strip().lower() not in {"0", "false", "no"}
YOLO_SYMBOL_TILE_SIZE = max(
    320,
    int(os.getenv("YOLO_SYMBOL_TILE_SIZE", "1280")),
)
YOLO_SYMBOL_TILE_OVERLAP = max(
    0,
    min(
        YOLO_SYMBOL_TILE_SIZE - 1,
        int(os.getenv("YOLO_SYMBOL_TILE_OVERLAP", "320")),
    ),
)
YOLO_SYMBOL_TILE_EDGE_MARGIN = max(
    0,
    int(os.getenv("YOLO_SYMBOL_TILE_EDGE_MARGIN", "2")),
)
YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH = os.getenv(
    "YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH", ""
).strip()
YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE = float(
    os.getenv("YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE", str(YOLO_SYMBOL_CONFIDENCE))
)
YOLO_SYMBOL_ENSEMBLE_REQUIRED = os.getenv(
    "YOLO_SYMBOL_ENSEMBLE_REQUIRED", "0"
).strip().lower() in {"1", "true", "yes"}
YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD = min(
    1.0,
    max(0.0, float(os.getenv("YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD", "0.30"))),
)
YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD = min(
    1.0,
    max(
        0.0,
        float(os.getenv("YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD", "0.70")),
    ),
)
YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED = os.getenv(
    "YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED", "1"
).strip().lower() not in {"0", "false", "no"}
YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES = tuple(
    item.strip()
    for item in os.getenv("YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES", "").split(",")
    if item.strip()
)
YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES = tuple(
    item.strip()
    for item in os.getenv("YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES", "").split(",")
    if item.strip()
)
YOLO_SYMBOL_RESCUE_PATH = os.getenv("YOLO_SYMBOL_RESCUE_PATH", "").strip()
YOLO_SYMBOL_RESCUE_CONFIDENCE = min(
    1.0, max(0.0, float(os.getenv("YOLO_SYMBOL_RESCUE_CONFIDENCE", "0.0")))
)
YOLO_SYMBOL_RESCUE_CLASSES = tuple(
    item.strip()
    for item in os.getenv("YOLO_SYMBOL_RESCUE_CLASSES", "dimension_text").split(",")
    if item.strip()
)
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").strip()
ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE", "krafo").strip()
ROBOFLOW_WORKFLOW_ID = os.getenv(
    "ROBOFLOW_WORKFLOW_ID",
    "ocrengineeringdrawing",
).strip()
ROBOFLOW_EXPECTED_MODEL_ID = os.getenv(
    "ROBOFLOW_EXPECTED_MODEL_ID",
    "krafo/ocr-balloon-system-5-yolov8s-t1",
).strip()
ROBOFLOW_ENABLED = os.getenv("ROBOFLOW_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
ROBOFLOW_CONFIDENCE = float(os.getenv("ROBOFLOW_CONFIDENCE", "0.45"))
ROBOFLOW_TIMEOUT_SECONDS = float(os.getenv("ROBOFLOW_TIMEOUT_SECONDS", "90"))
ROBOFLOW_MAX_RETRIES = int(os.getenv("ROBOFLOW_MAX_RETRIES", "2"))
ROBOFLOW_TILING_ENABLED = os.getenv("ROBOFLOW_TILING_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
ROBOFLOW_INCLUDE_FULL_IMAGE = os.getenv("ROBOFLOW_INCLUDE_FULL_IMAGE", "1").strip().lower() not in {"0", "false", "no"}
ROBOFLOW_TILE_OVERLAP = min(0.40, max(0.0, float(os.getenv("ROBOFLOW_TILE_OVERLAP", "0.15"))))
ROBOFLOW_MAX_REGIONS = max(1, int(os.getenv("ROBOFLOW_MAX_REGIONS", "5")))
MEASUREMENT_OCR_CONFIDENCE = float(os.getenv("MEASUREMENT_OCR_CONFIDENCE", "0.55"))
MEASUREMENT_REVIEW_THRESHOLD = float(os.getenv("MEASUREMENT_REVIEW_THRESHOLD", "0.75"))

PDF_DPI = int(os.getenv("PDF_DPI", "400"))
OCR_REVIEW_THRESHOLD = 0.70
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_SECONDS = 65

OCR_DETECTION_MODEL = os.getenv("OCR_DETECTION_MODEL", "PP-OCRv5_mobile_det")
OCR_RECOGNITION_MODELS = tuple(
    model.strip()
    for model in os.getenv(
        "OCR_RECOGNITION_MODELS",
        "PP-OCRv5_mobile_rec,en_PP-OCRv4_mobile_rec,PP-OCRv4_mobile_rec",
    ).split(",")
    if model.strip()
)

GEMINI_MODEL_CANDIDATES = (
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash",
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

FIELD_NAMES = [
    "Company Name",
    "Part Name",
    "Material",
    "Drawing Number",
    "Revision",
]

IMPORTANT_FIELD_NAMES = [
    "Part Name",
    "Drawing Number",
    "Revision",
]

FIELD_LABEL_HINTS = {
    "Company Name": [
        "COMPANY",
        "CUSTOMER",
        "CLIENT",
        "ä¼šç¤¾",
        "å…¬å¸",
        "SYARIKAT",
    ],
    "Part Name": [
        "PART NAME",
        "TITLE",
        "DESCRIPTION",
        "å“å",
        "éƒ¨å“å",
        "é›¶ä»¶åç§°",
        "NAMA BAHAGIAN",
    ],
    "Material": [
        "MATERIAL",
        "MATL",
        "MAT'L",
        "æè³ª",
        "ææ–™",
        "ææ–™å",
        "BAHAN",
    ],
    "Drawing Number": [
        "DRAWING NO",
        "DWG NO",
        "DWG. NO.",
        "å›³ç•ª",
        "å›³é¢ç•ªå·",
        "å›¾å·",
        "NO LUKISAN",
    ],
    "Revision": [
        "REV",
        "REVISION",
        "æ”¹è¨‚",
        "ç‰ˆæ¬¡",
        "ç‰ˆæœ¬",
        "SEMAKAN",
    ],
}


def ensure_directories():
    for folder in [
        RAW_PDF_FOLDER,
        DATASET_IMAGES_DIR,
        DATASET_CROPS_DIR,
        DATASET_OCR_OUTPUT_DIR,
        LAYOUT_REGIONS_DIR,
        VERIFIED_EXCEL_DIR,
        DEBUG_FULL_PAGE_DIR,
        DEBUG_TITLEBLOCK_CROP_DIR,
        DEBUG_OCR_TEXT_DIR,
        DEBUG_AI_JSON_DIR,
        DEBUG_LAYOUT_DIR,
        DEBUG_SYMBOL_DETECTION_DIR,
        DEBUG_MEASUREMENT_DETECTION_DIR,
        DEBUG_BALLOONING_DIR,
        LOG_DIR,
    ]:
        folder.mkdir(parents=True, exist_ok=True)


def setup_logging():
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
        force=True,
    )


def get_input_folder():
    dataset_pdfs = list(RAW_PDF_FOLDER.glob("*.pdf"))
    if dataset_pdfs:
        return RAW_PDF_FOLDER

    return LEGACY_DRAWING_FOLDER
