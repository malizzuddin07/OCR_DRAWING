"""Train or evaluate the isolated general-purpose detector Candidate V9."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "golden_tests" / "detector_training_package_v7"
CLASS_NAMES = (
    "dimension",
    "diameter",
    "radius",
    "chamfer_callout",
    "thread_callout",
    "hole_callout",
    "surface_finish",
    "gdt_frame",
)


def validate_package(package: Path) -> dict:
    manifest_path = package / "training_package_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {
        "schema_version": 7,
        "status": "prepared_not_trained",
        "approved_label_count": 966,
        "approved_drawing_count": 17,
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise ValueError(f"Invalid approved package {key}: {manifest.get(key)!r}")
    if manifest.get("c3010_used_for_training"):
        raise ValueError("Reserved C3010 drawing must not enter Candidate V9 training.")
    if not manifest.get("drawing_level_split_no_tile_leakage"):
        raise ValueError("Drawing-level split protection is missing.")
    for split in ("train", "val", "test"):
        for folder, suffix in (("images", ".png"), ("labels", ".txt")):
            files = list((package / folder / split).glob(f"*{suffix}"))
            if not files:
                raise ValueError(f"Candidate V9 {folder}/{split} is empty.")
    return manifest


def write_runtime_yaml(package: Path) -> Path:
    path = package / "runtime_data.yaml"
    lines = [
        f"path: '{package.resolve().as_posix()}'",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--evaluate-test", action="store_true")
    parser.add_argument("--confirm-start", action="store_true")
    return parser.parse_args()


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch

    return "0" if torch.cuda.is_available() else "cpu"


def metric_value(metrics, name: str):
    value = getattr(metrics.box, name, None)
    return None if value is None else float(value)


def main() -> None:
    args = parse_args()
    manifest = validate_package(args.package)
    data = write_runtime_yaml(args.package)
    device = resolve_device(args.device)
    run = ROOT / "runs" / "candidate_detector" / "golden_detector_v9"

    print(json.dumps({
        "package": str(args.package),
        "data": str(data),
        "starting_model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": device,
        "resume": args.resume,
        "evaluate_test": args.evaluate_test,
        "approved_drawings": manifest["approved_drawing_count"],
        "approved_labels": manifest["approved_label_count"],
        "production_model_will_change": False,
    }, indent=2))

    if not args.confirm_start:
        print("Candidate V9 package check passed. Training was NOT started.")
        return
    if device == "cpu":
        raise RuntimeError("CUDA GPU is unavailable; Candidate V9 training is blocked.")

    from ultralytics import YOLO

    if args.evaluate_test:
        best = run / "weights" / "best.pt"
        if not best.is_file():
            raise FileNotFoundError(best)
        metrics = YOLO(str(best)).val(
            data=str(data), split="test", imgsz=args.imgsz, batch=1,
            device=device, conf=0.001, iou=0.7, plots=True,
            project=str(run), name="held_out_test", exist_ok=True,
        )
        report = {
            "split": "test",
            "precision": metric_value(metrics, "mp"),
            "recall": metric_value(metrics, "mr"),
            "map50": metric_value(metrics, "map50"),
            "map50_95": metric_value(metrics, "map"),
            "production_model_will_change": False,
        }
        (run / "held_out_test_metrics.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return

    if args.resume:
        last = run / "weights" / "last.pt"
        if not last.is_file():
            raise FileNotFoundError(last)
        YOLO(str(last)).train(resume=True, device=device)
        return

    model = Path(args.model)
    if not model.is_absolute():
        model = ROOT / model
    if not model.is_file():
        raise FileNotFoundError(model)

    YOLO(str(model)).train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        patience=25,
        optimizer="AdamW",
        lr0=0.0005,
        lrf=0.05,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        warmup_bias_lr=0.0,
        cos_lr=True,
        freeze=0,
        box=10.0,
        cls=0.5,
        dfl=1.5,
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.05,
        degrees=0.5,
        translate=0.03,
        scale=0.08,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.0,
        mosaic=0.2,
        mixup=0.0,
        cutmix=0.0,
        copy_paste=0.0,
        erasing=0.0,
        close_mosaic=10,
        seed=42,
        deterministic=True,
        workers=2,
        cache=False,
        save_period=10,
        project=str(ROOT / "runs" / "candidate_detector"),
        name="golden_detector_v9",
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
