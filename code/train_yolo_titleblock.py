import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Train YOLO title-block detector.")
    parser.add_argument("--data", default="dataset/yolo_titleblock/data.yaml")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default=None, help="Use '0' for GPU or 'cpu' for CPU.")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install YOLO first: pip install ultralytics") from exc

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"Missing data.yaml: {data_path}")

    model = YOLO(args.model)
    train_args = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "project": "runs/titleblock",
        "name": "yolo_titleblock",
    }
    if args.device:
        train_args["device"] = args.device

    model.train(**train_args)


if __name__ == "__main__":
    main()
