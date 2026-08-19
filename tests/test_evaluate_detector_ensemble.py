import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from evaluate_detector_ensemble import (  # noqa: E402
    baseline_priority_merge,
    intersection_over_smaller,
    is_duplicate,
)


def prediction(class_name, box, confidence):
    return {
        "class_name": class_name,
        "box": box,
        "confidence": confidence,
        "tile": "tile.png",
    }


class DetectorEnsembleTests(unittest.TestCase):
    def test_merge_preserves_v3_even_when_v5_has_higher_confidence(self):
        v3 = [prediction("dimension", [10, 10, 20, 20], 0.61)]
        v5 = [prediction("dimension", [11, 11, 20, 20], 0.99)]
        merged, suppressed = baseline_priority_merge(v3, v5)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["box"], v3[0]["box"])
        self.assertEqual(merged[0]["source_model"], "v3")
        self.assertEqual(len(suppressed), 1)

    def test_merge_adds_non_duplicate_v5_detection(self):
        v3 = [prediction("dimension", [10, 10, 20, 20], 0.8)]
        v5 = [prediction("dimension", [100, 100, 20, 20], 0.9)]
        merged, suppressed = baseline_priority_merge(v3, v5)
        self.assertEqual(len(merged), 2)
        self.assertEqual({item["source_model"] for item in merged}, {"v3", "v5"})
        self.assertEqual(suppressed, [])

    def test_containing_box_is_treated_as_duplicate(self):
        v3 = prediction("gdt_frame", [20, 20, 20, 20], 0.7)
        v5 = prediction("gdt_frame", [10, 10, 40, 40], 0.9)
        self.assertEqual(intersection_over_smaller(v3["box"], v5["box"]), 1.0)
        self.assertTrue(is_duplicate(v3, v5))

    def test_containment_can_be_disabled_for_iou_only_approved_merge(self):
        v3 = prediction("gdt_frame", [20, 20, 20, 20], 0.7)
        v7 = prediction("gdt_frame", [10, 10, 40, 40], 0.9)
        self.assertLess(0.50, 1.0)
        self.assertFalse(
            is_duplicate(
                v3,
                v7,
                iou_threshold=0.50,
                containment_threshold=None,
            )
        )

    def test_different_classes_are_never_suppressed(self):
        v3 = [prediction("dimension", [10, 10, 20, 20], 0.8)]
        v5 = [prediction("gdt_frame", [10, 10, 20, 20], 0.9)]
        merged, suppressed = baseline_priority_merge(v3, v5)
        self.assertEqual(len(merged), 2)
        self.assertEqual(suppressed, [])

    def test_addition_can_be_restricted_to_selected_classes(self):
        v3 = [prediction("dimension", [10, 10, 20, 20], 0.8)]
        addition = [
            prediction("dimension", [60, 10, 20, 20], 0.9),
            prediction("gdt_frame", [60, 60, 20, 20], 0.9),
        ]
        merged, suppressed = baseline_priority_merge(
            v3,
            addition,
            addition_classes={"gdt_frame"},
        )
        self.assertEqual(
            [(item["class_name"], item["source_model"]) for item in merged],
            [("dimension", "v3"), ("gdt_frame", "v5")],
        )
        self.assertEqual(
            [item["suppression_reason"] for item in suppressed],
            ["class_not_enabled"],
        )

    def test_specialist_replaces_only_duplicate_preferred_class(self):
        v3 = [
            prediction("gdt_frame", [10, 10, 20, 20], 0.8),
            prediction("dimension", [50, 50, 20, 20], 0.8),
        ]
        specialist = [
            prediction("gdt_frame", [11, 11, 20, 20], 0.7),
            prediction("dimension", [51, 51, 20, 20], 0.99),
        ]
        merged, suppressed = baseline_priority_merge(
            v3,
            specialist,
            addition_classes={"gdt_frame"},
            preferred_addition_classes={"gdt_frame"},
            addition_source="v1",
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["source_model"], "v1")
        self.assertEqual(merged[0]["box"], specialist[0]["box"])
        self.assertEqual(merged[1]["source_model"], "v3")
        self.assertEqual(
            {item["suppression_reason"] for item in suppressed},
            {"class_not_enabled", "preferred_specialist_replaced_baseline"},
        )


if __name__ == "__main__":
    unittest.main()
