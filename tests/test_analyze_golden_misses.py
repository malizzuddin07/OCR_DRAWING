import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from analyze_golden_misses import group_by_box, match_groups, row_signature, select_manifests  # noqa: E402


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
    def test_gdt_spacing_is_semantically_equal(self):
        expected = row("1", 10, 10, "0.01Z")
        current = row("9", 10, 10, "0.01 Z")
        expected["Report Symbol"] = "//"
        current["Report Symbol"] = "//"
        self.assertEqual(row_signature(expected), row_signature(current))

    def test_report_symbol_overrides_duplicate_internal_symbol(self):
        expected = row("83.1", 10, 10, "5.6")
        current = row("82.1", 10, 10, "5.6")
        expected["Report Symbol"] = "6X"
        expected["Symbol"] = "6X"
        current["Report Symbol"] = "6X"
        current["Symbol"] = ""
        self.assertEqual(row_signature(expected), row_signature(current))

    def test_numeric_display_format_does_not_create_false_mismatch(self):
        expected = row("5", 10, 10, "86")
        current = row("6", 10, 10, "86.0")
        expected.update({"Tolerance -": "0.01", "Tolerance +": "0"})
        current.update({"Tolerance -": "0.010", "Tolerance +": "0.0"})
        self.assertEqual(row_signature(expected), row_signature(current))

    def test_manual_and_plain_dimension_are_semantically_equal(self):
        expected = row("10", 10, 10, "24.0")
        current = row("9", 10, 10, "24")
        expected["Measurement Type"] = "manual"
        self.assertEqual(row_signature(expected), row_signature(current))

    def test_depth_storage_types_are_semantically_equal(self):
        expected = row("15", 10, 10, "DEPTH 15")
        current = row("16", 10, 10, "DEPTH 15")
        expected["Measurement Type"] = "manual"
        current["Measurement Type"] = "hole_callout"
        self.assertEqual(row_signature(expected), row_signature(current))

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
