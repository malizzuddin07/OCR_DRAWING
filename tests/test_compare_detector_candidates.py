import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from compare_detector_candidates import (  # noqa: E402
    box_iou,
    classwise_nms,
    drawing_issues,
)


class DetectorCandidateComparisonTests(unittest.TestCase):
    def test_box_iou_handles_identical_and_disjoint_boxes(self):
        self.assertEqual(box_iou([10, 10, 20, 20], [10, 10, 20, 20]), 1.0)
        self.assertEqual(box_iou([0, 0, 5, 5], [10, 10, 5, 5]), 0.0)

    def test_classwise_nms_keeps_highest_confidence_duplicate(self):
        predictions = [
            {
                "class_name": "dimension",
                "box": [10, 10, 20, 20],
                "confidence": 0.9,
            },
            {
                "class_name": "dimension",
                "box": [11, 11, 20, 20],
                "confidence": 0.7,
            },
            {
                "class_name": "gdt_frame",
                "box": [10, 10, 20, 20],
                "confidence": 0.8,
            },
        ]
        kept = classwise_nms(predictions)
        self.assertEqual(len(kept), 2)
        self.assertIn(0.9, [item["confidence"] for item in kept])
        self.assertIn("gdt_frame", [item["class_name"] for item in kept])

    def test_drawing_issues_distinguish_regression_fixed_and_extra(self):
        truths = [
            {"class_name": "dimension", "box": [0, 0, 20, 20], "label_id": "A"},
            {"class_name": "radius", "box": [100, 0, 20, 20], "label_id": "B"},
        ]
        baseline = [
            {"class_name": "dimension", "box": [0, 0, 20, 20], "confidence": 0.9}
        ]
        candidate = [
            {"class_name": "radius", "box": [100, 0, 20, 20], "confidence": 0.9},
            {"class_name": "dimension", "box": [200, 0, 20, 20], "confidence": 0.8},
        ]
        issues, summary = drawing_issues(truths, baseline, candidate)
        self.assertEqual(
            {item["type"] for item in issues}, {"regression", "fixed", "extra"}
        )
        self.assertEqual(summary["baseline_matches"], 1)
        self.assertEqual(summary["candidate_matches"], 1)
        self.assertEqual(summary["candidate_extras"], 1)


if __name__ == "__main__":
    unittest.main()
