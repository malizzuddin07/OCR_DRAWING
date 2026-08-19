"""Process all five approved drawings into gate-ready candidate folders."""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from auto_ballooning import process_single_drawing
from golden_quality_gate import load_manifests, run_gate

REQUIRED_COMPLETED_ARTIFACTS = (
    "fa_inspection_report.xlsx",
    "ballooned.pdf",
    "characteristics.json",
    "processing_timings.json",
)


def preload_required_ensemble():
    """Load required YOLO models before Paddle to avoid Windows DLL conflicts."""
    ensemble_required = os.getenv(
        "YOLO_SYMBOL_ENSEMBLE_REQUIRED", "0"
    ).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    from vision_tools import get_yolo_symbol_model

    baseline = get_yolo_symbol_model()
    if baseline is None:
        raise RuntimeError(
            "Required primary YOLO detector could not be preloaded; "
            "golden run blocked."
        )
    if not ensemble_required:
        print(
            "Verified primary YOLO detector before Paddle OCR initialization.",
            flush=True,
        )
        return

    from vision_tools import get_yolo_symbol_addition_model

    addition = get_yolo_symbol_addition_model()
    if addition is None:
        raise RuntimeError(
            "Required detector ensemble could not be preloaded; golden run blocked."
        )
    print(
        "Verified required detector ensemble models before Paddle OCR initialization.",
        flush=True,
    )


def json_safe_metadata(metadata):
    return {
        "part_number": str(getattr(metadata, "part_number", "") or ""),
        "drawing_number": str(getattr(metadata, "drawing_number", "") or ""),
        "revision": str(getattr(metadata, "revision", "") or ""),
        "material": str(getattr(metadata, "material", "") or ""),
        "part_name": str(getattr(metadata, "part_name", "") or ""),
        "general_tolerances": dict(getattr(metadata, "general_tolerances", {}) or {}),
    }

def verified_completed_drawings(output_root, suite):
    """Return resumable drawing IDs only when all final artifacts exist."""
    completed = {}
    for entry in suite.get("drawings", []):
        drawing_number = str(entry.get("drawing_number", "")).strip()
        if not drawing_number or entry.get("status") != "complete":
            continue
        if drawing_number in completed:
            raise ValueError(
                f"Cannot resume because {drawing_number} appears more than once."
            )
        drawing_output = output_root / drawing_number
        missing = [
            name
            for name in REQUIRED_COMPLETED_ARTIFACTS
            if not (drawing_output / name).is_file()
        ]
        if missing:
            raise ValueError(
                f"Cannot resume {drawing_number}; completed entry is missing: "
                f"{', '.join(missing)}"
            )
        completed[drawing_number] = entry
    return completed


def run_suite(
    golden_root,
    output_root,
    use_cache=False,
    report_dir=None,
    candidate_id="production-code",
    repeat_output_root=None,
    baseline_root=None,
    promotion=False,
    resume=False,
):
    golden_root = Path(golden_root)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifests = load_manifests(golden_root)
    if len(manifests) != 5:
        raise ValueError(f"Expected exactly 5 golden manifests, found {len(manifests)}.")
    if promotion and (repeat_output_root is None or baseline_root is None):
        raise ValueError("Promotion requires a second fresh output root and an active-model baseline root.")

    suite_path = output_root / "suite_run.json"
    if resume:
        if not suite_path.is_file():
            raise FileNotFoundError(
                f"Cannot resume because suite state is missing: {suite_path}"
            )
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        if bool(suite.get("use_cache")) != bool(use_cache):
            raise ValueError("Resume must use the same cache setting as the original run.")
        completed = verified_completed_drawings(output_root, suite)
        suite.setdefault("resume_events", []).append(
            {
                "resumed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "verified_completed_drawings": sorted(completed),
            }
        )
        suite["status"] = "running"
        suite.pop("finished_at", None)
    else:
        if suite_path.exists():
            raise FileExistsError(
                f"Suite state already exists: {suite_path}. Use --resume only "
                "for a verified interrupted run."
            )
        completed = {}
        suite = {
            "schema_version": 1,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "running",
            "use_cache": bool(use_cache),
            "drawings": [],
        }
    suite_path.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    preload_required_ensemble()

    for index, manifest in enumerate(manifests, start=1):
        drawing_number = manifest["drawing_number"]
        source = golden_root / manifest["source_pdf"]["path"]
        drawing_output = output_root / drawing_number
        if drawing_number in completed:
            print(
                f"[{index}/5] Reusing verified completed output for "
                f"{drawing_number}.",
                flush=True,
            )
            continue
        if drawing_output.exists() and any(drawing_output.iterdir()):
            if not resume:
                raise FileExistsError(
                    f"Output already exists for {drawing_number}: {drawing_output}. "
                    "Use a new output root so evidence from an earlier run is preserved."
                )
            backup_root = output_root / "interrupted_backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = backup_root / f"{drawing_number}_{timestamp}"
            shutil.move(str(drawing_output), str(backup))
            print(
                f"[{index}/5] Archived incomplete output to {backup}.",
                flush=True,
            )
        drawing_output.mkdir(parents=True, exist_ok=True)
        print(f"[{index}/5] Processing {drawing_number}: {source.name}", flush=True)
        try:
            result = process_single_drawing(source, drawing_output, use_cache=use_cache)
            entry = {
                "drawing_number": drawing_number,
                "status": "complete",
                "characteristics": len(result.get("rows", [])),
                "metadata": json_safe_metadata(result.get("metadata")),
                "processing_seconds": result.get("processing_timings", {}).get("seconds", {}).get("total"),
            }
        except Exception as exc:
            entry = {"drawing_number": drawing_number, "status": "failed", "error": str(exc)}
            suite["drawings"].append(entry)
            suite["status"] = "failed"
            suite["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
            raise
        suite["drawings"].append(entry)
        suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")

    if repeat_output_root is not None:
        repeat_output_root = Path(repeat_output_root)
        repeat_output_root.mkdir(parents=True, exist_ok=True)
        suite["repeat_drawings"] = []
        for index, manifest in enumerate(manifests, start=1):
            drawing_number = manifest["drawing_number"]
            source = golden_root / manifest["source_pdf"]["path"]
            drawing_output = repeat_output_root / drawing_number
            if drawing_output.exists() and any(drawing_output.iterdir()):
                raise FileExistsError(
                    f"Repeat output already exists for {drawing_number}: {drawing_output}."
                )
            drawing_output.mkdir(parents=True, exist_ok=True)
            print(f"[repeat {index}/5] Processing {drawing_number}: {source.name}", flush=True)
            result = process_single_drawing(source, drawing_output, use_cache=False)
            suite["repeat_drawings"].append(
                {
                    "drawing_number": drawing_number,
                    "status": "complete",
                    "characteristics": len(result.get("rows", [])),
                    "processing_seconds": result.get("processing_timings", {}).get("seconds", {}).get("total"),
                }
            )
            suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")

    report_dir = Path(report_dir) if report_dir else output_root / "_gate_report"
    gate = run_gate(
        golden_root,
        candidate_root=output_root,
        repeat_root=repeat_output_root,
        baseline_root=baseline_root,
        report_dir=report_dir,
        promotion=promotion,
        candidate_id=candidate_id,
    )
    suite["gate_status"] = gate["status"]
    suite["gate_report_json"] = str(gate.get("report_json", ""))
    suite["gate_report_excel"] = str(gate.get("report_excel", ""))
    suite["status"] = "passed" if gate["status"] == "PASSED" else "rejected"
    suite["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
    return suite


def main():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Process all five golden drawings for candidate evaluation.")
    parser.add_argument("--golden-root", default=str(project_root / "golden_tests"))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report-dir", help="Where the strict comparison reports are written.")
    parser.add_argument("--candidate-id", default="production-code")
    parser.add_argument("--use-cache", action="store_true", help="Developer smoke test only; promotion runs must be fresh.")
    parser.add_argument("--repeat-output-root", help="Second empty output folder for deterministic repeat processing.")
    parser.add_argument("--baseline-root", help="Previously preserved active-model output folder.")
    parser.add_argument("--promotion", action="store_true", help="Run the strict promotion gate; requires repeat and baseline roots.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted suite after verifying every completed drawing.",
    )
    args = parser.parse_args()
    try:
        suite = run_suite(
            args.golden_root,
            args.output_root,
            use_cache=args.use_cache,
            report_dir=args.report_dir,
            candidate_id=args.candidate_id,
            repeat_output_root=args.repeat_output_root,
            baseline_root=args.baseline_root,
            promotion=args.promotion,
            resume=args.resume,
        )
    except Exception as exc:
        print(f"GOLDEN SUITE FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Suite status: {suite['status']}")
    print(f"Output root: {Path(args.output_root).resolve()}")
    return 0 if suite["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
