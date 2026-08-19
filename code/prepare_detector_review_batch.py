"""Prepare machine-proposed detector labels for human review.

The output is deliberately unapproved. It becomes training data only after a
human checks the clean label preview and the normal OCR review artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_golden_detector_dataset import detector_class, draw_preview, group_rows_by_box  # noqa: E402


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_json(path: Path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def proposal_payload(drawing, groups, invalid_rows):
    proposals = []
    for index, group in enumerate(groups, start=1):
        rows = group["rows"]
        proposals.append(
            {
                "proposal_id": index,
                "class_name": detector_class(rows),
                "box": [round(float(value), 2) for value in group["box"]],
                "balloon_numbers": [str(row.get("Balloon No", "")) for row in rows],
                "values": [
                    str(row.get("Specification", row.get("Extracted Value", "")))
                    for row in rows
                ],
                "measurement_types": [str(row.get("Measurement Type", "")) for row in rows],
                "review_decision": "pending",
                "review_note": "",
            }
        )
    return {
        "schema_version": 1,
        "drawing": drawing,
        "status": "machine_proposals_not_approved",
        "proposal_count": len(proposals),
        "invalid_row_count": len(invalid_rows),
        "proposals": proposals,
    }


def run_batch(pdf_paths, output_root: Path):
    from auto_ballooning import process_single_drawing

    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "batch_status.json"
    state = {
        "schema_version": 1,
        "status": "running",
        "started_at": utc_now(),
        "approval_status": "not_approved",
        "drawings": [],
    }
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "running"
        state["resumed_at"] = utc_now()

    known = {item["source_pdf"]: item for item in state.get("drawings", [])}
    for index, pdf_path in enumerate(pdf_paths, start=1):
        pdf_path = pdf_path.resolve()
        drawing = pdf_path.stem
        job_dir = output_root / drawing
        existing = known.get(str(pdf_path))
        if existing and existing.get("status") == "complete" and (job_dir / "label_proposals.json").is_file():
            print(f"[{index}/{len(pdf_paths)}] Skipping completed {drawing}", flush=True)
            continue

        entry = existing or {"drawing": drawing, "source_pdf": str(pdf_path)}
        if not existing:
            state["drawings"].append(entry)
        entry.update({"status": "processing", "started_at": utc_now(), "error": ""})
        save_json(state_path, state)
        print(f"[{index}/{len(pdf_paths)}] Processing {drawing}", flush=True)

        try:
            result = process_single_drawing(pdf_path, job_dir, use_cache=False)
            groups, invalid_rows = group_rows_by_box(result["rows"])
            for group in groups:
                group["class_name"] = detector_class(group["rows"])
            image = cv2.imread(str(result["original_image"]))
            if image is None:
                raise FileNotFoundError(f"Could not read {result['original_image']}")
            draw_preview(image, groups, job_dir / "labels_preview.png")
            proposals = proposal_payload(drawing, groups, invalid_rows)
            save_json(job_dir / "label_proposals.json", proposals)

            entry.update(
                {
                    "status": "complete",
                    "finished_at": utc_now(),
                    "characteristics": len(result["rows"]),
                    "physical_proposals": len(groups),
                    "invalid_rows": len(invalid_rows),
                    "labels_preview": str(job_dir / "labels_preview.png"),
                    "label_proposals": str(job_dir / "label_proposals.json"),
                    "ballooned_pdf": str(result["ballooned_pdf"]),
                    "fa_excel": str(result["fa_excel"]),
                    "processing_seconds": result["processing_timings"]["seconds"].get("total"),
                }
            )
        except Exception as exc:
            entry.update({"status": "failed", "finished_at": utc_now(), "error": str(exc)})
            state["status"] = "failed"
            save_json(state_path, state)
            raise
        save_json(state_path, state)

    state["status"] = "complete"
    state["finished_at"] = utc_now()
    save_json(state_path, state)
    print(f"Review batch complete: {output_root}", flush=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("pdfs", nargs="+", type=Path)
    args = parser.parse_args()
    missing = [str(path) for path in args.pdfs if not path.is_file()]
    if missing:
        parser.error(f"Missing PDF files: {missing}")
    run_batch(args.pdfs, args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
