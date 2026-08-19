"""Validate or train the isolated detector candidate V8."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "golden_tests" / "detector_training_package_v8"
CLASSES = [
    "dimension", "diameter", "radius", "chamfer_callout",
    "thread_callout", "hole_callout", "surface_finish", "gdt_frame",
]


def validate_package(package: Path):
    manifest = json.loads(
        (package / "training_package_manifest.json").read_text(encoding="utf-8")
    )
    checks = {
        "schema_version": 8,
        "status": "prepared_not_trained",
        "approved_label_count": 966,
        "approved_drawing_count": 17,
        "v8_focus_tile_count": 2,
        "v8_focus_repeat_count_per_tile": 3,
        "v8_focus_repeat_tile_count": 6,
    }
    for key, expected in checks.items():
        if manifest.get(key) != expected:
            raise ValueError(f"Invalid V8 manifest {key}: {manifest.get(key)!r}")
    if manifest.get("c3010_used_for_training"):
        raise ValueError("Reserved C3010 drawing must not enter training")
    if not manifest.get("test_drawings_reserved_from_candidate_v8_training"):
        raise ValueError("V8 reserved-drawing protection is missing")
    for stem in manifest["v8_focus_tile_stems"]:
        for folder, suffix in (("images", ".png"), ("labels", ".txt")):
            path = package / folder / "train" / f"{stem}{suffix}"
            if not path.is_file():
                raise FileNotFoundError(path)
    return manifest


def write_runtime_yaml(package: Path) -> Path:
    path = package / "runtime_data.yaml"
    lines = [
        f"path: '{package.resolve().as_posix()}'", "train: images/train",
        "val: images/val", "test: images/test", "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASSES))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--model", default="candidate_detector_v7_best.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-start", action="store_true")
    return parser.parse_args()


def main():
    args = arguments()
    manifest = validate_package(args.package)
    data = write_runtime_yaml(args.package)
    if args.device == "auto":
        import torch
        device = "0" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    print(json.dumps({
        "package": str(args.package), "data": str(data), "model": args.model,
        "epochs": args.epochs, "imgsz": args.imgsz, "batch": args.batch,
        "device": device, "resume": args.resume,
        "approved_labels": manifest["approved_label_count"],
        "focus_tiles": manifest["v8_focus_tile_count"],
        "focus_repeats": manifest["v8_focus_repeat_tile_count"],
        "production_model_will_change": False,
    }, indent=2))
    if not args.confirm_start:
        print("V8 package check passed. Training was NOT started.")
        return
    if device == "cpu" and not args.allow_cpu:
        raise RuntimeError("CUDA GPU is unavailable; candidate training is blocked.")

    from ultralytics import YOLO
    run = ROOT / "runs" / "candidate_detector" / "golden_detector_v8"
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
        data=str(data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=device, patience=12, optimizer="AdamW", lr0=0.000005, lrf=0.1,
        weight_decay=0.001, box=12.0, warmup_epochs=2.0,
        warmup_bias_lr=0.0, cos_lr=True, freeze=10, hsv_h=0.0, hsv_s=0.0,
        hsv_v=0.02, degrees=0.0, translate=0.01, scale=0.03, shear=0.0,
        perspective=0.0, flipud=0.0, fliplr=0.0, mosaic=0.0, mixup=0.0,
        cutmix=0.0, copy_paste=0.0, erasing=0.0, close_mosaic=0, seed=42,
        deterministic=True, workers=2, cache=False, save_period=10,
        project=str(ROOT / "runs" / "candidate_detector"),
        name="golden_detector_v8", pretrained=True, plots=True,
    )


if __name__ == "__main__":
    main()
