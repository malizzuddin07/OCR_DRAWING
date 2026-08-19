"""Build positional golden references only from human-approved correction data.

This script is intentionally separate from OCR.  It never predicts or repairs
values.  It copies the approved characteristics, including their bounding-box
and balloon settings, into the golden test folder and updates each manifest.
"""

import argparse
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_ROOT = PROJECT_ROOT / "golden_tests"
APPROVAL_ROOT = PROJECT_ROOT / "private_data" / "approvals"
GENERATED_JOB_ROOT = PROJECT_ROOT / "generated_jobs" / "jobs"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approved_items_for_manifest(manifest):
    approval_id = str(manifest.get("approval_id", ""))
    approval_path = APPROVAL_ROOT / approval_id / "approval.json"
    if approval_path.is_file():
        approval = load_json(approval_path)
        if not approval.get("confirmed_complete"):
            raise ValueError(f"Approval is not confirmed complete: {approval_path}")
        return approval.get("corrected_items", []), str(approval_path.relative_to(PROJECT_ROOT))

    job_id = str(manifest.get("job_id", ""))
    candidate_path = GENERATED_JOB_ROOT / job_id / "golden_candidate" / "corrected_items.json"
    if candidate_path.is_file() and str(manifest.get("approval_method", "")).lower() == "user_final_qc":
        return load_json(candidate_path), str(candidate_path.relative_to(PROJECT_ROOT))

    raise FileNotFoundError(
        f"No human-approved characteristic source exists for {manifest.get('drawing_number', '')}."
    )


def validate_items(manifest, items):
    expected_count = int(manifest.get("approved_characteristics", 0) or 0)
    if len(items) != expected_count:
        raise ValueError(
            f"{manifest.get('drawing_number')}: expected {expected_count} approved items, found {len(items)}."
        )
    required = ("Balloon No", "X", "Y", "Width", "Height")
    for index, item in enumerate(items, start=1):
        missing = [field for field in required if str(item.get(field, "")).strip() == ""]
        if missing:
            raise ValueError(
                f"{manifest.get('drawing_number')}: approved item {index} is missing {', '.join(missing)}."
            )


def build_references(golden_root=DEFAULT_GOLDEN_ROOT):
    golden_root = Path(golden_root)
    output_root = golden_root / "expected_characteristics"
    output_root.mkdir(parents=True, exist_ok=True)
    updated = []

    for manifest_path in sorted(golden_root.glob("*_golden_manifest.json")):
        manifest = load_json(manifest_path)
        items, source = approved_items_for_manifest(manifest)
        validate_items(manifest, items)
        drawing_number = str(manifest["drawing_number"])
        output_path = output_root / f"{drawing_number}_expected.json"
        payload = {
            "schema_version": 1,
            "drawing_number": drawing_number,
            "approval_id": manifest.get("approval_id", ""),
            "approved_source": source,
            "record_count": len(items),
            "records": items,
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["expected_characteristics"] = {
            "path": str(output_path.relative_to(golden_root)).replace("\\", "/"),
            "sha256": sha256_file(output_path),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        updated.append((drawing_number, len(items), output_path))
    return updated


def main():
    parser = argparse.ArgumentParser(description="Build positional references from approved corrections.")
    parser.add_argument("--golden-root", default=str(DEFAULT_GOLDEN_ROOT))
    args = parser.parse_args()
    for drawing, count, path in build_references(args.golden_root):
        print(f"{drawing}: {count} approved characteristics -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
