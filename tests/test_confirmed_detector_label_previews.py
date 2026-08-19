import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from build_confirmed_detector_label_previews import apply_corrections


class ConfirmedDetectorLabelPreviewTests(unittest.TestCase):
    def setUp(self):
        self.proposals = [
            {"proposal_id": 1, "class_name": "dimension", "box": [10, 10, 20, 20]},
            {"proposal_id": 2, "class_name": "hole_callout", "box": [40, 10, 20, 20]},
            {"proposal_id": 3, "class_name": "thread_callout", "box": [70, 10, 20, 20]},
        ]

    def test_delete_replace_and_add_are_applied_once(self):
        plan = {
            "delete_ids": [1],
            "replace": [
                {
                    "source_ids": [2, 3],
                    "class_name": "thread_callout",
                    "box": [40, 10, 50, 20],
                    "reason": "merge",
                }
            ],
            "add": [
                {
                    "class_name": "gdt_frame",
                    "box": [100, 10, 30, 20],
                    "reason": "missing",
                }
            ],
        }
        labels = apply_corrections(self.proposals, plan)
        self.assertEqual(len(labels), 2)
        self.assertEqual({item["source"] for item in labels}, {
            "human_confirmed_replacement",
            "human_confirmed_missing_addition",
        })

    def test_same_proposal_cannot_be_deleted_and_replaced(self):
        plan = {
            "delete_ids": [2],
            "replace": [
                {
                    "source_ids": [2],
                    "class_name": "hole_callout",
                    "box": [40, 10, 20, 20],
                    "reason": "invalid overlap",
                }
            ],
            "add": [],
        }
        with self.assertRaises(ValueError):
            apply_corrections(self.proposals, plan)


if __name__ == "__main__":
    unittest.main()
