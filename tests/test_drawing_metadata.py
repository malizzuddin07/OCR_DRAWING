import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from drawing_metadata import infer_part_name, parse_metric_general_tolerances  # noqa: E402


class DrawingMetadataToleranceTests(unittest.TestCase):
    def test_explicit_metric_decimal_labels_are_parsed(self):
        text = "METRIC .XXXX +/- 0.005 mm .XXX +/- 0.025 mm .XX +/- 0.05 mm .X +/- 0.1 mm"
        self.assertEqual(
            parse_metric_general_tolerances(text),
            {4: 0.005, 3: 0.025, 2: 0.05, 1: 0.1},
        )

    def test_metric_values_are_recovered_when_ocr_drops_row_labels(self):
        text = """METRIC
X +/- 0.005 mm
+/- 0.025 mm
0.05 mm
+/- 0.1 mm
DWG NO. C3010-035-250F
"""
        self.assertEqual(
            parse_metric_general_tolerances(text),
            {4: 0.005, 3: 0.025, 2: 0.05, 1: 0.1},
        )

    def test_unbounded_numbers_are_not_treated_as_tolerance_table(self):
        text = "METRIC 112.0 86.0 0.01 1.2 DWG NO. TEST"
        self.assertEqual(parse_metric_general_tolerances(text), {})

    def test_part_name_recovers_text_joined_to_drawn_by(self):
        lines = [
            "498789",
            "LTP1,",
            "PULLEY",
            "SUPPORTPRAWN BY",
            "DATECHECKED BY",
        ]
        self.assertEqual(infer_part_name(lines), "LTP1, PULLEY SUPPORT")

    def test_part_name_recovers_word_emitted_after_fused_drawn_by(self):
        lines = [
            "Singapore 498789",
            "PLATE,",
            "LTP1,",
            "SUPPORTPRAWN BY",
            "PULLEY",
            "DATE",
            "CHECKED BY",
        ]
        self.assertEqual(infer_part_name(lines), "PLATE, LTP1, PULLEY SUPPORT")

    def test_part_name_recovers_split_ocr_drawn_by_marker(self):
        lines = [
            "PLATE,",
            "LTP1,",
            "SUPPORTPRAWN",
            "BY",
            "PULLEY",
            "DATE",
        ]
        self.assertEqual(infer_part_name(lines), "PLATE, LTP1, PULLEY SUPPORT")


if __name__ == "__main__":
    unittest.main()
