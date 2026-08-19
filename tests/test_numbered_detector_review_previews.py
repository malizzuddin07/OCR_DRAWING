import sys
import unittest
from pathlib import Path

import numpy as np


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from build_numbered_detector_review_previews import draw_numbered_preview, readable_text_color


class NumberedDetectorReviewPreviewTests(unittest.TestCase):
    def test_text_color_contrasts_with_box_color(self):
        self.assertEqual(readable_text_color((20, 120, 255)), (0, 0, 0))
        self.assertEqual(readable_text_color((40, 40, 220)), (255, 255, 255))

    def test_numbered_preview_changes_pixels_without_resizing(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        proposal = {
            "proposal_id": 7,
            "class_name": "dimension",
            "box": [100, 100, 80, 40],
        }
        preview = draw_numbered_preview(image, [proposal])
        self.assertEqual(preview.shape, image.shape)
        self.assertFalse(np.array_equal(preview, image))


if __name__ == "__main__":
    unittest.main()
