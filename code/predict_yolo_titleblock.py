import argparse
from pathlib import Path


DEFAULT_MODEL_CANDIDATES = [
    Path("runs/titleblock/yolo_titleblock/weights/best.pt"),
    Path("runs/detect/runs/titleblock/yolo_titleblock/weights/best.pt"),
]


def resolve_model_path(model_arg):
    if model_arg:
        model_path = Path(model_arg)
        if model_path.exists():
            return model_path
        raise SystemExit(f"Missing model weights: {model_path}")

    for model_path in DEFAULT_MODEL_CANDIDATES:
        if model_path.exists():
            return model_path

    candidates = "\n".join(f"  - {path}" for path in DEFAULT_MODEL_CANDIDATES)
    raise SystemExit(f"Missing model weights. Checked:\n{candidates}")


def main():
    parser = argparse.ArgumentParser(description="Test YOLO title-block detector.")
    parser.add_argument(
        "--model",
        default=None,
        help="Path to trained YOLO weights.",
    )
    parser.add_argument("--source", default="dataset/images")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install YOLO first: pip install ultralytics") from exc

    model_path = resolve_model_path(args.model)

    model = YOLO(str(model_path))
    model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        save=True,
        project="runs/titleblock",
        name="predict_titleblock",
    )


if __name__ == "__main__":
    main()
