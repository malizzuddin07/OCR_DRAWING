import unittest
import sys
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from build_detector_correction_sheets import box_iou, proposal_risks


class DetectorCorrectionSheetTests(unittest.TestCase):
    def test_box_iou_detects_overlap(self):
        self.assertGreater(box_iou((0, 0, 100, 100), (50, 0, 100, 100)), 0.3)
        self.assertEqual(box_iou((0, 0, 10, 10), (20, 20, 10, 10)), 0)

    def test_proposal_risks_flags_callout_review_and_overlap(self):
        proposal = {
            "proposal_id": 1,
            "class_name": "hole_callout",
            "box": [0, 0, 100, 100],
        }
        other = {
            "proposal_id": 2,
            "class_name": "dimension",
            "box": [20, 0, 100, 100],
        }
        rows = [{"Needs Review": "NO", "AI Confidence": 0.9}]
        risks = proposal_risks(proposal, rows, [proposal, other])
        self.assertTrue(any("English callout" in reason for reason in risks))
        self.assertTrue(any("overlaps proposal 2" in reason for reason in risks))


if __name__ == "__main__":
    unittest.main()
