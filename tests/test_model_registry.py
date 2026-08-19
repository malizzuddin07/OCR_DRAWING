import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from model_registry import (  # noqa: E402
    active_model_deployment,
    new_registry,
    promote_candidate,
    record_evaluation,
    register_candidate,
)


class ModelRegistryTests(unittest.TestCase):
    def write_report(self, folder, candidate_id, status):
        path = Path(folder) / f"{status}.json"
        path.write_text(
            json.dumps(
                {
                    "mode": "promotion",
                    "status": status,
                    "candidate_id": candidate_id,
                    "golden_count": 5,
                    "drawings": [
                        {
                            "drawing_number": f"DRAWING-{number}",
                            "checks": [{"name": "strict gate", "status": "PASS" if status == "PASSED" else "FAIL"}],
                        }
                        for number in range(1, 6)
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_failed_gate_rejects_candidate_without_changing_active_model(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = new_registry()
            active = registry["active_model"]
            register_candidate(registry, "candidate-1")
            record_evaluation(registry, "candidate-1", self.write_report(folder, "candidate-1", "REJECTED"))
            self.assertEqual(registry["active_model"], active)
            self.assertEqual(registry["models"]["candidate-1"]["status"], "rejected")

    def test_first_three_promotions_require_human_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = new_registry()
            active = registry["active_model"]
            register_candidate(registry, "candidate-1", metadata={"deployment": {"workspace": "krafo", "workflow_id": "candidate-workflow"}})
            report = self.write_report(folder, "candidate-1", "PASSED")
            with self.assertRaisesRegex(ValueError, "Human approval"):
                promote_candidate(registry, "candidate-1", report, human_approved=False)
            self.assertEqual(registry["active_model"], active)

    def test_passed_gate_and_human_approval_preserve_rollback_model(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = new_registry()
            active = registry["active_model"]
            register_candidate(registry, "candidate-1", metadata={"deployment": {"workspace": "krafo", "workflow_id": "candidate-workflow"}})
            report = self.write_report(folder, "candidate-1", "PASSED")
            promote_candidate(registry, "candidate-1", report, human_approved=True)
            self.assertEqual(registry["active_model"], "candidate-1")
            self.assertEqual(registry["rollback_model"], active)
            self.assertEqual(registry["models"][active]["status"], "rollback")

    def test_promoted_model_without_workflow_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = new_registry()
            register_candidate(registry, "candidate-1")
            report = self.write_report(folder, "candidate-1", "PASSED")
            with self.assertRaisesRegex(ValueError, "workflow ID"):
                promote_candidate(registry, "candidate-1", report, human_approved=True)

    def test_active_deployment_uses_promoted_workflow(self):
        registry = new_registry()
        registry["active_model"] = "candidate-1"
        registry["models"]["candidate-1"] = {
            "metadata": {"deployment": {"workspace": "krafo", "workflow_id": "candidate-workflow"}}
        }
        deployment = active_model_deployment(
            registry,
            configured_model_id="old-model",
            default_workspace="old-workspace",
            default_workflow_id="old-workflow",
        )
        self.assertEqual(deployment["model_id"], "candidate-1")
        self.assertEqual(deployment["workflow_id"], "candidate-workflow")


if __name__ == "__main__":
    unittest.main()
