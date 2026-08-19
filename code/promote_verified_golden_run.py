"""Promote a human-approved OCR run into a golden reference safely.

The command refuses promotion when the comparison contains missing or
incorrect characteristics, or when the approved extra characteristic does not
match the requested specification. Existing golden artifacts are backed up
before any replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def issue_rows(report) -> list[dict]:
    if isinstance(report, list):
        return report
    if isinstance(report, dict) and isinstance(report.get("results"), list):
        return [
            row
            for result in report["results"]
            for row in (result.get("issues") or [])
        ]
    if isinstance(report, dict) and isinstance(report.get("results"), dict):
        return list(report["results"].get("issues") or [])
    for key in ("issues", "records", "rows"):
        rows = report.get(key) if isinstance(report, dict) else None
        if isinstance(rows, list):
            return rows
    return []


def normalized_issue_type(row: dict) -> str:
    return str(
        row.get("issue_type")
        or row.get("Issue Type")
        or row.get("Issue")
        or row.get("status")
        or row.get("Status")
        or ""
    ).strip().lower()


def issue_specification(row: dict) -> str:
    for key in (
        "current_specification",
        "Current Specification",
        "specification",
        "Specification",
        "current_value",
        "Current Value",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--approved-extra-specification", required=True)
    args = parser.parse_args()

    golden_root = args.golden_root.resolve()
    run_root = args.run_root.resolve()
    job = run_root / "job"
    report_path = run_root / "missed_characteristics_analysis" / "missed_characteristics.json"
    manifest_path = golden_root / f"{args.drawing}_golden_manifest.json"

    required = {
        "comparison report": report_path,
        "candidate characteristics": job / "characteristics.json",
        "candidate Excel": job / "fa_inspection_report.xlsx",
        "candidate PDF": job / "ballooned.pdf",
        "candidate layout": job / "balloon_layout.json",
        "golden manifest": manifest_path,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.is_file()]
    if missing:
        raise SystemExit("Missing required files:\n" + "\n".join(missing))

    report = load_json(report_path)
    rows = issue_rows(report)
    missing_rows = [row for row in rows if normalized_issue_type(row) == "missing"]
    wrong_rows = [
        row for row in rows if normalized_issue_type(row) in {"wrong", "incorrect"}
    ]
    extra_rows = [row for row in rows if normalized_issue_type(row) == "extra"]
    if missing_rows or wrong_rows:
        raise SystemExit(
            f"Promotion rejected: missing={len(missing_rows)}, incorrect={len(wrong_rows)}"
        )
    if len(extra_rows) != 1:
        raise SystemExit(f"Promotion rejected: expected exactly 1 approved extra, found {len(extra_rows)}")
    actual_extra = issue_specification(extra_rows[0])
    actual_nominal = actual_extra.split()[0] if actual_extra else ""
    if actual_nominal != args.approved_extra_specification:
        raise SystemExit(
            "Promotion rejected: approved extra mismatch: "
            f"expected {args.approved_extra_specification!r}, found {actual_extra!r}"
        )

    characteristics = load_json(job / "characteristics.json")
    if not isinstance(characteristics, list) or not characteristics:
        raise SystemExit("Candidate characteristics must be a non-empty JSON list")
    layout = load_json(job / "balloon_layout.json")
    if int(layout.get("issue_count", -1)) != 0:
        raise SystemExit(f"Promotion rejected: layout issue count is {layout.get('issue_count')}")

    manifest = load_json(manifest_path)
    expected_json = golden_root / manifest["expected_characteristics"]["path"]
    expected_excel = golden_root / manifest["expected_excel"]["path"]
    expected_pdf = golden_root / manifest["expected_pdf"]["path"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_extra = "".join(
        character if character.isalnum() or character in {"-", "."} else "_"
        for character in args.approved_extra_specification
    )
    backup = golden_root / "backups" / (
        f"{args.drawing}_{timestamp}_before_approved_{safe_extra}"
    )
    backup.mkdir(parents=True, exist_ok=False)
    for source in (manifest_path, expected_json, expected_excel, expected_pdf):
        shutil.copy2(source, backup / source.name)

    wrapper = {
        "schema_version": 1,
        "drawing_number": args.drawing,
        "approval_id": manifest.get("approval_id", ""),
        "approved_source": str((job / "characteristics.json").relative_to(golden_root)),
        "record_count": len(characteristics),
        "records": characteristics,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "update_reason": f"User approved new characteristic {args.approved_extra_specification}",
    }
    expected_json.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(job / "fa_inspection_report.xlsx", expected_excel)
    shutil.copy2(job / "ballooned.pdf", expected_pdf)

    manifest["approved_characteristics"] = len(characteristics)
    manifest["main_balloons"] = int(layout["record_count"])
    manifest["valid_crops"] = sum(
        1
        for row in characteristics
        if int(row.get("Width", 0) or 0) > 0 and int(row.get("Height", 0) or 0) > 0
    )
    manifest["approval_method"] = (
        "protected_approve_endpoint_user_final_qc_and_verified_golden_update"
    )
    manifest["last_golden_update"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run": str(run_root.relative_to(golden_root)),
        "approved_extra_specification": args.approved_extra_specification,
        "comparison": {"missing": 0, "incorrect": 0, "extra_approved": 1},
        "layout_issue_count": 0,
        "backup": str(backup.relative_to(golden_root)),
    }
    manifest["expected_characteristics"]["sha256"] = sha256(expected_json)
    manifest["expected_excel"]["sha256"] = sha256(expected_excel)
    manifest["expected_pdf"]["sha256"] = sha256(expected_pdf)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Promoted {args.drawing}: {len(characteristics)} characteristics")
    print(f"Physical balloons: {layout['record_count']}")
    print(f"Backup: {backup}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
