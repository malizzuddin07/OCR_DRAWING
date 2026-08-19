import json
import logging
import os
import re
import sys
import tempfile
import types
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from config import (
    DEBUG_LAYOUT_DIR,
    LAYOUT_REGIONS_DIR,
    OCR_DETECTION_MODEL,
    OCR_RECOGNITION_MODELS,
    ROBOFLOW_API_KEY,
    ROBOFLOW_CONFIDENCE,
    ROBOFLOW_ENABLED,
    ROBOFLOW_INCLUDE_FULL_IMAGE,
    ROBOFLOW_MAX_REGIONS,
    ROBOFLOW_TILE_OVERLAP,
    ROBOFLOW_TILING_ENABLED,
    YOLO_SYMBOL_CONFIDENCE,
    YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES,
    YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH,
    YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD,
    YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD,
    YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES,
    YOLO_SYMBOL_ENSEMBLE_REQUIRED,
    YOLO_SYMBOL_MODEL_CANDIDATES,
    YOLO_TITLEBLOCK_CONFIDENCE,
    YOLO_TITLEBLOCK_MODEL_CANDIDATES,
)
from detector_ensemble import baseline_priority_merge
from roboflow_workflow_client import (
    RoboflowWorkflowError,
    run_engineering_symbol_workflow,
)

TITLE_KEYWORDS = (
    "DWG",
    "DRAWING",
    "DRAWING NO",
    "DWG NO",
    "REV",
    "REVISION",
    "MATERIAL",
    "MATL",
    "PART",
    "PART NAME",
    "TITLE",
    "DESCRIPTION",
    "SCALE",
    "SHT",
    "SHEET",
    "図番",
    "図面番号",
    "図名",
    "品名",
    "部品名",
    "材料",
    "材質",
    "改訂",
    "版次",
    "版本",
)

DRAWING_NUMBER_PATTERN = re.compile(
    r"\b(?:W3-C\d{9}-[A-Z0-9]{2}|C\d{4}-\d{3}-[A-Z0-9]+(?:-[A-Z0-9]{2})?)\b"
)

_yolo_titleblock_model = None
_yolo_titleblock_available = None
_yolo_symbol_model = None
_yolo_symbol_available = None
_yolo_symbol_addition_model = None
_yolo_symbol_addition_available = None
_paddle_ocr = None
_paddle_text_recognizer = None


os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "false")
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")

if os.environ.get("PADDLE_PDX_MODEL_SOURCE", "").upper() == "BOS":
    modelscope_stub = types.ModuleType("modelscope")

    def _disabled_modelscope_download(*args, **kwargs):
        raise RuntimeError("ModelScope is disabled because PADDLE_PDX_MODEL_SOURCE=BOS.")

    modelscope_stub.snapshot_download = _disabled_modelscope_download
    sys.modules.setdefault("modelscope", modelscope_stub)

@dataclass
class Region:
    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    method: str = "traditional_cv"

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1

    @property
    def area(self):
        return self.width * self.height


@dataclass
class CropCandidate:
    name: str
    x1: int
    y1: int
    x2: int
    y2: int
    source: str
    visual_score: float = 0.0
    line_density: float = 0.0

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1

    @property
    def box(self):
        return self.x1, self.y1, self.x2, self.y2


def create_paddle_ocr():
    global _paddle_ocr
    if _paddle_ocr is not None:
        return _paddle_ocr

    import paddle
    from paddleocr import PaddleOCR

    paddle.set_flags({
        "FLAGS_use_mkldnn": False,
        "FLAGS_enable_pir_api": False,
    })

    base_config = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_detection_model_name": OCR_DETECTION_MODEL,
        "lang": "en",
        "device": "cpu",
        "text_det_limit_side_len": 960,
        "enable_mkldnn": False,
    }

    errors = []

    for recognition_model in OCR_RECOGNITION_MODELS:
        common_config = {
            **base_config,
            "text_recognition_model_name": recognition_model,
        }

        try:
            _paddle_ocr = PaddleOCR(**common_config)
            return _paddle_ocr
        except Exception as exc:
            errors.append(f"{recognition_model}: {exc}")
            logging.warning("PaddleOCR model failed: %s: %s", recognition_model, exc)

    raise RuntimeError("No supported PaddleOCR recognition model found. " + " | ".join(errors))


def create_paddle_text_recognizer():
    """Create recognition-only OCR for boxes already located by a detector."""
    global _paddle_text_recognizer
    if _paddle_text_recognizer is not None:
        return _paddle_text_recognizer

    import paddle
    from paddleocr import TextRecognition

    paddle.set_flags({
        "FLAGS_use_mkldnn": False,
        "FLAGS_enable_pir_api": False,
    })

    errors = []
    for recognition_model in OCR_RECOGNITION_MODELS:
        try:
            _paddle_text_recognizer = TextRecognition(
                model_name=recognition_model,
                device="cpu",
                enable_mkldnn=False,
            )
            return _paddle_text_recognizer
        except Exception as exc:
            errors.append(f"{recognition_model}: {exc}")
            logging.warning("PaddleOCR recognition-only model failed: %s: %s", recognition_model, exc)

    raise RuntimeError("No supported recognition-only OCR model found. " + " | ".join(errors))


def get_yolo_titleblock_model():
    global _yolo_titleblock_model
    global _yolo_titleblock_available

    if _yolo_titleblock_available is False:
        return None

    if _yolo_titleblock_model is not None:
        return _yolo_titleblock_model

    model_path = next(
        (path for path in YOLO_TITLEBLOCK_MODEL_CANDIDATES if path.exists()),
        None,
    )
    if model_path is None:
        _yolo_titleblock_available = False
        logging.info("YOLO title-block model not found. Using crop-candidate fallback.")
        return None

    try:
        from ultralytics import YOLO

        _yolo_titleblock_model = YOLO(str(model_path))
        _yolo_titleblock_available = True
        logging.info("Loaded YOLO title-block model: %s", model_path)
        return _yolo_titleblock_model
    except Exception as exc:
        _yolo_titleblock_available = False
        logging.warning("Could not load YOLO title-block model: %s", exc)
        return None


def get_yolo_symbol_model():
    global _yolo_symbol_model
    global _yolo_symbol_available

    if _yolo_symbol_available is False:
        return None

    if _yolo_symbol_model is not None:
        return _yolo_symbol_model

    model_path = next(
        (path for path in YOLO_SYMBOL_MODEL_CANDIDATES if path.exists()),
        None,
    )
    if model_path is None:
        _yolo_symbol_available = False
        logging.info("YOLO symbol model not found. Symbol-aware filtering disabled.")
        return None

    try:
        from ultralytics import YOLO

        _yolo_symbol_model = YOLO(str(model_path))
        _yolo_symbol_available = True
        logging.info("Loaded YOLO symbol model: %s", model_path)
        return _yolo_symbol_model
    except Exception as exc:
        _yolo_symbol_available = False
        logging.warning("Could not load YOLO symbol model: %s", exc)
        return None


def get_yolo_symbol_addition_model():
    global _yolo_symbol_addition_model
    global _yolo_symbol_addition_available

    if not YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH:
        return None
    if _yolo_symbol_addition_available is False:
        return None
    if _yolo_symbol_addition_model is not None:
        return _yolo_symbol_addition_model

    model_path = Path(YOLO_SYMBOL_ENSEMBLE_ADDITION_PATH).expanduser()
    if not model_path.is_file():
        _yolo_symbol_addition_available = False
        if YOLO_SYMBOL_ENSEMBLE_REQUIRED:
            raise FileNotFoundError(
                f"Required YOLO ensemble addition model was not found: {model_path}"
            )
        logging.warning("YOLO ensemble addition model was not found: %s", model_path)
        return None
    try:
        from ultralytics import YOLO

        _yolo_symbol_addition_model = YOLO(str(model_path))
        _yolo_symbol_addition_available = True
        logging.info("Loaded YOLO ensemble addition model: %s", model_path)
        return _yolo_symbol_addition_model
    except Exception as exc:
        _yolo_symbol_addition_available = False
        if YOLO_SYMBOL_ENSEMBLE_REQUIRED:
            raise RuntimeError(
                f"Required YOLO ensemble addition model could not be loaded: {model_path}"
            ) from exc
        logging.warning("Could not load YOLO ensemble addition model: %s", exc)
        return None


def _predict_symbols_with_model(
    model,
    image,
    confidence,
    image_size,
    detector_name,
):
    if model is None or image is None:
        return []
    try:
        results = model.predict(
            image,
            imgsz=image_size,
            conf=confidence,
            verbose=False,
        )
    except Exception as exc:
        if YOLO_SYMBOL_ENSEMBLE_REQUIRED:
            raise RuntimeError(
                f"Required {detector_name} symbol prediction failed"
            ) from exc
        logging.warning("%s symbol prediction failed: %s", detector_name, exc)
        return []

    if not results:
        return []

    image_height, image_width = image.shape[:2]
    detections = []
    boxes = getattr(results[0], "boxes", None)
    if boxes is None:
        return detections

    for box in boxes:
        class_id = int(box.cls[0])
        # Local candidate models may use the same broad class schema returned
        # by Roboflow. Normalize both sources so downstream OCR rules receive
        # one stable detector interface.
        symbol_class = normalize_roboflow_class_name(model.names[class_id])
        confidence_score = float(box.conf[0])
        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
        x1, y1, x2, y2 = clamp_crop_box(x1, y1, x2, y2, image_width, image_height)
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append(
            {
                "Symbol Class": symbol_class,
                "Confidence": round(confidence_score, 4),
                "X": x1,
                "Y": y1,
                "Width": x2 - x1,
                "Height": y2 - y1,
                "Box": f"{x1},{y1},{x2},{y2}",
                "Detector": detector_name,
            }
        )

    return detections


def _ensemble_record(detection):
    return {
        "class_name": detection["Symbol Class"],
        "box": [
            detection["X"],
            detection["Y"],
            detection["Width"],
            detection["Height"],
        ],
        "confidence": detection["Confidence"],
        "detection": detection,
    }


def detect_symbols_with_yolo(image, confidence=None, image_size=1280):
    model = get_yolo_symbol_model()
    if model is None or image is None:
        return []

    conf = YOLO_SYMBOL_CONFIDENCE if confidence is None else confidence
    baseline = _predict_symbols_with_model(
        model,
        image,
        conf,
        image_size,
        "local_yolo",
    )
    addition_model = get_yolo_symbol_addition_model()
    if addition_model is None:
        return baseline

    addition = _predict_symbols_with_model(
        addition_model,
        image,
        conf,
        image_size,
        "local_yolo_ensemble_addition",
    )
    addition_classes = {
        normalize_roboflow_class_name(item)
        for item in YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES
    }
    preferred_classes = {
        normalize_roboflow_class_name(item)
        for item in YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES
    }
    merged, suppressed = baseline_priority_merge(
        [_ensemble_record(item) for item in baseline],
        [_ensemble_record(item) for item in addition],
        iou_threshold=YOLO_SYMBOL_ENSEMBLE_IOU_THRESHOLD,
        containment_threshold=YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_THRESHOLD,
        addition_classes=addition_classes,
        preferred_addition_classes=preferred_classes,
        addition_source="specialist",
    )
    logging.info(
        "YOLO detector ensemble returned %d baseline/specialist boxes, "
        "including %d specialist boxes; "
        "suppressed %d duplicates.",
        len(merged),
        sum(item["source_model"] == "specialist" for item in merged),
        len(suppressed),
    )
    return [item["detection"] for item in merged]


def normalize_roboflow_class_name(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    aliases = {
        "chamfer": "dimension_chamfer_text",
        "chamfer_text": "dimension_chamfer_text",
        "dimension_chamfer": "dimension_chamfer_text",
        "chamfer_callout": "dimension_chamfer_text",
        "diameter": "dimension_diameter_text",
        "diameter_text": "dimension_diameter_text",
        "dimension_diameter": "dimension_diameter_text",
        "radius": "dimension_radius_text",
        "radius_text": "dimension_radius_text",
        "dimension_radius": "dimension_radius_text",
        "metric": "dimension_metric_text",
        "metric_text": "dimension_metric_text",
        "thread": "dimension_metric_text",
        "thread_callout": "dimension_metric_text",
        "thickness": "dimension_thickness_text",
        "thickness_text": "dimension_thickness_text",
        "surface_finish": "surface_finish_text",
        "surface_finish_symbol": "surface_finish_symbol",
        "gdt": "gdt_frame_symbol",
        "gdt_frame": "gdt_frame_symbol",
        "gdt_frame_text": "gdt_frame_symbol",
        "datum": "datum_symbol",
        "datum_feature": "datum_symbol",
        "hole_callout": "hole_callout_text",
        "note": "note_text",
        "parallelism": "gdt_parallelism_symbol",
        "perpendicularity": "gdt_perpendicularity_symbol",
        "dimension": "dimension_text",
        "dimension_text": "dimension_text",
        "dimension_vertical": "dimension_vertical_text",
        "vertical_dimension": "dimension_vertical_text",
        "vertical_dimension_text": "dimension_vertical_text",
        "angle": "dimension_angle_text",
        "angle_text": "dimension_angle_text",
    }
    return aliases.get(text, text)


def iter_roboflow_predictions(value):
    if isinstance(value, dict):
        if any(key in value for key in ("x", "y", "width", "height", "bbox", "box", "points")):
            yield value
        for nested in value.values():
            yield from iter_roboflow_predictions(nested)
    elif isinstance(value, list):
        for item in value:
            yield from iter_roboflow_predictions(item)


def iter_roboflow_model_outputs(result):
    if isinstance(result, list):
        for item in result:
            yield from iter_roboflow_model_outputs(item)
        return

    if not isinstance(result, dict):
        return

    model_output = result.get("model_output")
    if isinstance(model_output, dict) and isinstance(model_output.get("predictions"), list):
        yield model_output

    for nested in result.values():
        if nested is model_output:
            continue
        yield from iter_roboflow_model_outputs(nested)


def roboflow_prediction_box(prediction, image_width, image_height):
    if "bbox" in prediction and isinstance(prediction["bbox"], (list, tuple)) and len(prediction["bbox"]) >= 4:
        x1, y1, x2, y2 = [float(value) for value in prediction["bbox"][:4]]
        if x2 <= x1 or y2 <= y1:
            x, y, width, height = x1, y1, x2, y2
            x1, y1, x2, y2 = x - width / 2, y - height / 2, x + width / 2, y + height / 2
        return clamp_crop_box(int(x1), int(y1), int(x2), int(y2), image_width, image_height)

    if "box" in prediction and isinstance(prediction["box"], dict):
        return roboflow_prediction_box(prediction["box"], image_width, image_height)

    if all(key in prediction for key in ("x", "y", "width", "height")):
        x = float(prediction["x"])
        y = float(prediction["y"])
        width = float(prediction["width"])
        height = float(prediction["height"])
        return clamp_crop_box(
            int(x - width / 2),
            int(y - height / 2),
            int(x + width / 2),
            int(y + height / 2),
            image_width,
            image_height,
        )

    if "points" in prediction and isinstance(prediction["points"], list) and prediction["points"]:
        xs = [float(point.get("x", 0)) for point in prediction["points"] if isinstance(point, dict)]
        ys = [float(point.get("y", 0)) for point in prediction["points"] if isinstance(point, dict)]
        if xs and ys:
            return clamp_crop_box(int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)), image_width, image_height)

    return None


def scale_roboflow_box(box, source_width, source_height, image_width, image_height):
    x1, y1, x2, y2 = box
    if source_width <= 0 or source_height <= 0:
        return clamp_crop_box(x1, y1, x2, y2, image_width, image_height)

    scale_x = image_width / source_width
    scale_y = image_height / source_height
    return clamp_crop_box(
        int(round(x1 * scale_x)),
        int(round(y1 * scale_y)),
        int(round(x2 * scale_x)),
        int(round(y2 * scale_y)),
        image_width,
        image_height,
    )


def roboflow_inference_regions(image_width, image_height):
    """Return one full-page region plus four overlapping tiles for small callouts."""
    regions = []
    if ROBOFLOW_INCLUDE_FULL_IMAGE or not ROBOFLOW_TILING_ENABLED:
        regions.append({"name": "full", "x1": 0, "y1": 0, "x2": image_width, "y2": image_height})

    if ROBOFLOW_TILING_ENABLED and len(regions) < ROBOFLOW_MAX_REGIONS:
        overlap = ROBOFLOW_TILE_OVERLAP
        tile_width = min(image_width, int(round(image_width / max(1.0, 2.0 - overlap))))
        tile_height = min(image_height, int(round(image_height / max(1.0, 2.0 - overlap))))
        x_positions = [0, max(0, image_width - tile_width)]
        y_positions = [0, max(0, image_height - tile_height)]
        for row_index, y1 in enumerate(y_positions):
            for column_index, x1 in enumerate(x_positions):
                region = {
                    "name": f"tile_{row_index + 1}_{column_index + 1}",
                    "x1": x1,
                    "y1": y1,
                    "x2": min(image_width, x1 + tile_width),
                    "y2": min(image_height, y1 + tile_height),
                }
                if not any(
                    existing["x1"] == region["x1"]
                    and existing["y1"] == region["y1"]
                    and existing["x2"] == region["x2"]
                    and existing["y2"] == region["y2"]
                    for existing in regions
                ):
                    regions.append(region)
                if len(regions) >= ROBOFLOW_MAX_REGIONS:
                    return regions
    return regions


def append_roboflow_diagnostic(
    diagnostics,
    *,
    region_name,
    source_class="",
    normalized_class="",
    confidence=0,
    box=None,
    status,
    reason="",
    detection_id="",
):
    if diagnostics is None:
        return
    x1, y1, x2, y2 = box or (0, 0, 0, 0)
    diagnostics.append(
        {
            "Detection ID": detection_id,
            "Region": region_name,
            "Source Class": source_class,
            "Normalized Class": normalized_class,
            "Confidence": round(float(confidence or 0), 4),
            "X": int(x1),
            "Y": int(y1),
            "Width": max(0, int(x2 - x1)),
            "Height": max(0, int(y2 - y1)),
            "Box": f"{int(x1)},{int(y1)},{int(x2)},{int(y2)}" if box else "",
            "Status": status,
            "Reason": reason,
        }
    )


def roboflow_detections_from_result(result, region, diagnostics=None):
    region_width = region["x2"] - region["x1"]
    region_height = region["y2"] - region["y1"]
    detections = []
    model_outputs = list(iter_roboflow_model_outputs(result))
    if not model_outputs:
        model_outputs = [
            {
                "image": {"width": region_width, "height": region_height},
                "predictions": list(iter_roboflow_predictions(result)),
            }
        ]

    prediction_index = 0
    for model_output in model_outputs:
        output_image = model_output.get("image") if isinstance(model_output.get("image"), dict) else {}
        source_width = int(float(output_image.get("width") or region_width))
        source_height = int(float(output_image.get("height") or region_height))

        for prediction in model_output.get("predictions", []):
            if not isinstance(prediction, dict):
                continue
            prediction_index += 1
            detection_id = f"{region['name']}:{prediction_index}"
            source_class = str(
                prediction.get("class")
                or prediction.get("class_name")
                or prediction.get("label")
                or prediction.get("name")
                or ""
            ).strip()
            symbol_class = normalize_roboflow_class_name(source_class)
            confidence = float(
                prediction.get("confidence")
                or prediction.get("score")
                or prediction.get("probability")
                or 0
            )
            local_box = roboflow_prediction_box(prediction, source_width, source_height)
            if not local_box:
                append_roboflow_diagnostic(
                    diagnostics,
                    region_name=region["name"],
                    source_class=source_class,
                    normalized_class=symbol_class,
                    confidence=confidence,
                    status="rejected",
                    reason="Missing or invalid bounding box",
                    detection_id=detection_id,
                )
                continue
            local_box = scale_roboflow_box(
                local_box,
                source_width,
                source_height,
                region_width,
                region_height,
            )
            lx1, ly1, lx2, ly2 = local_box
            box = (
                region["x1"] + lx1,
                region["y1"] + ly1,
                region["x1"] + lx2,
                region["y1"] + ly2,
            )
            if confidence < ROBOFLOW_CONFIDENCE:
                append_roboflow_diagnostic(
                    diagnostics,
                    region_name=region["name"],
                    source_class=source_class,
                    normalized_class=symbol_class,
                    confidence=confidence,
                    box=box,
                    status="rejected",
                    reason=f"Below confidence threshold {ROBOFLOW_CONFIDENCE:.2f}",
                    detection_id=detection_id,
                )
                continue
            if not symbol_class:
                append_roboflow_diagnostic(
                    diagnostics,
                    region_name=region["name"],
                    source_class=source_class,
                    confidence=confidence,
                    box=box,
                    status="rejected",
                    reason="Missing class name",
                    detection_id=detection_id,
                )
                continue
            if symbol_class == "note_text":
                append_roboflow_diagnostic(
                    diagnostics,
                    region_name=region["name"],
                    source_class=source_class,
                    normalized_class=symbol_class,
                    confidence=confidence,
                    box=box,
                    status="excluded",
                    reason="Notes are review-only and are not ballooned",
                    detection_id=detection_id,
                )
                continue

            x1, y1, x2, y2 = box
            detection = {
                "Symbol Class": symbol_class,
                "Confidence": round(confidence, 4),
                "X": x1,
                "Y": y1,
                "Width": x2 - x1,
                "Height": y2 - y1,
                "Box": f"{x1},{y1},{x2},{y2}",
                "Detector": "roboflow",
                "_Detection ID": detection_id,
            }
            detections.append(detection)
            append_roboflow_diagnostic(
                diagnostics,
                region_name=region["name"],
                source_class=source_class,
                normalized_class=symbol_class,
                confidence=confidence,
                box=box,
                status="candidate",
                detection_id=detection_id,
            )
    return detections


def detect_symbols_with_roboflow(image_path, image=None, diagnostics=None):
    if not ROBOFLOW_ENABLED or not ROBOFLOW_API_KEY:
        append_roboflow_diagnostic(
            diagnostics,
            region_name="configuration",
            status="disabled",
            reason="Roboflow is disabled or ROBOFLOW_API_KEY is missing",
        )
        return []

    image_path = str(image_path)
    if image is None:
        image = cv2.imread(image_path)
    if image is None:
        return []

    image_height, image_width = image.shape[:2]
    regions = roboflow_inference_regions(image_width, image_height)
    detections = []
    with tempfile.TemporaryDirectory(prefix="ocr_drawing_roboflow_") as temporary_dir:
        temporary_dir = Path(temporary_dir)
        for region_index, region in enumerate(regions):
            region_path = Path(image_path)
            if region["name"] != "full":
                crop = image[region["y1"] : region["y2"], region["x1"] : region["x2"]]
                region_path = temporary_dir / f"{region['name']}.png"
                if crop.size == 0 or not cv2.imwrite(str(region_path), crop):
                    append_roboflow_diagnostic(
                        diagnostics,
                        region_name=region["name"],
                        status="error",
                        reason="Could not create inference tile",
                    )
                    continue
            try:
                result = run_engineering_symbol_workflow(
                    str(region_path),
                    excluded_fields=["predictions.*.points"],
                )
            except RoboflowWorkflowError as exc:
                logging.warning("Roboflow workflow failed for %s: %s", region["name"], exc)
                append_roboflow_diagnostic(
                    diagnostics,
                    region_name=region["name"],
                    status="error",
                    reason=str(exc),
                )
                # Each request already exhausted the configured retries. A
                # second region would normally hit the same network/workflow
                # failure and only delay the local-YOLO fallback.
                for skipped_region in regions[region_index + 1 :]:
                    append_roboflow_diagnostic(
                        diagnostics,
                        region_name=skipped_region["name"],
                        status="skipped",
                        reason="Skipped after previous Roboflow workflow failure",
                    )
                break
            detections.extend(roboflow_detections_from_result(result, region, diagnostics))

    merged = merge_symbol_detections(detections)
    accepted = filter_implausible_symbol_detections(merged, image.shape)
    merged_ids = {item.get("_Detection ID", "") for item in merged}
    accepted_ids = {item.get("_Detection ID", "") for item in accepted}
    for row in diagnostics or []:
        if row.get("Status") != "candidate":
            continue
        detection_id = row.get("Detection ID", "")
        if detection_id in accepted_ids:
            row["Status"] = "accepted"
        elif detection_id in merged_ids:
            row["Status"] = "rejected"
            row["Reason"] = "Implausible box size"
        else:
            row["Status"] = "duplicate"
            row["Reason"] = "Duplicate detection from overlapping region"

    cleaned = []
    for detection in accepted:
        cleaned.append({key: value for key, value in detection.items() if not key.startswith("_")})
    return cleaned


def merge_symbol_detections(*detection_groups):
    merged = []
    for detections in detection_groups:
        for detection in detections or []:
            duplicate_index = None
            for index, existing in enumerate(merged):
                if detection.get("Symbol Class") != existing.get("Symbol Class"):
                    continue
                ax1, ay1 = int(detection.get("X", 0)), int(detection.get("Y", 0))
                ax2 = ax1 + int(detection.get("Width", 0))
                ay2 = ay1 + int(detection.get("Height", 0))
                bx1, by1 = int(existing.get("X", 0)), int(existing.get("Y", 0))
                bx2 = bx1 + int(existing.get("Width", 0))
                by2 = by1 + int(existing.get("Height", 0))
                ix1, iy1 = max(ax1, bx1), max(ay1, by1)
                ix2, iy2 = min(ax2, bx2), min(ay2, by2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                intersection = (ix2 - ix1) * (iy2 - iy1)
                area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
                area_b = max(1, (bx2 - bx1) * (by2 - by1))
                iou = intersection / max(1, area_a + area_b - intersection)
                if iou >= 0.45:
                    duplicate_index = index
                    break
            if duplicate_index is None:
                merged.append(detection)
                continue
            if float(detection.get("Confidence", 0) or 0) > float(merged[duplicate_index].get("Confidence", 0) or 0):
                merged[duplicate_index] = detection
    return merged


def filter_implausible_symbol_detections(detections, image_shape):
    """Remove detector boxes that are far too large to be drawing symbols."""
    if image_shape is None:
        return list(detections or [])

    image_height, image_width = image_shape[:2]
    image_area = max(1, image_width * image_height)
    compact_classes = {
        "datum_symbol",
        "gdt_frame_symbol",
        "gdt_parallelism_symbol",
        "gdt_perpendicularity_symbol",
        "revision_triangle_symbol",
        "surface_finish_symbol",
    }
    kept = []
    for detection in detections or []:
        width = int(detection.get("Width", 0) or 0)
        height = int(detection.get("Height", 0) or 0)
        if width <= 0 or height <= 0:
            continue

        width_ratio = width / max(1, image_width)
        height_ratio = height / max(1, image_height)
        area_ratio = (width * height) / image_area
        symbol_class = str(detection.get("Symbol Class", ""))
        if width_ratio > 0.40 or height_ratio > 0.35 or area_ratio > 0.04:
            continue
        if symbol_class in compact_classes and (
            width_ratio > 0.25 or height_ratio > 0.18 or area_ratio > 0.015
        ):
            continue
        kept.append(detection)
    return kept


def detect_title_block_with_yolo(image):
    model = get_yolo_titleblock_model()
    if model is None:
        return None

    try:
        results = model.predict(image, imgsz=960, conf=0.25, verbose=False)
    except Exception as exc:
        logging.warning("YOLO title-block prediction failed: %s", exc)
        return None

    if not results:
        return None

    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None

    image_height, image_width = image.shape[:2]
    detections = []
    for box in boxes:
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
        x1, y1, x2, y2 = clamp_crop_box(x1, y1, x2, y2, image_width, image_height)
        if x2 <= x1 or y2 <= y1:
            continue

        detections.append(
            {
                "box": (x1, y1, x2, y2),
                "confidence": confidence,
            }
        )

    if not detections:
        return None

    return max(detections, key=lambda item: item["confidence"])


def preprocess_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    thresholded = cv2.threshold(
        denoised,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    sharpen_kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0],
    ])
    sharpened = cv2.filter2D(thresholded, -1, sharpen_kernel)

    return sharpened


def fixed_title_block_region(image):
    image_height, image_width = image.shape[:2]
    return fallback_title_block(image_width, image_height)


def clamp_crop_box(x1, y1, x2, y2, image_width, image_height):
    return (
        max(0, int(x1)),
        max(0, int(y1)),
        min(image_width, int(x2)),
        min(image_height, int(y2)),
    )


def crop_region(image, region, padding_ratio=0.02):
    image_height, image_width = image.shape[:2]
    padding_x = int(image_width * padding_ratio)
    padding_y = int(image_height * padding_ratio)
    x1, y1, x2, y2 = clamp_crop_box(
        region.x1 - padding_x,
        region.y1 - padding_y,
        region.x2 + padding_x,
        region.y2 + padding_y,
        image_width,
        image_height,
    )
    return image[y1:y2, x1:x2], (x1, y1, x2, y2)


def crop_candidate_image(image, candidate, padding_ratio=0.01):
    image_height, image_width = image.shape[:2]
    padding_x = int(image_width * padding_ratio)
    padding_y = int(image_height * padding_ratio)
    x1, y1, x2, y2 = clamp_crop_box(
        candidate.x1 - padding_x,
        candidate.y1 - padding_y,
        candidate.x2 + padding_x,
        candidate.y2 + padding_y,
        image_width,
        image_height,
    )
    return image[y1:y2, x1:x2], (x1, y1, x2, y2)


def make_crop_candidate(name, box, source, image_width, image_height, visual_score=0.0, line_density=0.0):
    x1, y1, x2, y2 = clamp_crop_box(*box, image_width, image_height)
    if x2 <= x1 or y2 <= y1:
        return None

    return CropCandidate(
        name=name,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        source=source,
        visual_score=round(float(visual_score), 4),
        line_density=round(float(line_density), 4),
    )


def add_candidate(candidates, candidate):
    if candidate is None:
        return

    if candidate.width < 20 or candidate.height < 20:
        return

    for existing in candidates:
        if box_iou(candidate.box, existing.box) > 0.88:
            if candidate.visual_score > existing.visual_score:
                existing.name = candidate.name
                existing.x1, existing.y1, existing.x2, existing.y2 = candidate.box
                existing.source = candidate.source
                existing.visual_score = candidate.visual_score
                existing.line_density = candidate.line_density
            return

    candidates.append(candidate)


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


def score_visual_candidate(candidate, image_width, image_height):
    width_ratio = candidate.width / image_width
    height_ratio = candidate.height / image_height
    area_ratio = (candidate.width * candidate.height) / (image_width * image_height)

    size_score = 1.0 - min(abs(area_ratio - 0.12) / 0.18, 1.0)
    table_score = min(candidate.line_density, 0.22) / 0.22
    readable_size_score = min(width_ratio / 0.45, 1.0) * min(height_ratio / 0.35, 1.0)

    return (size_score * 0.35) + (table_score * 0.4) + (readable_size_score * 0.25)


def build_position_crop_candidates(image):
    image_height, image_width = image.shape[:2]
    specs = [
        ("fixed_bottom_right_small", 0.65, 0.75, 1.00, 1.00),
        ("fixed_bottom_right_medium", 0.52, 0.62, 1.00, 1.00),
        ("fixed_bottom_left", 0.00, 0.62, 0.52, 1.00),
        ("fixed_top_right", 0.52, 0.00, 1.00, 0.38),
        ("fixed_top_left", 0.00, 0.00, 0.52, 0.38),
        ("fixed_center_right", 0.45, 0.30, 1.00, 0.82),
    ]

    candidates = []
    for name, x1, y1, x2, y2 in specs:
        candidate = make_crop_candidate(
            name,
            (image_width * x1, image_height * y1, image_width * x2, image_height * y2),
            "position",
            image_width,
            image_height,
            visual_score=0.2,
        )
        add_candidate(candidates, candidate)

    return candidates


def build_table_crop_candidates(image, table_candidates):
    image_height, image_width = image.shape[:2]
    candidates = []

    for index, table_candidate in enumerate(table_candidates):
        x1, y1, x2, y2 = table_candidate["box"]
        candidate = make_crop_candidate(
            f"table_candidate_{index + 1}",
            (x1, y1, x2, y2),
            "table_detection",
            image_width,
            image_height,
            line_density=table_candidate.get("line_density", 0.0),
        )
        if candidate is None:
            continue

        candidate.visual_score = round(score_visual_candidate(candidate, image_width, image_height), 4)
        add_candidate(candidates, candidate)

    return candidates


def build_crop_candidates(image, max_candidates=6):
    table_candidates = find_table_candidates(image)
    candidates = []

    for candidate in build_table_crop_candidates(image, table_candidates):
        add_candidate(candidates, candidate)

    for candidate in build_position_crop_candidates(image):
        add_candidate(candidates, candidate)

    image_height, image_width = image.shape[:2]
    fallback = make_crop_candidate(
        "fixed_crop_fallback",
        (image_width * 0.65, image_height * 0.75, image_width, image_height),
        "fallback",
        image_width,
        image_height,
        visual_score=0.1,
    )
    add_candidate(candidates, fallback)

    image_height, image_width = image.shape[:2]
    for candidate in candidates:
        area_ratio = (candidate.width * candidate.height) / max(1, image_width * image_height)
        if area_ratio > 0.30:
            candidate.visual_score -= 0.25

    candidates.sort(key=lambda candidate: candidate.visual_score, reverse=True)
    return candidates[:max_candidates], table_candidates


def ensure_bgr(image):
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    return image


def upscale_image(image, scale):
    if scale == 1:
        return image.copy()

    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def sharpen_gray(gray):
    sharpen_kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0],
    ])
    return cv2.filter2D(gray, -1, sharpen_kernel)


def enhance_contrast(gray):
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def remove_table_lines(gray):
    binary_inv = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        12,
    )
    image_height, image_width = gray.shape
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(12, image_width // 45), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(12, image_height // 35)),
    )
    horizontal = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    line_mask = cv2.add(horizontal, vertical)
    cleaned = cv2.inpaint(gray, line_mask, 3, cv2.INPAINT_TELEA)
    return cleaned


def build_ocr_variants(crop):
    variants = []

    scaled = upscale_image(crop, 2)
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(
        gray,
        None,
        h=10,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    thresholded = cv2.threshold(
        denoised,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    contrast = enhance_contrast(gray)
    contrast_sharp = sharpen_gray(contrast)
    line_removed = remove_table_lines(contrast_sharp)
    line_removed_threshold = cv2.adaptiveThreshold(
        line_removed,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        7,
    )

    variants.extend(
        [
            {
                "name": "upscale_2x_original",
                "image": ensure_bgr(scaled),
                "debug_image": scaled,
            },
            {
                "name": "upscale_2x_otsu_sharpen",
                "image": ensure_bgr(sharpen_gray(thresholded)),
                "debug_image": sharpen_gray(thresholded),
            },
            {
                "name": "upscale_2x_adaptive",
                "image": ensure_bgr(adaptive),
                "debug_image": adaptive,
            },
            {
                "name": "upscale_2x_clahe_sharpen",
                "image": ensure_bgr(contrast_sharp),
                "debug_image": contrast_sharp,
            },
            {
                "name": "upscale_2x_line_removed",
                "image": ensure_bgr(line_removed_threshold),
                "debug_image": line_removed_threshold,
            },
        ]
    )

    return variants


def build_fast_ocr_variant(crop):
    return {
        "name": "fast_1x_original",
        "image": crop.copy(),
        "debug_image": crop.copy(),
    }


def extract_ocr_items(ocr_result):
    if not ocr_result:
        return []

    first_result = ocr_result[0]
    items = []

    if isinstance(first_result, dict):
        texts = first_result.get("rec_texts", []) or []
        scores = first_result.get("rec_scores", []) or []
        for index, text in enumerate(texts):
            score = scores[index] if index < len(scores) else None
            items.append({"text": text, "confidence": score})
        return items

    for line in first_result or []:
        try:
            text = line[1][0]
            score = line[1][1]
        except (IndexError, TypeError):
            continue
        items.append({"text": text, "confidence": score})

    return items


def average_confidence(ocr_items):
    scores = [
        float(item["confidence"])
        for item in ocr_items
        if item.get("confidence") is not None
    ]

    if not scores:
        return 0.0

    return sum(scores) / len(scores)


def score_ocr_text(ocr_items):
    text_lines = [str(item.get("text", "")).strip() for item in ocr_items if item.get("text")]
    joined_text = "\n".join(text_lines).upper()
    confidence = average_confidence(ocr_items)
    label_hits = count_title_keywords(joined_text)
    identifier_hits = len(DRAWING_NUMBER_PATTERN.findall(joined_text))
    text_length_score = min(len(joined_text) / 600, 1.0)
    line_score = min(len(text_lines) / 18, 1.0)

    return (
        confidence * 0.45
        + min(label_hits / 5, 1.0) * 0.25
        + min(identifier_hits, 1) * 0.15
        + text_length_score * 0.10
        + line_score * 0.05
    )


def count_title_keywords(text):
    upper_text = text.upper()
    return sum(1 for keyword in TITLE_KEYWORDS if keyword.upper() in upper_text)


def score_crop_candidate(candidate, ocr_result, image_shape):
    image_height, image_width = image_shape[:2]
    text = ocr_result["text"]
    keyword_hits = count_title_keywords(text)
    identifier_hits = len(DRAWING_NUMBER_PATTERN.findall(text.upper()))
    area_ratio = (candidate.width * candidate.height) / max(1, image_width * image_height)
    size_penalty = 0.0
    if area_ratio > 0.45:
        size_penalty = min((area_ratio - 0.45) / 0.35, 1.0) * 0.25
    elif area_ratio < 0.015:
        size_penalty = min((0.015 - area_ratio) / 0.015, 1.0) * 0.2

    keyword_score = min(keyword_hits / 7, 1.0)
    identifier_score = min(identifier_hits, 1)
    visual_score = min(candidate.visual_score, 1.0)

    score = (
        ocr_result["selection_score"] * 0.42
        + keyword_score * 0.25
        + identifier_score * 0.18
        + visual_score * 0.10
        + min(candidate.line_density, 0.2) / 0.2 * 0.05
        - size_penalty
    )

    return max(0.0, score), keyword_hits, identifier_hits


def is_strong_crop_candidate(evaluated_result):
    return (
        evaluated_result["crop_score"] >= 0.72
        and evaluated_result["keyword_hits"] >= 5
        and evaluated_result["identifier_hits"] >= 1
        and evaluated_result["ocr_result"]["confidence"] >= 0.80
    )


def is_strong_ocr_result(candidate):
    return (
        candidate["confidence"] >= 0.85
        and candidate["line_count"] >= 10
        and candidate["selection_score"] >= 0.60
    )


def is_good_yolo_fast_ocr_result(ocr_result):
    return (
        ocr_result["confidence"] >= 0.80
        and len(DRAWING_NUMBER_PATTERN.findall(ocr_result["text"].upper())) >= 1
    )


def run_best_ocr(ocr, crop):
    best = None

    for variant in build_ocr_variants(crop):
        result = ocr.predict(variant["image"])
        items = extract_ocr_items(result)
        lines = [item["text"] for item in items if item.get("text")]
        score = score_ocr_text(items)
        candidate = {
            "variant_name": variant["name"],
            "result": result,
            "items": items,
            "text": "\n".join(lines),
            "confidence": average_confidence(items),
            "selection_score": score,
            "line_count": len(lines),
            "text_length": len("\n".join(lines)),
            "debug_image": variant["debug_image"],
        }

        if best is None or candidate["selection_score"] > best["selection_score"]:
            best = candidate

        if is_strong_ocr_result(candidate):
            break

    return best or {
        "variant_name": "",
        "result": None,
        "items": [],
        "text": "",
        "confidence": 0.0,
        "selection_score": 0.0,
        "line_count": 0,
        "text_length": 0,
        "debug_image": crop,
    }


def run_ocr_variant(ocr, crop, variant):
    result = ocr.predict(variant["image"])
    items = extract_ocr_items(result)
    lines = [item["text"] for item in items if item.get("text")]
    text = "\n".join(lines)
    return {
        "variant_name": variant["name"],
        "result": result,
        "items": items,
        "text": text,
        "confidence": average_confidence(items),
        "selection_score": score_ocr_text(items),
        "line_count": len(lines),
        "text_length": len(text),
        "debug_image": variant["debug_image"],
    }


def run_fast_ocr(ocr, crop):
    variant = build_fast_ocr_variant(crop)
    return run_ocr_variant(ocr, crop, variant)


def select_title_block_with_ocr(ocr, image, max_candidates=6):
    yolo_detection = detect_title_block_with_yolo(image)
    if yolo_detection and yolo_detection["confidence"] >= YOLO_TITLEBLOCK_CONFIDENCE:
        x1, y1, x2, y2 = yolo_detection["box"]
        candidate = CropCandidate(
            name="yolo_title_block",
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            source="yolo",
            visual_score=1.0,
        )
        final_crop, crop_box = crop_candidate_image(image, candidate)
        final_ocr = run_fast_ocr(ocr, final_crop)
        if not is_good_yolo_fast_ocr_result(final_ocr):
            final_ocr = run_best_ocr(ocr, final_crop)
        final_score, final_keyword_hits, final_identifier_hits = score_crop_candidate(
            candidate,
            final_ocr,
            image.shape,
        )
        regions = {
            "title_block": Region(
                label="title_block",
                x1=crop_box[0],
                y1=crop_box[1],
                x2=crop_box[2],
                y2=crop_box[3],
                confidence=round(float(yolo_detection["confidence"]), 4),
                method="yolo_title_block",
            )
        }
        diagnostics = {
            "crop_method": "yolo_title_block",
            "crop_source": "yolo",
            "crop_confidence": round(float(yolo_detection["confidence"]), 4),
            "crop_box": crop_box,
            "crop_keyword_hits": final_keyword_hits,
            "crop_identifier_hits": final_identifier_hits,
            "crop_candidate_count": 1,
            "layout_candidate_count": 0,
            "evaluated_candidates": [
                {
                    "name": "yolo_title_block",
                    "source": "yolo",
                    "box": crop_box,
                    "crop_score": round(final_score, 4),
                    "keyword_hits": final_keyword_hits,
                    "identifier_hits": final_identifier_hits,
                    "ocr_confidence": round(final_ocr["confidence"], 4),
                    "ocr_line_count": final_ocr["line_count"],
                    "yolo_confidence": round(float(yolo_detection["confidence"]), 4),
                }
            ],
            "regions": regions,
            "candidates": [],
        }

        return final_crop, final_ocr, diagnostics

    crop_candidates, table_candidates = build_crop_candidates(image, max_candidates=max_candidates)
    best = None
    evaluated = []

    for candidate in crop_candidates:
        crop, crop_box = crop_candidate_image(image, candidate)
        ocr_result = run_fast_ocr(ocr, crop)
        crop_score, keyword_hits, identifier_hits = score_crop_candidate(candidate, ocr_result, image.shape)
        evaluated_result = {
            "candidate": candidate,
            "crop": crop,
            "crop_box": crop_box,
            "ocr_result": ocr_result,
            "crop_score": crop_score,
            "keyword_hits": keyword_hits,
            "identifier_hits": identifier_hits,
        }
        evaluated.append(evaluated_result)

        if best is None or crop_score > best["crop_score"]:
            best = evaluated_result

        if is_strong_crop_candidate(evaluated_result):
            break

    if best is None:
        fallback_region = fixed_title_block_region(image)
        crop, crop_box = crop_region(image, fallback_region)
        ocr_result = run_best_ocr(ocr, crop)
        best = {
            "candidate": CropCandidate(
                name="fixed_crop_fallback",
                x1=crop_box[0],
                y1=crop_box[1],
                x2=crop_box[2],
                y2=crop_box[3],
                source="fallback",
                visual_score=0.1,
            ),
            "crop": crop,
            "crop_box": crop_box,
            "ocr_result": ocr_result,
            "crop_score": ocr_result["selection_score"],
            "keyword_hits": count_title_keywords(ocr_result["text"]),
            "identifier_hits": len(DRAWING_NUMBER_PATTERN.findall(ocr_result["text"].upper())),
        }
        evaluated.append(best)

    final_crop = best["crop"]
    final_ocr = run_best_ocr(ocr, final_crop)
    final_score, final_keyword_hits, final_identifier_hits = score_crop_candidate(
        best["candidate"],
        final_ocr,
        image.shape,
    )

    regions = {
        "title_block": Region(
            label="title_block",
            x1=best["crop_box"][0],
            y1=best["crop_box"][1],
            x2=best["crop_box"][2],
            y2=best["crop_box"][3],
            confidence=round(final_score, 4),
            method=best["candidate"].name,
        )
    }

    diagnostics = {
        "crop_method": best["candidate"].name,
        "crop_source": best["candidate"].source,
        "crop_confidence": round(final_score, 4),
        "crop_box": best["crop_box"],
        "crop_keyword_hits": final_keyword_hits,
        "crop_identifier_hits": final_identifier_hits,
        "crop_candidate_count": len(crop_candidates),
        "layout_candidate_count": len(table_candidates),
        "evaluated_candidates": [
            {
                "name": item["candidate"].name,
                "source": item["candidate"].source,
                "box": item["crop_box"],
                "crop_score": round(item["crop_score"], 4),
                "keyword_hits": item["keyword_hits"],
                "identifier_hits": item["identifier_hits"],
                "ocr_confidence": round(item["ocr_result"]["confidence"], 4),
                "ocr_line_count": item["ocr_result"]["line_count"],
            }
            for item in sorted(evaluated, key=lambda item: item["crop_score"], reverse=True)
        ],
        "regions": regions,
        "candidates": table_candidates,
    }

    return final_crop, final_ocr, diagnostics


def clamp_box(x, y, w, h, image_width, image_height):
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    x2 = min(image_width, int(x + w))
    y2 = min(image_height, int(y + h))
    return x1, y1, x2, y2


def build_line_mask(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        12,
    )

    image_height, image_width = gray.shape
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(20, image_width // 55), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(20, image_height // 55)),
    )

    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    line_mask = cv2.add(horizontal, vertical)

    connect_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(5, image_width // 240), max(5, image_height // 240)),
    )
    return cv2.dilate(line_mask, connect_kernel, iterations=2)


def find_table_candidates(image):
    image_height, image_width = image.shape[:2]
    line_mask = build_line_mask(image)
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    page_area = image_width * image_height

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        x1, y1, x2, y2 = clamp_box(x, y, w, h, image_width, image_height)
        box_area = max(1, (x2 - x1) * (y2 - y1))

        area_ratio = box_area / page_area

        if area_ratio < 0.002:
            continue
        if area_ratio > 0.40:
            continue
        if w < image_width * 0.08 or h < image_height * 0.03:
            continue

        roi = line_mask[y1:y2, x1:x2]
        line_density = cv2.countNonZero(roi) / box_area
        aspect_ratio = (x2 - x1) / max(1, y2 - y1)

        if line_density < 0.02:
            continue

        candidates.append(
            {
                "box": (x1, y1, x2, y2),
                "area_ratio": area_ratio,
                "line_density": line_density,
                "aspect_ratio": aspect_ratio,
            }
        )

    return candidates


def score_title_block(candidate, image_width, image_height):
    x1, y1, x2, y2 = candidate["box"]
    cx = (x1 + x2) / 2 / image_width
    cy = (y1 + y2) / 2 / image_height
    area = candidate["area_ratio"]
    density = min(candidate["line_density"], 0.25) / 0.25

    bottom_score = max(0.0, (cy - 0.45) / 0.55)
    right_score = max(0.0, (cx - 0.35) / 0.65)
    size_score = min(area / 0.18, 1.0)

    return (bottom_score * 0.38) + (right_score * 0.28) + (size_score * 0.2) + (density * 0.14)


def fallback_title_block(image_width, image_height):
    return Region(
        label="title_block",
        x1=int(image_width * 0.65),
        y1=int(image_height * 0.75),
        x2=image_width,
        y2=image_height,
        confidence=0.25,
        method="fixed_crop_fallback",
    )


def make_region(label, candidate, confidence):
    x1, y1, x2, y2 = candidate["box"]
    return Region(label=label, x1=x1, y1=y1, x2=x2, y2=y2, confidence=round(confidence, 4))


def overlaps(a, b, padding=0):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (
        ax2 + padding <= bx1
        or bx2 + padding <= ax1
        or ay2 + padding <= by1
        or by2 + padding <= ay1
    )


def detect_layout_regions(image):
    image_height, image_width = image.shape[:2]
    candidates = find_table_candidates(image)

    regions = {}
    used_boxes = []

    if candidates:
        title_candidate = max(
            candidates,
            key=lambda candidate: score_title_block(candidate, image_width, image_height),
        )
        confidence = score_title_block(title_candidate, image_width, image_height)
        if confidence >= 0.55:
            title_region = make_region("title_block", title_candidate, confidence)
        else:
            title_region = fallback_title_block(image_width, image_height)
    else:
        title_region = fallback_title_block(image_width, image_height)

    regions["title_block"] = title_region
    used_boxes.append((title_region.x1, title_region.y1, title_region.x2, title_region.y2))

    remaining = [
        candidate
        for candidate in candidates
        if not overlaps(candidate["box"], used_boxes[0], padding=8)
    ]

    title_box = used_boxes[0]
    title_x1, title_y1, title_x2, _ = title_box

    revision_candidates = [
        candidate
        for candidate in remaining
        if candidate["box"][2] > title_x1
        and candidate["box"][0] < title_x2
        and candidate["box"][3] <= title_y1 + image_height * 0.05
    ]
    if revision_candidates:
        revision = max(
            revision_candidates,
            key=lambda candidate: candidate["line_density"] + candidate["area_ratio"],
        )
        regions["revision_table"] = make_region("revision_table", revision, 0.45)
        used_boxes.append(revision["box"])

    remaining = [
        candidate
        for candidate in remaining
        if not any(overlaps(candidate["box"], used_box, padding=8) for used_box in used_boxes)
    ]

    bom_candidates = [
        candidate
        for candidate in remaining
        if candidate["area_ratio"] > 0.015 and candidate["aspect_ratio"] < 4.5
    ]
    if bom_candidates:
        bom = max(
            bom_candidates,
            key=lambda candidate: candidate["area_ratio"] * 0.7 + candidate["line_density"] * 0.3,
        )
        regions["bom_table"] = make_region("bom_table", bom, 0.4)
        used_boxes.append(bom["box"])

    remaining = [
        candidate
        for candidate in remaining
        if not any(overlaps(candidate["box"], used_box, padding=8) for used_box in used_boxes)
    ]

    notes_candidates = [
        candidate
        for candidate in remaining
        if candidate["box"][0] < image_width * 0.65 and candidate["area_ratio"] > 0.01
    ]
    if notes_candidates:
        notes = max(notes_candidates, key=lambda candidate: candidate["area_ratio"])
        regions["notes_area"] = make_region("notes_area", notes, 0.35)

    return regions, candidates


def draw_debug(image, regions):
    output = image.copy()
    colors = {
        "title_block": (0, 180, 0),
        "revision_table": (0, 165, 255),
        "bom_table": (255, 0, 0),
        "notes_area": (180, 0, 180),
    }

    for label, region in regions.items():
        color = colors.get(label, (120, 120, 120))
        cv2.rectangle(output, (region.x1, region.y1), (region.x2, region.y2), color, 3)
        text = f"{label} {region.confidence:.2f}"
        cv2.putText(
            output,
            text,
            (region.x1, max(24, region.y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )

    return output


def save_detection(image_path, image, regions, candidates):
    image_height, image_width = image.shape[:2]
    payload = {
        "source_image": image_path.name,
        "image_size": {"width": image_width, "height": image_height},
        "regions": {label: asdict(region) for label, region in regions.items()},
        "candidate_count": len(candidates),
    }

    (LAYOUT_REGIONS_DIR / f"{image_path.stem}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    debug_image = draw_debug(image, regions)
    cv2.imwrite(str(DEBUG_LAYOUT_DIR / f"{image_path.stem}.png"), debug_image)


def process_image(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    regions, candidates = detect_layout_regions(image)
    save_detection(image_path, image, regions, candidates)
    return regions
