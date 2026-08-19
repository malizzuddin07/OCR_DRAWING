"""Train an isolated detector candidate from a prepared package.

The script is fail-closed: training starts only when --confirm-start is passed.
It never changes the active production model or model registry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = PROJECT_ROOT / "golden_tests" / "detector_training_package_v1"


def resolve_device(requested, torch_module=None):
    if requested != "auto":
        return requested
    if torch_module is None:
        import torch as torch_module
    return "0" if torch_module.cuda.is_available() else "cpu"


def validate_package(package_root: Path):
    manifest_path = package_root / "training_package_manifest.json"
    data_path = package_root / "data.yaml"
    if not manifest_path.is_file() or not data_path.is_file():
        raise FileNotFoundError("Training package is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "prepared_not_trained":
        raise ValueError("Training package status is not prepared_not_trained")
    if not manifest.get("train_contains_all_classes"):
        raise ValueError("Training split does not contain every detector class")
    if manifest.get("approved_label_count") != 303:
        raise ValueError("Approved label count changed")
    return manifest, data_path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-start", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    manifest, data_path = validate_package(args.package)
    device = resolve_device(args.device)
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
        "approved_labels": manifest["approved_label_count"],
        "production_model_will_change": False,
    }
    print(json.dumps(plan, indent=2))
    if not args.confirm_start:
        print("Preparation check passed. Training was NOT started.")
        print("Add --confirm-start only when candidate training is explicitly approved.")
        return

    if device == "cpu" and not args.allow_cpu:
        raise RuntimeError(
            "CUDA GPU is unavailable. Accuracy-focused 1280px CPU training is blocked by default because it may take a very long time. "
            "Use a CUDA machine/cloud trainer, or explicitly add --allow-cpu."
        )

    from ultralytics import YOLO

    run_root = PROJECT_ROOT / "runs" / "candidate_detector" / "golden_detector_v1"
    if args.resume:
        last_weights = run_root / "weights" / "last.pt"
        if not last_weights.is_file():
            raise FileNotFoundError(f"Resume checkpoint was not found: {last_weights}")
        model = YOLO(str(last_weights))
        model.train(resume=True, device=device)
        return

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        patience=30,
        seed=42,
        deterministic=True,
        workers=2,
        cache=False,
        save_period=10,
        project=str(PROJECT_ROOT / "runs" / "candidate_detector"),
        name="golden_detector_v1",
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
