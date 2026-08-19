"""Small, fail-closed model registry for candidate evaluation and rollback."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROJECT_ROOT / "private_data" / "model_registry.json"
DEFAULT_ACTIVE_MODEL = os.getenv("ROBOFLOW_EXPECTED_MODEL_ID", "krafo/ocr-balloon-system-5-yolov8s-t1").strip()


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_registry():
    return {
        "schema_version": 1,
        "active_model": DEFAULT_ACTIVE_MODEL,
        "rollback_model": "",
        "successful_promotions": 0,
        "automatic_promotion_enabled": False,
        "models": {
            DEFAULT_ACTIVE_MODEL: {
                "model_id": DEFAULT_ACTIVE_MODEL,
                "status": "active",
                "created_at": now_utc(),
                "source": "existing_system_configuration",
            }
        },
    }


def load_registry(path=DEFAULT_REGISTRY):
    path = Path(path)
    if not path.is_file():
        return new_registry()
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(registry, path=DEFAULT_REGISTRY):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def register_candidate(registry, candidate_id, metadata=None):
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        raise ValueError("Candidate ID is required.")
    if candidate_id == registry.get("active_model"):
        raise ValueError("The active model cannot be registered as a candidate.")
    existing = registry.setdefault("models", {}).get(candidate_id)
    if existing and existing.get("status") == "active":
        raise ValueError("An active model cannot be overwritten.")
    registry["models"][candidate_id] = {
        "model_id": candidate_id,
        "status": "candidate",
        "created_at": existing.get("created_at", now_utc()) if existing else now_utc(),
        "metadata": metadata or {},
        "gate_report": "",
    }
    return registry["models"][candidate_id]


def active_model_deployment(
    registry,
    *,
    configured_model_id,
    default_workspace,
    default_workflow_id,
):
    """Resolve the registry's active model to the workflow used by inference.

    The original configured model may use the existing environment workflow.
    Every promoted candidate must have an explicit deployment mapping so a
    registry promotion cannot silently keep running the old workflow.
    """
    active_model = str(registry.get("active_model", "") or "").strip()
    record = registry.get("models", {}).get(active_model) or {}
    deployment = (record.get("metadata") or {}).get("deployment") or {}
    workspace = str(deployment.get("workspace", "") or "").strip()
    workflow_id = str(deployment.get("workflow_id", "") or "").strip()
    if not workflow_id and active_model == str(configured_model_id or "").strip():
        workspace = str(default_workspace or "").strip()
        workflow_id = str(default_workflow_id or "").strip()
    if not active_model:
        raise ValueError("The model registry has no active model.")
    if not workspace or not workflow_id:
        raise ValueError(
            f"Active model {active_model} has no Roboflow workspace/workflow deployment mapping."
        )
    return {
        "model_id": active_model,
        "workspace": workspace,
        "workflow_id": workflow_id,
    }


def load_gate_report(report_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if report.get("mode") != "promotion":
        raise ValueError("Only a strict promotion-mode golden gate report may activate a model.")
    if report.get("golden_count") != 5:
        raise ValueError("A promotion report must cover exactly five approved golden drawings.")
    drawings = report.get("drawings")
    if not isinstance(drawings, list) or len(drawings) != 5:
        raise ValueError("A promotion report must contain results for all five golden drawings.")
    drawing_numbers = {str(item.get("drawing_number", "")).strip() for item in drawings}
    if len(drawing_numbers) != 5 or "" in drawing_numbers:
        raise ValueError("Promotion drawing results must have five unique drawing numbers.")
    statuses = [
        str(item.get("status", ""))
        for drawing in drawings
        for item in drawing.get("checks", [])
    ]
    if report.get("status") == "PASSED" and (not statuses or any(status != "PASS" for status in statuses)):
        raise ValueError("A promotion report may not contain failed or skipped checks.")
    return report


def record_evaluation(registry, candidate_id, report_path):
    model = registry.get("models", {}).get(candidate_id)
    if not model or model.get("status") not in {"candidate", "rejected"}:
        raise ValueError("Register the candidate before recording its evaluation.")
    report = load_gate_report(report_path)
    report_candidate = str(report.get("candidate_id", "") or "").strip()
    if report_candidate != candidate_id:
        raise ValueError("Gate report candidate ID does not match the registered candidate.")
    model["gate_report"] = str(Path(report_path).resolve())
    model["evaluated_at"] = now_utc()
    model["gate_status"] = report.get("status", "")
    if report.get("status") != "PASSED":
        model["status"] = "rejected"
        model["rejection_reason"] = "Golden quality gate did not pass."
    else:
        model["status"] = "candidate"
    return model


def promote_candidate(registry, candidate_id, report_path, human_approved=False):
    model = record_evaluation(registry, candidate_id, report_path)
    if model.get("gate_status") != "PASSED":
        raise ValueError("Candidate rejected: the strict golden quality gate did not pass.")
    if int(registry.get("successful_promotions", 0) or 0) < 3 and not human_approved:
        raise ValueError("Human approval is required for the first three successful candidate models.")
    deployment = (model.get("metadata") or {}).get("deployment") or {}
    if not str(deployment.get("workspace", "")).strip() or not str(deployment.get("workflow_id", "")).strip():
        raise ValueError("Candidate promotion requires an explicit Roboflow workspace and workflow ID.")

    previous_active = registry.get("active_model", "")
    previous_record = registry.setdefault("models", {}).get(previous_active)
    if previous_record:
        previous_record["status"] = "rollback"
        previous_record["retired_at"] = now_utc()
    registry["rollback_model"] = previous_active
    registry["active_model"] = candidate_id
    registry["successful_promotions"] = int(registry.get("successful_promotions", 0) or 0) + 1
    registry["automatic_promotion_enabled"] = registry["successful_promotions"] >= 3
    model["status"] = "active"
    model["promoted_at"] = now_utc()
    model["human_approved"] = bool(human_approved)
    return model


def rollback_active_model(registry):
    rollback_model = str(registry.get("rollback_model", "") or "")
    active_model = str(registry.get("active_model", "") or "")
    if not rollback_model or rollback_model not in registry.get("models", {}):
        raise ValueError("No rollback model is available.")
    if active_model in registry.get("models", {}):
        registry["models"][active_model]["status"] = "rejected"
        registry["models"][active_model]["rejection_reason"] = "Post-promotion smoke test failed."
    registry["models"][rollback_model]["status"] = "active"
    registry["active_model"] = rollback_model
    registry["rollback_model"] = ""
    return registry["models"][rollback_model]


def main():
    parser = argparse.ArgumentParser(description="Safely register, evaluate, and promote OCR models.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("rollback")
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--candidate-id", required=True)
    register_parser.add_argument("--workspace", required=True)
    register_parser.add_argument("--workflow-id", required=True)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--candidate-id", required=True)
    evaluate_parser.add_argument("--report", required=True)
    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--candidate-id", required=True)
    promote_parser.add_argument("--report", required=True)
    promote_parser.add_argument("--human-approved", action="store_true")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    try:
        if args.command == "register":
            register_candidate(
                registry,
                args.candidate_id,
                metadata={
                    "deployment": {
                        "workspace": args.workspace,
                        "workflow_id": args.workflow_id,
                    }
                },
            )
            save_registry(registry, args.registry)
        elif args.command == "evaluate":
            record_evaluation(registry, args.candidate_id, args.report)
            save_registry(registry, args.registry)
        elif args.command == "promote":
            promote_candidate(registry, args.candidate_id, args.report, human_approved=args.human_approved)
            save_registry(registry, args.registry)
        elif args.command == "rollback":
            rollback_active_model(registry)
            save_registry(registry, args.registry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MODEL REGISTRY ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(registry, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
