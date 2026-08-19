import argparse
import sys
import time
from pathlib import Path

import cv2
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATASET_IMAGES_DIR,
    DEBUG_SYMBOL_DETECTION_DIR,
    SYMBOL_DETECTION_OUTPUT_PATH,
    YOLO_SYMBOL_CONFIDENCE,
    YOLO_SYMBOL_MODEL_CANDIDATES,
    YOLO_SYMBOL_REVIEW_THRESHOLD,
    ensure_directories,
)
from exporter import sanitize_dataframe_for_excel


SYMBOL_DEFINITIONS = {
    "datum_symbol": "Datum reference marker used as a measurement reference.",
    "dimension_chamfer_symbol": "Chamfer dimension for an angled or beveled edge.",
    "dimension_diameter_symbol": "Diameter dimension for a circular feature or hole.",
    "dimension_metric_symbol": "Metric thread or metric dimension callout.",
    "dimension_radius_symbol": "Radius dimension for an arc or rounded corner.",
    "dimension_thickness_symbol": "Thickness dimension for plate or wall thickness.",
    "gdt_frame_symbol": "GD&T feature control frame containing geometric tolerance requirements.",
    "gdt_parallelism_symbol": "GD&T parallelism tolerance symbol.",
    "gdt_perpendicularity_symbol": "GD&T perpendicularity tolerance symbol.",
    "revision_triangle_symbol": "Revision marker showing drawing change location.",
    "surface_finish_symbol": "Surface finish or roughness requirement symbol.",
}

DEFAULT_SYMBOL_CLASSES = {
    "datum_symbol",
    "dimension_chamfer_symbol",
    "dimension_diameter_symbol",
    "dimension_radius_symbol",
    "gdt_perpendicularity_symbol",
    "revision_triangle_symbol",
    "surface_finish_symbol",
}

WEAK_SYMBOL_CLASSES = {
    "dimension_metric_symbol",
    "dimension_thickness_symbol",
    "gdt_frame_symbol",
    "gdt_parallelism_symbol",
}

CLASS_COLORS = {
    "datum_symbol": (220, 70, 40),
    "dimension_chamfer_symbol": (60, 160, 220),
    "dimension_diameter_symbol": (50, 180, 90),
    "dimension_metric_symbol": (60, 60, 220),
    "dimension_radius_symbol": (160, 80, 200),
    "dimension_thickness_symbol": (80, 180, 180),
    "gdt_frame_symbol": (30, 140, 240),
    "gdt_parallelism_symbol": (40, 200, 80),
    "gdt_perpendicularity_symbol": (30, 220, 30),
    "revision_triangle_symbol": (210, 50, 210),
    "surface_finish_symbol": (220, 180, 40),
}


def resolve_symbol_model(model_path=None):
    if model_path:
        path = Path(model_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Symbol model not found: {path}")

    for path in YOLO_SYMBOL_MODEL_CANDIDATES:
        if path.exists():
            return path

    candidates = "\n".join(str(path) for path in YOLO_SYMBOL_MODEL_CANDIDATES)
    raise FileNotFoundError(f"No symbol model found. Checked:\n{candidates}")


def get_image_paths(image_path=None, limit=None):
    if image_path:
        paths = [Path(image_path)]
    else:
        paths = sorted(DATASET_IMAGES_DIR.glob("*.png"))

    if limit:
        paths = paths[:limit]

    return paths


def class_ids_for_names(model, class_names):
    names = model.names
    if isinstance(names, dict):
        items = names.items()
    else:
        items = enumerate(names)

    wanted = set(class_names)
    return [int(class_id) for class_id, name in items if str(name) in wanted]


def format_box(x1, y1, x2, y2):
    return f"{int(x1)},{int(y1)},{int(x2)},{int(y2)}"


def review_reason(symbol_class, confidence, review_threshold):
    reasons = []
    if confidence < review_threshold:
        reasons.append("Low confidence")
    if symbol_class in WEAK_SYMBOL_CLASSES:
        reasons.append("Weak class")
    return "; ".join(reasons)


def create_detection_row(source_file, symbol_class, confidence, x1, y1, x2, y2, review_threshold):
    reason = review_reason(symbol_class, confidence, review_threshold)
    width = x2 - x1
    height = y2 - y1
    return {
        "Source File": source_file,
        "Symbol Class": symbol_class,
        "Definition": SYMBOL_DEFINITIONS.get(symbol_class, ""),
        "Confidence": round(float(confidence), 4),
        "X": int(x1),
        "Y": int(y1),
        "Width": int(width),
        "Height": int(height),
        "Box": format_box(x1, y1, x2, y2),
        "Needs Review": "YES" if reason else "NO",
        "Review Reason": reason,
        "Human Correction": "",
    }


def draw_detection(image, symbol_class, confidence, x1, y1, x2, y2):
    color = CLASS_COLORS.get(symbol_class, (0, 180, 255))
    cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

    label = f"{symbol_class} {confidence:.2f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.45
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(label, font, scale, thickness)
    label_x = int(x1)
    label_y = max(int(y1) - text_height - baseline - 4, 0)
    cv2.rectangle(
        image,
        (label_x, label_y),
        (label_x + text_width + 6, label_y + text_height + baseline + 6),
        color,
        -1,
    )
    cv2.putText(
        image,
        label,
        (label_x + 3, label_y + text_height + 2),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def save_symbol_workbook(rows, output_path):
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(
            columns=[
                "Source File",
                "Symbol Class",
                "Definition",
                "Confidence",
                "X",
                "Y",
                "Width",
                "Height",
                "Box",
                "Needs Review",
                "Review Reason",
                "Human Correction",
            ]
        )

    df = sanitize_dataframe_for_excel(df)
    df.to_excel(output_path, index=False)


def run_symbol_detection(
    image_paths,
    model_path,
    confidence,
    review_threshold,
    class_names,
    image_size,
    output_path,
):
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    class_ids = class_ids_for_names(model, class_names) if class_names else None
    rows = []
    failed = []

    DEBUG_SYMBOL_DETECTION_DIR.mkdir(parents=True, exist_ok=True)

    for image_path in image_paths:
        start = time.perf_counter()
        image = cv2.imread(str(image_path))
        if image is None:
            failed.append(str(image_path))
            print(f"{image_path.name}: could not read image")
            continue

        result = model.predict(
            image,
            imgsz=image_size,
            conf=confidence,
            classes=class_ids,
            verbose=False,
        )[0]

        debug_image = image.copy()
        boxes = getattr(result, "boxes", None)
        count = 0

        if boxes is not None:
            for box in boxes:
                class_id = int(box.cls[0])
                symbol_class = str(model.names[class_id])
                confidence_score = float(box.conf[0])
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                rows.append(
                    create_detection_row(
                        source_file=image_path.name,
                        symbol_class=symbol_class,
                        confidence=confidence_score,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        review_threshold=review_threshold,
                    )
                )
                draw_detection(debug_image, symbol_class, confidence_score, x1, y1, x2, y2)
                count += 1

        debug_path = DEBUG_SYMBOL_DETECTION_DIR / image_path.name
        cv2.imwrite(str(debug_path), debug_image)
        elapsed = time.perf_counter() - start
        print(f"{image_path.name}: {count} symbols detected in {elapsed:.1f}s")

    save_symbol_workbook(rows, output_path)
    return rows, failed


def parse_class_filter(value):
    if not value:
        return sorted(DEFAULT_SYMBOL_CLASSES)
    if value.lower() == "all":
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    parser = argparse.ArgumentParser(description="Detect engineering drawing symbols and export review Excel.")
    parser.add_argument("--image", type=Path, help="Optional single PNG/JPG image to process.")
    parser.add_argument("--limit", type=int, help="Optional number of images to process.")
    parser.add_argument("--model", type=Path, help="Optional YOLO symbol model path.")
    parser.add_argument("--conf", type=float, default=YOLO_SYMBOL_CONFIDENCE, help="YOLO confidence threshold.")
    parser.add_argument(
        "--review-threshold",
        type=float,
        default=YOLO_SYMBOL_REVIEW_THRESHOLD,
        help="Rows below this confidence are marked Needs Review.",
    )
    parser.add_argument("--imgsz", type=int, default=1280, help="YOLO inference image size.")
    parser.add_argument(
        "--classes",
        default=",".join(sorted(DEFAULT_SYMBOL_CLASSES)),
        help="Comma-separated class names to include, or 'all'.",
    )
    parser.add_argument("--output", type=Path, default=SYMBOL_DETECTION_OUTPUT_PATH, help="Excel output path.")
    args = parser.parse_args()

    ensure_directories()
    model_path = resolve_symbol_model(args.model)
    image_paths = get_image_paths(args.image, args.limit)
    class_names = parse_class_filter(args.classes)

    if not image_paths:
        print(f"No images found in {DATASET_IMAGES_DIR}")
        return

    print(f"Symbol model: {model_path}")
    print(f"Images: {len(image_paths)}")
    print(f"Confidence: {args.conf}")
    print(f"Classes: {', '.join(class_names) if class_names else 'all'}")
    print()

    rows, failed = run_symbol_detection(
        image_paths=image_paths,
        model_path=model_path,
        confidence=args.conf,
        review_threshold=args.review_threshold,
        class_names=class_names,
        image_size=args.imgsz,
        output_path=args.output,
    )

    print()
    print(f"Saved symbol review workbook: {args.output}")
    print(f"Saved debug images: {DEBUG_SYMBOL_DETECTION_DIR}")
    print(f"Total detections: {len(rows)}")
    print(f"Failed images: {', '.join(failed) if failed else 'None'}")


if __name__ == "__main__":
    main()
