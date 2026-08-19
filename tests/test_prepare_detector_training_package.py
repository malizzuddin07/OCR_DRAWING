import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from prepare_detector_training_package import boxes_intersect, ink_density, split_lookup  # noqa: E402
from train_detector_candidate import resolve_device  # noqa: E402


class TrainingPackageTests(unittest.TestCase):
    def test_auto_device_uses_cpu_when_cuda_is_unavailable(self):
        class FakeCuda:
            @staticmethod
            def is_available():
                return False

        class FakeTorch:
            cuda = FakeCuda()

        self.assertEqual(resolve_device("auto", FakeTorch()), "cpu")

    def test_explicit_device_is_preserved(self):
        self.assertEqual(resolve_device("1"), "1")

    def test_split_lookup_keeps_each_drawing_in_one_split(self):
        lookup = split_lookup()
        self.assertEqual(len(lookup), 5)
        self.assertEqual(len(set(lookup)), 5)
        self.assertEqual(lookup["C3010-035-250F"], "train")
        self.assertEqual(lookup["W3-C171246401-00"], "test")

    def test_intersection_rejects_negative_tile_containing_label(self):
        self.assertTrue(boxes_intersect((0, 0, 100, 100), (90, 90, 20, 20)))
        self.assertFalse(boxes_intersect((0, 0, 100, 100), (101, 101, 20, 20)))

    def test_blank_image_has_zero_ink_density(self):
        import numpy as np

        image = np.full((20, 20, 3), 255, dtype=np.uint8)
        self.assertEqual(ink_density(image), 0.0)


if __name__ == "__main__":
    unittest.main()
