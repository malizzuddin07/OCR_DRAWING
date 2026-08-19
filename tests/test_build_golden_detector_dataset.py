import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from build_golden_detector_dataset import (  # noqa: E402
    apply_box_overrides,
    characteristic_rows,
    choose_tile,
    detector_class,
    group_rows_by_box,
    normalized_yolo,
    tile_starts,
)


class GoldenDetectorDatasetTests(unittest.TestCase):
    def test_human_box_override_changes_geometry_without_changing_rows(self):
        rows = [{"Balloon No": "5", "X": 10, "Y": 20, "Width": 30, "Height": 40}]
        groups, _ = group_rows_by_box(rows)
        groups[0]["source"] = "approved_expected"
        review = {
            "drawings": {
                "DRAWING": {
                    "box_overrides": [
                        {"expected_balloon": "5", "X": 1, "Y": 2, "Width": 100, "Height": 50}
                    ]
                }
            }
        }
        self.assertEqual(apply_box_overrides("DRAWING", groups, review), 1)
        self.assertEqual(groups[0]["box"], (1.0, 2.0, 100.0, 50.0))
        self.assertEqual(groups[0]["original_box"], (10.0, 20.0, 30.0, 40.0))
        self.assertEqual(groups[0]["source"], "human_box_override")

    def test_characteristic_rows_accepts_list_and_wrapped_formats(self):
        rows = [{"Dimension": "25"}]
        self.assertIs(characteristic_rows(rows), rows)
        self.assertIs(characteristic_rows({"characteristics": rows}), rows)
        self.assertIs(characteristic_rows({"records": rows}), rows)

    def test_groups_compound_rows_into_one_physical_callout(self):
        rows = [
            {"X": 10, "Y": 20, "Width": 100, "Height": 30, "Measurement Type": "metric_thread"},
            {"X": 10, "Y": 20, "Width": 100, "Height": 30, "Measurement Type": "hole_callout"},
        ]
        groups, invalid = group_rows_by_box(rows)
        self.assertFalse(invalid)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["rows"]), 2)

    def test_class_priority_keeps_thread_and_depth_as_thread_callout(self):
        rows = [
            {"Measurement Type": "hole_callout"},
            {"Measurement Type": "metric_thread"},
        ]
        self.assertEqual(detector_class(rows), "thread_callout")

    def test_unmapped_dimension_types_use_dimension_class(self):
        self.assertEqual(detector_class([{"Measurement Type": "plain_dimension"}]), "dimension")
        self.assertEqual(detector_class([{"Measurement Type": "reference_dimension"}]), "dimension")

    def test_tile_starts_include_final_image_edge(self):
        starts = tile_starts(3306, 1280, 320)
        self.assertEqual(starts[0], 0)
        self.assertEqual(starts[-1], 3306 - 1280)

    def test_choose_tile_places_box_fully_inside_one_tile(self):
        tiles = [(0, 0, 1280, 1280), (960, 0, 1280, 1280)]
        tile = choose_tile((1100, 100, 80, 40), tiles)
        self.assertIsNotNone(tile)
        self.assertLessEqual(tile[0], 1100)
        self.assertLessEqual(1100 + 80, tile[0] + tile[2])

    def test_yolo_coordinates_are_relative_to_tile(self):
        values = normalized_yolo((100, 200, 50, 20), (0, 0, 1000, 1000))
        self.assertEqual(values, (0.125, 0.21, 0.05, 0.02))


if __name__ == "__main__":
    unittest.main()
