import sys
import unittest
from pathlib import Path

import numpy as np


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from build_draft_detector_issue_previews import draw_issue, integer_box


class DraftDetectorIssuePreviewTests(unittest.TestCase):
    def test_integer_box_clamps_to_image(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        self.assertEqual(integer_box((-10, -20, 400, 300), image), (0, 0, 200, 100))

    def test_draw_issue_changes_image_without_resizing(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        original = image.copy()
        draw_issue(image, (100, 100, 80, 40), "wrong", "WRONG ID 7")
        self.assertEqual(image.shape, original.shape)
        self.assertFalse(np.array_equal(image, original))


if __name__ == "__main__":
    unittest.main()
