import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webapp.approval_data import approval_content_hash, change_counts, compare_characteristics


def row(balloon, value, x, y, width=20, height=10, symbol="", measurement_type="plain_dimension"):
    return {
        "Balloon No": balloon,
        "Dimension": value,
        "Report Symbol": symbol,
        "Measurement Type": measurement_type,
        "X": x,
        "Y": y,
        "Width": width,
        "Height": height,
    }


class ApprovalDataTests(unittest.TestCase):
    def test_reordered_items_are_unchanged(self):
        original = [row("1", "195.5", 10, 20), row("2", "25", 50, 60)]
        corrected = [dict(original[1]), dict(original[0])]

        changes = compare_characteristics(original, corrected)

        self.assertEqual(change_counts(changes), {"added": 0, "edited": 0, "deleted": 0, "moved": 0, "unchanged": 2})

    def test_added_edited_deleted_and_moved_are_separate(self):
        original = [
            row("1", "95.5", 10, 20),
            row("2", "25", 50, 60),
            row("4", "DEPTH 6", 90, 100),
        ]
        corrected = [
            row("1", "195.5", 10, 20),
            row("2", "25", 150, 160),
            row("3", "0.5", 200, 210),
        ]

        counts = change_counts(compare_characteristics(original, corrected))

        self.assertEqual(counts, {"added": 1, "edited": 1, "deleted": 1, "moved": 1, "unchanged": 0})

    def test_missing_box_is_not_detector_training_eligible(self):
        changes = compare_characteristics([], [{"Balloon No": "1", "Dimension": "3"}])
        self.assertFalse(changes[0]["detector_training_eligible"])

    def test_content_hash_is_stable_but_detects_corrections(self):
        items = [row("1", "195.5", 10, 20)]
        first = approval_content_hash("a" * 12, "b" * 64, items, {"revision": "A", "part": "P1"})
        reordered_metadata = approval_content_hash("a" * 12, "b" * 64, items, {"part": "P1", "revision": "A"})
        changed = approval_content_hash("a" * 12, "b" * 64, [row("1", "95.5", 10, 20)], {"part": "P1", "revision": "A"})
        self.assertEqual(first, reordered_metadata)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
