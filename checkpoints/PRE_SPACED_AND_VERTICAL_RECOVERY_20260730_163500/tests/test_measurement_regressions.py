import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from auto_ballooning import (  # noqa: E402
    balloon_circle_radius,
    build_balloon_layout_diagnostics,
    build_characteristics,
    classify_gdt_symbol_crop,
    circle_overlaps_frame,
    create_gdt_characteristic_rows,
    detector_ocr_candidate_is_better,
    is_report_excluded,
    load_or_run_content_measurements,
    normalize_compound_callout_rows,
    normalize_depth_display_text,
    normalize_fa_export_row,
    parse_compound_hole_callout_rows,
    parse_counterbore_rows,
    parse_drill_depth_rows,
    parse_fit_dimension_fields,
    parse_tolerance,
    remark_for_row,
    separate_mild_frame_overlaps,
    tight_balloon_frame_box,
)
from measurement_extraction import classify_measurement  # noqa: E402
from vision_tools import detect_symbols_with_yolo  # noqa: E402


class MeasurementRegressionTests(unittest.TestCase):
    def test_local_yolo_broad_classes_use_pipeline_class_names(self):
        box = type(
            "Box",
            (),
            {
                "cls": np.array([0]),
                "conf": np.array([0.9]),
                "xyxy": np.array([[10, 20, 80, 50]]),
            },
        )()
        model = type(
            "Model",
            (),
            {
                "names": {0: "dimension"},
                "predict": lambda self, *args, **kwargs: [type("Result", (), {"boxes": [box]})()],
            },
        )()

        with patch("vision_tools.get_yolo_symbol_model", return_value=model):
            detections = detect_symbols_with_yolo(np.zeros((100, 200, 3), dtype=np.uint8))

        self.assertEqual(detections[0]["Symbol Class"], "dimension_text")

    def test_fresh_measurement_run_bypasses_existing_content_cache(self):
        cached_row = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "95.5",
            "X": 1,
            "Y": 2,
            "Width": 3,
            "Height": 4,
        }
        fresh_row = dict(cached_row, **{"Extracted Value": "195.5"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pdf_path = root / "drawing.pdf"
            image_path = root / "drawing.png"
            cache_path = root / "measurement_cache.xlsx"
            pdf_path.write_bytes(b"drawing")
            image_path.write_bytes(b"image")
            pd.DataFrame([cached_row]).to_excel(cache_path, index=False)
            with patch("auto_ballooning.content_measurement_cache_path", return_value=cache_path), patch(
                "auto_ballooning.run_ocr_measurements", return_value=[fresh_row]
            ) as fresh_ocr:
                rows, source = load_or_run_content_measurements(
                    pdf_path,
                    root,
                    image_path,
                    allow_cache=False,
                )

            fresh_ocr.assert_called_once_with(image_path)
            self.assertEqual(source, "fresh_ocr")
            self.assertEqual(rows[0]["Extracted Value"], "195.5")

    def test_balloon_circle_size_follows_number_length(self):
        self.assertEqual(balloon_circle_radius("7"), 21)
        self.assertEqual(balloon_circle_radius("39"), 24)
        self.assertEqual(balloon_circle_radius("105"), 28)
        self.assertEqual(balloon_circle_radius("39", 0.85), 20)

    def test_complete_plain_numbers_are_preserved(self):
        for value in ("195.5", "25", "0.5"):
            measurement_type, extracted = classify_measurement(value)
            self.assertEqual(measurement_type, "plain_dimension")
            self.assertEqual(extracted, value)

    def test_positive_only_tolerance_is_separate_from_nominal(self):
        self.assertEqual(
            parse_tolerance("3 +0.09", apply_general=False),
            ("3", "", "0.09", "3", "3.09"),
        )

    def test_asymmetric_negative_tolerances_keep_upper_and_lower_sides(self):
        self.assertEqual(
            parse_tolerance("20 -0.009/-0.025", apply_general=False),
            ("20", "0.025", "-0.009", "19.975", "19.991"),
        )
        self.assertEqual(
            parse_tolerance("19 +0 -0.05", apply_general=False),
            ("19", "0.05", "0", "18.95", "19"),
        )

    def test_wider_detector_crop_can_restore_missing_leading_digit(self):
        partial = (1.20, 0.90, "normal", "plain_dimension", "95.5", "95.5")
        complete = (1.15, 0.84, "normal", "plain_dimension", "195.5", "195.5")
        weak = (1.15, 0.70, "normal", "plain_dimension", "195.5", "195.5")
        self.assertTrue(detector_ocr_candidate_is_better(partial, complete))
        self.assertFalse(detector_ocr_candidate_is_better(partial, weak))

    def test_fit_dimension_is_split_into_engineering_fields(self):
        fields = parse_fit_dimension_fields("\u23004 H8 +0.018 / 0")
        self.assertEqual(fields["symbol"], "Ø")
        self.assertEqual(fields["nominal"], "4")
        self.assertEqual(fields["tolerance_class"], "H8")
        self.assertEqual(fields["minus"], "0.000")
        self.assertEqual(fields["plus"], "+0.018")
        self.assertEqual(fields["minimum"], "4.000")
        self.assertEqual(fields["maximum"], "4.018")

    def test_fit_dimension_without_diameter_keeps_symbol_blank(self):
        fields = parse_fit_dimension_fields("4 H8 +0.018 / 0")
        self.assertEqual(fields["symbol"], "")
        self.assertEqual(fields["nominal"], "4")
        self.assertEqual(fields["tolerance_class"], "H8")

    def test_fit_dimension_export_keeps_canonical_diameter_and_numeric_limits(self):
        exported = normalize_fa_export_row(
            {
                "Balloon No": "1",
                "Report Symbol": "\u2300",
                "Dimension": "4",
                "Tolerance Class": "H8",
                "Tolerance -": "0.000",
                "Tolerance +": "+0.018",
                "MIN": "4.000",
                "MAX": "4.018",
                "Review Reason": "",
            }
        )
        self.assertEqual(exported["SYMBOL"], "Ø")
        self.assertEqual(exported["VALUE"], "4")
        self.assertEqual(exported["-"], "0.000")
        self.assertEqual(exported["+"], "+0.018")
        self.assertEqual(exported["MIN"], "4.000")
        self.assertEqual(exported["MAX"], "4.018")
        self.assertEqual(exported["REMARKS"], "")

    def test_fit_class_is_kept_in_remarks_when_symbol_is_blank(self):
        exported = normalize_fa_export_row(
            {
                "Balloon No": "1",
                "Report Symbol": "",
                "Dimension": "4",
                "Tolerance Class": "H8",
                "Tolerance -": "0.000",
                "Tolerance +": "+0.018",
                "MIN": "4.000",
                "MAX": "4.018",
                "Review Reason": "",
            }
        )
        self.assertEqual(exported["SYMBOL"], "")
        self.assertEqual(exported["REMARKS"], "Tolerance Class: H8")

    def test_grouped_two_negative_fit_tolerance_overrides_partial_ocr_limits(self):
        source = {
            "Source File": "drawing.png",
            "Measurement Type": "diameter",
            "Extracted Value": "Ø34.5 g6 +0 -0.025",
            "OCR Text": "Ø34.5g6-0.025",
            "OCR Confidence": "0.86",
            "Grouped Tolerance -": "0.025",
            "Grouped Tolerance +": "-0.009",
            "X": "100",
            "Y": "100",
            "Width": "80",
            "Height": "40",
            "Box": "100,100,180,140",
        }
        rows, rejected = build_characteristics([source], "drawing.png")
        self.assertEqual(rejected, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tolerance -"], "0.025")
        self.assertEqual(rows[0]["Tolerance +"], "-0.009")
        self.assertEqual(rows[0]["MIN"], "34.475")
        self.assertEqual(rows[0]["MAX"], "34.491")

    def test_duplicate_depth_text_is_reduced_to_one_depth(self):
        rows = parse_drill_depth_rows("DEPTH6DEPTH6")
        self.assertEqual([row["dimension"] for row in rows], ["DEPTH 6"])

    def test_counterbore_keeps_counterbore_and_depth_as_separate_values(self):
        rows = parse_counterbore_rows("CBORE11 DP7")
        self.assertEqual(rows[0]["symbol"], "CBORE")
        self.assertEqual(rows[0]["dimension"], "11")
        self.assertEqual(rows[1]["symbol"], "")
        self.assertEqual(rows[1]["dimension"], "DEPTH 7")

    def test_compound_hole_callout_splits_thru_counterbore_and_depth(self):
        rows = parse_compound_hole_callout_rows("6X 5.6 THRU CBORE12 DP10")
        self.assertEqual(len(rows), 8)
        self.assertEqual([row["dimension"] for row in rows[:6]], ["5.6"] * 6)
        self.assertEqual(rows[6]["symbol"], "CBORE")
        self.assertEqual(rows[6]["dimension"], "12")
        self.assertEqual(rows[7]["dimension"], "DEPTH 10")

    def test_compound_hole_callout_builds_three_stable_balloon_groups(self):
        source = {
            "Source File": "drawing.png",
            "Measurement Type": "hole_callout",
            "Extracted Value": "6X 5.6 THRU CBORE12 DP10",
            "OCR Text": "6X 5.6 THRU CBORE12 DP10",
            "OCR Confidence": 0.99,
            "X": 100,
            "Y": 100,
            "Width": 300,
            "Height": 70,
            "OCR Orientation": "pdf_text_layer",
        }
        rows, rejected = build_characteristics([source], "drawing.png")
        self.assertEqual(rejected, [])
        self.assertEqual(
            [row["Balloon No"] for row in rows],
            ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "2", "3"],
        )
        self.assertEqual(rows[6]["Symbol"], "CBORE")
        self.assertEqual(rows[7]["Dimension"], "DEPTH 10")

    def test_exact_pdf_hole_callout_is_not_deleted_by_fixed_page_zone(self):
        row = {
            "Measurement Type": "hole_callout",
            "Extracted Value": "CBORE12 DP10",
            "OCR Text": "CBORE12 DP10",
            "OCR Orientation": "pdf_text_layer",
            "X": 2300,
            "Y": 2500,
            "Width": 220,
            "Height": 40,
        }
        self.assertFalse(is_report_excluded(row, image_shape=(3200, 4500, 3)))

    def test_depth_display_always_has_one_space(self):
        self.assertEqual(normalize_depth_display_text("DEPTH6"), "DEPTH 6")
        self.assertEqual(normalize_depth_display_text("DEPTH   15"), "DEPTH 15")
        self.assertEqual(normalize_depth_display_text("SCREW DEPTH12"), "SCREW DEPTH 12")
        self.assertIn("DEPTH 15", normalize_depth_display_text("mojibake DEPTHgarbage15"))

    def test_customer_excel_remark_hides_internal_diagnostics(self):
        row = {
            "Needs Review": "YES",
            "Review Reason": (
                "Low OCR confidence; YOLO hole_callout_text crop; "
                "General tolerance applied; BELOW limit; Customer special check"
            ),
        }
        self.assertEqual(remark_for_row(row), "BELOW limit; Customer special check")

    def test_customer_excel_remark_hides_merged_duplicate_diagnostic(self):
        row = {
            "Review Reason": "Merged duplicate detection from detector_recognition_normal_dimension_metric_text"
        }
        self.assertEqual(remark_for_row(row), "")

    def test_real_japanese_depth_text_is_normalized(self):
        rows = normalize_compound_callout_rows(
            [
                {
                    "Measurement Type": "hole_callout",
                    "Extracted Value": "\u4e0b\u30ad\u30eaDEPTH\u30b515",
                    "OCR Text": "\u4e0b\u30ad\u30eaDEPTH\u30b515",
                    "Review Reason": "",
                }
            ]
        )
        self.assertEqual(rows[0]["Extracted Value"], "DEPTH 15")

    def test_gdt_crop_distinguishes_perpendicularity_and_parallelism(self):
        perpendicularity = np.full((70, 70, 3), 255, dtype=np.uint8)
        cv2.line(perpendicularity, (35, 15), (35, 52), (0, 0, 0), 3)
        cv2.line(perpendicularity, (15, 52), (55, 52), (0, 0, 0), 3)
        self.assertEqual(classify_gdt_symbol_crop(perpendicularity), "⊥")

        parallelism = np.full((70, 70, 3), 255, dtype=np.uint8)
        cv2.line(parallelism, (15, 55), (38, 15), (0, 0, 0), 3)
        cv2.line(parallelism, (32, 55), (55, 15), (0, 0, 0), 3)
        self.assertEqual(classify_gdt_symbol_crop(parallelism), "//")

    def test_generic_gdt_frame_uses_the_loaded_drawing_image(self):
        image = np.full((300, 500, 3), 255, dtype=np.uint8)
        values = [
            {
                "Measurement Type": "plain_dimension",
                "Extracted Value": "0.05 Z",
                "OCR Text": "0.05 Z",
                "OCR Confidence": 0.95,
                "X": 160,
                "Y": 110,
                "Width": 100,
                "Height": 30,
            }
        ]
        symbols = [
            {
                "Symbol Class": "gdt_frame_symbol",
                "Confidence": 0.95,
                "X": 100,
                "Y": 100,
                "Width": 180,
                "Height": 50,
            }
        ]
        with patch("auto_ballooning.infer_gdt_frame_symbol", return_value="⊥") as infer:
            rows = create_gdt_characteristic_rows(values, symbols, "original.png", source_image=image)
        self.assertEqual(rows[0]["Symbol"], "⊥")
        self.assertIs(infer.call_args.args[0], image)

    def test_gdt_balloon_frame_preserves_the_complete_detector_box(self):
        row = {
            "Measurement Type": "gdt",
            "Symbol": "⊥",
            "Dimension": "0.1 Z",
            "X": 100,
            "Y": 200,
            "Width": 260,
            "Height": 70,
        }
        x1, y1, x2, y2 = tight_balloon_frame_box(row, 1000, 1000)
        self.assertLessEqual(x1, 100)
        self.assertGreaterEqual(x2, 360)
        self.assertLessEqual(y1, 200)
        self.assertGreaterEqual(y2, 270)

    def test_balloon_circle_collision_checks_characteristic_frames(self):
        self.assertTrue(circle_overlaps_frame(90, 150, 20, (100, 100, 200, 200)))
        self.assertFalse(circle_overlaps_frame(60, 150, 20, (100, 100, 200, 200)))

    def test_balloon_layout_diagnostics_reports_overlapping_frames(self):
        rows = [
            {"Balloon No": "1", "Display Balloon No": "1", "X": 100, "Y": 100, "Width": 80, "Height": 30},
            {"Balloon No": "2", "Display Balloon No": "2", "X": 130, "Y": 105, "Width": 80, "Height": 30},
        ]
        diagnostics = build_balloon_layout_diagnostics(rows, (500, 500, 3))
        self.assertEqual(diagnostics["record_count"], 2)
        self.assertTrue(any(issue["type"] == "frame_frame_overlap" for issue in diagnostics["issues"]))

    def test_small_frame_overlap_is_separated_but_severe_overlap_is_left_for_qc(self):
        rows = [{"Balloon Rotation": 0}, {"Balloon Rotation": 0}]
        mild = separate_mild_frame_overlaps(rows, [(100, 100, 200, 140), (180, 100, 280, 140)])
        self.assertLess(mild[0][2], mild[1][0])
        severe = separate_mild_frame_overlaps(rows, [(100, 100, 200, 140), (140, 100, 240, 140)])
        self.assertEqual(severe, [(100, 100, 200, 140), (140, 100, 240, 140)])

    def test_japanese_drill_words_do_not_remain_in_thread_value(self):
        rows = normalize_compound_callout_rows(
            [
                {
                    "Measurement Type": "metric_thread",
                    "Extracted Value": "4Mx6 キリ DEPTH15",
                    "OCR Text": "4Mx6 キリ DEPTH15",
                    "Review Reason": "",
                }
            ]
        )
        values = [str(row.get("Extracted Value", "")) for row in rows]
        self.assertIn("4X M6", values)
        self.assertTrue(all("キリ" not in value for value in values))


if __name__ == "__main__":
    unittest.main()
