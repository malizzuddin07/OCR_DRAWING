"""Development-only runner for one fresh tiled-detector OCR candidate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


def write_status(path, value):
    path.write_text(value + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    output_dir = args.output_dir.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Drawing PDF was not found: {pdf_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "runner_status.txt"
    write_status(status_path, "RUNNING")

    try:
        # Load torch/YOLO before Paddle OCR to avoid their Windows DLL conflict.
        from vision_tools import (
            get_yolo_symbol_addition_model,
            get_yolo_symbol_model,
        )

        if get_yolo_symbol_model() is None:
            raise RuntimeError("Primary YOLO symbol model could not be loaded")
        ensemble_required = os.getenv(
            "YOLO_SYMBOL_ENSEMBLE_REQUIRED", "0"
        ).strip().lower() in {"1", "true", "yes"}
        if ensemble_required and get_yolo_symbol_addition_model() is None:
            raise RuntimeError("Required specialist YOLO model could not be loaded")

        from auto_ballooning import process_single_drawing

        result = process_single_drawing(pdf_path, output_dir, use_cache=False)
        summary = {
            "status": "complete",
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pdf": str(pdf_path),
            "output_dir": str(output_dir),
            "characteristics": len(result.get("rows", [])),
            "processing_seconds": result.get("processing_timings", {})
            .get("seconds", {})
            .get("total"),
            "fa_excel": str(result.get("fa_excel", "")),
            "ballooned_pdf": str(result.get("ballooned_pdf", "")),
        }
        (output_dir / "single_candidate_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        write_status(status_path, "COMPLETED")
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    except Exception as exc:
        write_status(status_path, f"FAILED: {exc}")
        raise


if __name__ == "__main__":
    main()
