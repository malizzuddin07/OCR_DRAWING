"""Validate or train the isolated detector candidate v3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = PROJECT_ROOT / "golden_tests" / "detector_training_package_v3"
CLASS_NAMES = [
    "dimension",
    "diameter",
    "radius",
    "chamfer_callout",
    "thread_callout",
    "hole_callout",
    "surface_finish",
    "gdt_frame",
]


def validate_package(package: Path):
    manifest_path = package / "training_package_manifest.json"
    data_path = package / "data.yaml"
    if not manifest_path.is_file() or not data_path.is_file():
        raise FileNotFoundError("Training package v3 is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise ValueError("Training package schema is not v3")
    if manifest.get("status") != "prepared_not_trained":
        raise ValueError("Package status is not prepared_not_trained")
    if manifest.get("approved_label_count") != 639:
        raise ValueError("Approved label count is not 639")
    if manifest.get("approved_drawing_count") != 11:
        raise ValueError("Approved drawing count is not 11")
    if not manifest.get("all_classes_present_in_every_split"):
        raise ValueError("Every split must contain all eight classes")
    for split in ("train", "val", "test"):
        counts = manifest["class_counts_by_split"][split]
        missing = [name for name in CLASS_NAMES if int(counts.get(name, 0)) <= 0]
        if missing:
            raise ValueError(f"{split} is missing classes: {missing}")
    for name, target in manifest["rare_class_targets"].items():
        effective = manifest["effective_train_class_counts"].get(name, 0)
        if int(effective) < int(target):
            raise ValueError(f"Effective {name} count is below its target")
    return manifest


def write_runtime_data_yaml(package: Path):
    runtime_path = package / "runtime_data.yaml"
    lines = [
        f"path: '{package.resolve().as_posix()}'",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    runtime_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="candidate_detector_v1_best.pt")
    parser.add_argument("--epochs", type=int, default=100)
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
    manifest = validate_package(args.package)
    runtime_data = write_runtime_data_yaml(args.package)
    device = resolved_device(args.device)
    plan = {
        "package": str(args.package),
        "runtime_data": str(runtime_data),
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "requested_device": args.device,
        "resolved_device": device,
        "resume": args.resume,
        "approved_drawings": manifest["approved_drawing_count"],
        "approved_labels": manifest["approved_label_count"],
        "effective_train_class_counts": manifest["effective_train_class_counts"],
        "production_model_will_change": False,
    }
    print(json.dumps(plan, indent=2))
    if not args.confirm_start:
        print("Package check passed. Training was NOT started.")
        return
    if device == "cpu" and not args.allow_cpu:
        raise RuntimeError("CUDA GPU is unavailable; candidate training is blocked.")

    from ultralytics import YOLO

    run_root = PROJECT_ROOT / "runs" / "candidate_detector" / "golden_detector_v3"
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
        data=str(runtime_data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        patience=25,
        optimizer="AdamW",
        lr0=0.0002,
        lrf=0.1,
        weight_decay=0.0005,
        warmup_epochs=2.0,
        warmup_bias_lr=0.0,
        cos_lr=True,
        freeze=10,
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.05,
        degrees=0.0,
        translate=0.02,
        scale=0.05,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.0,
        mosaic=0.0,
        mixup=0.0,
        cutmix=0.0,
        copy_paste=0.0,
        erasing=0.0,
        close_mosaic=0,
        seed=42,
        deterministic=True,
        workers=2,
        cache=False,
        save_period=10,
        project=str(PROJECT_ROOT / "runs" / "candidate_detector"),
        name="golden_detector_v3",
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
