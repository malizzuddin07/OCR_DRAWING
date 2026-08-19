"""Validate or train the isolated detector candidate v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = PROJECT_ROOT / "golden_tests" / "detector_training_package_v2"


def validate_package(package: Path):
    manifest_path = package / "training_package_manifest.json"
    data_path = package / "data.yaml"
    if not manifest_path.is_file() or not data_path.is_file():
        raise FileNotFoundError("Training package v2 is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "prepared_not_trained":
        raise ValueError("Package status is not prepared_not_trained")
    if manifest.get("approved_label_count") != 639:
        raise ValueError("Approved label count is not 639")
    if manifest.get("approved_drawing_count") != 11:
        raise ValueError("Approved drawing count is not 11")
    if not manifest.get("train_contains_all_classes"):
        raise ValueError("Training split does not contain every class")
    return manifest, data_path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="candidate_detector_v1_best.pt")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-start", action="store_true")
    return parser.parse_args()


def resolved_device(requested):
    if requested != "auto":
        return requested
    import torch

    return "0" if torch.cuda.is_available() else "cpu"


def main():
    args = parse_args()
    manifest, data_path = validate_package(args.package)
    device = resolved_device(args.device)
    plan = {
        "package": str(args.package),
        "data": str(data_path),
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "requested_device": args.device,
        "resolved_device": device,
        "resume": args.resume,
        "approved_drawings": manifest["approved_drawing_count"],
        "approved_labels": manifest["approved_label_count"],
        "production_model_will_change": False,
    }
    print(json.dumps(plan, indent=2))
    if not args.confirm_start:
        print("Package check passed. Training was NOT started.")
        return
    if device == "cpu" and not args.allow_cpu:
        raise RuntimeError("CUDA GPU is unavailable; candidate training is blocked.")

    from ultralytics import YOLO

    run_root = PROJECT_ROOT / "runs" / "candidate_detector" / "golden_detector_v2"
    if args.resume:
        last = run_root / "weights" / "last.pt"
        if not last.is_file():
            raise FileNotFoundError(f"Resume checkpoint was not found: {last}")
        YOLO(str(last)).train(resume=True, device=device)
        return

    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    if not model_path.is_file():
        raise FileNotFoundError(f"Starting model was not found: {model_path}")
    YOLO(str(model_path)).train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        patience=35,
        seed=42,
        deterministic=True,
        workers=2,
        cache=False,
        save_period=10,
        project=str(PROJECT_ROOT / "runs" / "candidate_detector"),
        name="golden_detector_v2",
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
