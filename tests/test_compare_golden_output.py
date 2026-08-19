import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from compare_golden_output import (  # noqa: E402
    compare_characteristic_geometry,
    compare_characteristic_values,
    compare_rows,
)


def fa_row(balloon, value, symbol=""):
    return {
        "BALLOON NO": balloon,
        "SYMBOL": symbol,
        "VALUE": value,
        "-": "",
        "+": "",
        "MIN": "",
        "MAX": "",
        "REMARKS": "",
    }


def characteristic(balloon, value, x, y, width=80, height=30, symbol=""):
    return {
        "Balloon No": balloon,
        "Report Symbol": symbol,
        "Symbol": symbol,
        "Dimension": value,
        "Tolerance -": "",
        "Tolerance +": "",
        "MIN": "",
        "MAX": "",
        "Measurement Type": "plain_dimension",
        "X": x,
        "Y": y,
        "Width": width,
        "Height": height,
    }


class GoldenComparisonTests(unittest.TestCase):
    def test_row_order_does_not_create_false_differences(self):
        expected = [fa_row("1", "195.5"), fa_row("2", "25")]
        current = [fa_row("2", "25"), fa_row("1", "195.5")]
        self.assertEqual(compare_rows(expected, current), [])

    def test_balloon_renumbering_is_reported(self):
        differences = compare_rows([fa_row("8", "195.5")], [fa_row("9", "195.5")])
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["COLUMN"], "BALLOON NO")

    def test_missing_and_extra_characteristics_are_reported(self):
        differences = compare_rows([fa_row("1", "25")], [fa_row("1", "25"), fa_row("2", "3")])
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["COLUMN"], "ROW")
        self.assertEqual(differences[0]["EXPECTED"], "<MISSING>")

    def test_position_change_is_reported_by_balloon_identity(self):
        expected = [{"Balloon No": "7", "X": 100, "Y": 100, "Width": 50, "Height": 20}]
        current = [{"Balloon No": "7", "X": 200, "Y": 100, "Width": 50, "Height": 20}]
        issues = compare_characteristic_geometry(expected, current)
        self.assertTrue(any(item["type"] == "position_changed" for item in issues))

    def test_small_box_variation_is_allowed(self):
        expected = [{"Balloon No": "7", "X": 100, "Y": 100, "Width": 50, "Height": 20}]
        current = [{"Balloon No": "7", "X": 105, "Y": 98, "Width": 54, "Height": 22}]
        self.assertEqual(compare_characteristic_geometry(expected, current), [])

    def test_position_match_accepts_same_characteristic_after_renumbering(self):
        expected = [characteristic("55", "25", 1365, 2783, 124, 39, "Ra")]
        current = [characteristic("45", "25", 1363, 2777, 133, 47, "Ra")]
        self.assertEqual(compare_characteristic_values(expected, current), [])
        self.assertEqual(compare_characteristic_geometry(expected, current), [])

    def test_position_match_reports_wrong_value_as_one_incorrect_characteristic(self):
        expected = [characteristic("8", "195.5", 100, 100)]
        current = [characteristic("7", "95.5", 103, 98)]
        differences = compare_characteristic_values(expected, current)
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["COLUMN"], "CHARACTERISTIC")

    def test_distant_characteristic_is_missing_and_extra(self):
        expected = [characteristic("1", "25", 100, 100)]
        current = [characteristic("1", "25", 1000, 1000)]
        differences = compare_characteristic_values(expected, current)
        self.assertEqual(len(differences), 2)
        self.assertTrue(all(item["COLUMN"] == "ROW" for item in differences))


if __name__ == "__main__":
    unittest.main()
