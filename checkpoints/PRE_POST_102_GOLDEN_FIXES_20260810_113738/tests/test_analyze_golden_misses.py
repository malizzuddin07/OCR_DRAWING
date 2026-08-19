import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from analyze_golden_misses import group_by_box, match_groups, select_manifests  # noqa: E402


def row(balloon, x, y, value):
    return {
        "Balloon No": balloon,
        "X": x,
        "Y": y,
        "Width": 50,
        "Height": 20,
        "Dimension": value,
        "Measurement Type": "plain_dimension",
    }


class GoldenMissAnalysisTests(unittest.TestCase):
    def test_shifted_balloon_number_matches_by_position(self):
        expected, _ = group_by_box([row("2", 100, 100, "25")])
        current, _ = group_by_box([row("1", 105, 102, "25")])
        matches, missing, extra = match_groups(expected, current)
        self.assertEqual(len(matches), 1)
        self.assertEqual(missing, [])
        self.assertEqual(extra, [])

    def test_distant_current_box_is_missing_and_extra(self):
        expected, _ = group_by_box([row("1", 100, 100, "25")])
        current, _ = group_by_box([row("1", 500, 500, "25")])
        matches, missing, extra = match_groups(expected, current)
        self.assertEqual(matches, [])
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(extra), 1)

    def test_subrows_are_one_physical_callout_group(self):
        rows = [row("3.1", 100, 100, "6X 5.5"), row("3.2", 100, 100, "CBORE 11")]
        groups, invalid = group_by_box(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["rows"]), 2)
        self.assertEqual(invalid, [])

    def test_one_drawing_can_be_selected_for_focused_review(self):
        manifests = [
            {"drawing_number": "A", "golden_test_number": 1},
            {"drawing_number": "B", "golden_test_number": 2},
        ]
        self.assertEqual(select_manifests(manifests, "b"), [manifests[1]])

    def test_unknown_focused_drawing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Golden drawing was not found"):
            select_manifests([{"drawing_number": "A"}], "B")


if __name__ == "__main__":
    unittest.main()
