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
    assign_stable_balloon_numbers,
    balloon_circle_radius,
    build_balloon_layout_diagnostics,
    build_characteristics,
    candidate_quality_score,
    classify_gdt_symbol_crop,
    classify_gdt_datum_glyph,
    clean_detector_engineering_text,
    classify_yolo_text_box,
    compound_component_measurement,
    circle_overlaps_frame,
    create_gdt_characteristic_rows,
    corrected_measurement_specification,
    detector_crop_looks_like_rotated_eight,
    detector_ocr_candidate_is_better,
    extract_yolo_text_box_rows,
    group_split_tolerance_measurements,
    is_duplicate_hole_callout_noise,
    is_ambiguous_drill_rescue_fragment,
    is_plain_duplicate_of_specialized_measurement,
    is_red_lower_note_fragment,
    is_report_excluded,
    is_numeric_fragment,
    is_nested_specialized_fragment,
    is_shadowed_by_detector_measurement,
    load_or_run_content_measurements,
    normalize_compound_callout_rows,
    normalize_depth_display_text,
    normalize_duplicate_text,
    normalize_fa_export_row,
    parse_compound_hole_callout_rows,
    parse_counterbore_rows,
    parse_drill_depth_rows,
    parse_fit_dimension_fields,
    parse_tolerance,
    prefer_adjacent_english_depth,
    recover_left_quantity_prefix,
    recover_split_below_radius,
    remove_duplicate_characteristics,
    remark_for_row,
    repair_gdt_value_with_datum,
    repair_split_iso_fit_measurements,
    separate_mild_frame_overlaps,
    tight_balloon_frame_box,
    vertical_rescue_has_leading_diameter_glyph,
)
import measurement_extraction  # noqa: E402
from measurement_extraction import (  # noqa: E402
    classify_measurement,
    filter_junk_and_notes,
    should_suppress_nearby_small_rescue,
)
from vision_tools import detect_symbols_with_yolo  # noqa: E402


class MeasurementRegressionTests(unittest.TestCase):
    def test_split_below_radius_does_not_invent_extra_zero(self):
        self.assertEqual(recover_split_below_radius("BELOW 2 X R 0. 2 以下 A"), "2XR0.2")
        self.assertEqual(recover_split_below_radius("R0. 5 BELOW"), "R0.5")
        self.assertEqual(recover_split_below_radius("R0.02 BELOW"), "")

    def test_high_confidence_small_text_is_not_hidden_by_nearby_fragment(self):
        existing = [{"text": "11", "confidence": 0.8, "box": (100, 100, 130, 130)}]
        recovered = {"text": "31", "confidence": 0.9435, "box": (104, 104, 134, 134)}
        uncertain = {"text": "31", "confidence": 0.75, "box": (104, 104, 134, 134)}
        self.assertFalse(should_suppress_nearby_small_rescue(recovered, existing))
        self.assertTrue(should_suppress_nearby_small_rescue(uncertain, existing))

    def test_small_text_rescue_runs_after_broad_ocr_cleanup(self):
        image = np.full((200, 300, 3), 255, dtype=np.uint8)
        cleaned = [
            {
                "text": "11",
                "confidence": 0.8,
                "box": (100, 100, 130, 130),
                "orientation": "normal",
            }
        ]
        recovered = {
            "text": "31",
            "confidence": 0.9435,
            "box": (140, 100, 170, 130),
            "orientation": "small_text_rescue",
        }

        with (
            patch.object(measurement_extraction, "predict_full_page_ocr_items", return_value=[]),
            patch.object(measurement_extraction, "rescue_angled_dimensions", return_value=[]),
            patch.object(measurement_extraction, "rescue_vertical_decimal_dimensions", return_value=[]),
            patch.object(measurement_extraction, "clean_ocr_results", return_value=cleaned),
            patch.object(
                measurement_extraction,
                "rescue_small_text_dimensions",
                return_value=[recovered],
            ) as small_rescue,
            patch.object(measurement_extraction, "rescue_single_digit_dimensions", return_value=[]),
            patch.object(measurement_extraction, "is_inside_table", return_value=False),
        ):
            result = measurement_extraction.extract_measurement_ocr_items(object(), image)

        self.assertEqual(small_rescue.call_args.args[2], cleaned)
        self.assertIn(recovered, result)

    def test_detector_ocr_removes_only_edge_cad_marks(self):
        self.assertEqual(clean_detector_engineering_text("6←"), "6")
        self.assertEqual(clean_detector_engineering_text("|5|"), "5")
        self.assertEqual(clean_detector_engineering_text("3→"), "3")
        self.assertEqual(clean_detector_engineering_text("CBORE12 DP10"), "CBORE12 DP10")
        self.assertEqual(clean_detector_engineering_text("3-"), "3")
        self.assertEqual(clean_detector_engineering_text("-24.0-"), "24.0")
        self.assertEqual(clean_detector_engineering_text("3 +0.1 -0.2"), "3 +0.1 -0.2")

    def test_rotated_eight_requires_exactly_two_enclosed_loops(self):
        image = np.full((80, 80, 3), 255, dtype=np.uint8)
        cv2.circle(image, (30, 40), 10, (0, 0, 0), 3)
        cv2.circle(image, (50, 40), 10, (0, 0, 0), 3)
        symbol = {"X": 15, "Y": 20, "Width": 50, "Height": 40}
        self.assertTrue(detector_crop_looks_like_rotated_eight(image, symbol))

    def test_incomplete_general_tolerance_map_uses_range_fallback(self):
        self.assertEqual(parse_tolerance("5.6", general_tolerances={2: 0.05})[1:3], ("0.1", "0.1"))
        self.assertEqual(parse_tolerance("12", general_tolerances={2: 0.05})[1:3], ("0.2", "0.2"))

    def test_stacked_tolerance_missing_decimal_is_repaired(self):
        self.assertEqual(
            parse_tolerance("1.35+0140", apply_general=False),
            ("1.35", "0", "0.14", "1.35", "1.49"),
        )

    def test_multiplier_is_restored_from_detector_ocr_text(self):
        row = {
            "Measurement Type": "radius",
            "Extracted Value": "R5",
            "OCR Text": "2XR5",
            "Width": 90,
            "Height": 120,
        }
        self.assertEqual(corrected_measurement_specification(row), "2XR5")

    def test_thread_depth_arrow_is_normalized(self):
        self.assertEqual(normalize_depth_display_text("M5x0.8-v15"), "M5x0.8 DEPTH 15")

    def test_duplicate_normalization_restores_leading_decimal_zero(self):
        self.assertEqual(normalize_duplicate_text("C.5"), normalize_duplicate_text("C0.5"))

    def test_thread_pitch_frame_does_not_cover_adjacent_depth_text(self):
        row = {
            "Measurement Type": "metric_thread",
            "Specification": "M4X0.7",
            "Symbol": "M",
            "Dimension": "4X0.7",
            "X": 100,
            "Y": 100,
            "Width": 420,
            "Height": 58,
        }
        x1, _, x2, _ = tight_balloon_frame_box(row, 1000, 1000)
        self.assertLess(x2 - x1, 300)

    def test_scale_value_is_not_an_inspection_dimension(self):
        row = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "1.2:1",
            "OCR Text": "1.2:1",
        }
        self.assertTrue(is_report_excluded(row, image_shape=(3000, 4000, 3)))

    def test_standalone_depth_is_duplicate_of_complete_compound_callout(self):
        depth = {
            "Measurement Type": "hole_callout",
            "Extracted Value": "DEPTH 7",
            "OCR Text": "DEPTH 7",
            "X": 2740,
            "Y": 1940,
            "Width": 55,
            "Height": 30,
        }
        complete = {
            "Measurement Type": "hole_callout",
            "Extracted Value": "CBORE11 DP7",
            "OCR Text": "CBORE11 DP7",
            "X": 2620,
            "Y": 1940,
            "Width": 240,
            "Height": 30,
        }
        self.assertTrue(is_duplicate_hole_callout_noise(depth, [depth, complete]))

    def test_low_confidence_unprefixed_drill_rescue_is_rejected(self):
        row = {
            "Measurement Type": "hole_callout",
            "Extracted Value": "3",
            "OCR Text": "3DRILL THRU",
            "OCR Orientation": "small_text_rescue",
            "OCR Confidence": 0.8179,
        }
        self.assertTrue(is_ambiguous_drill_rescue_fragment(row))
        row["OCR Confidence"] = 0.95
        self.assertFalse(is_ambiguous_drill_rescue_fragment(row))

    def test_normalized_wide_single_digit_drill_rescue_is_rejected(self):
        row = {
            "Measurement Type": "hole_callout",
            "Extracted Value": "3",
            "OCR Text": "3",
            "OCR Orientation": "small_text_rescue",
            "OCR Confidence": 0.8179,
            "Width": 117,
            "Height": 37,
        }
        self.assertTrue(is_ambiguous_drill_rescue_fragment(row))
        row["Width"] = 25
        self.assertFalse(is_ambiguous_drill_rescue_fragment(row))

    def test_red_lower_note_fragment_is_rejected_but_black_dimension_is_kept(self):
        image = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        row = {
            "Measurement Type": "chamfer",
            "Extracted Value": "C0.4",
            "X": 100, "Y": 800, "Width": 120, "Height": 60,
        }
        cv2.putText(image, "C0.4", (105, 840), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
        self.assertTrue(is_red_lower_note_fragment(row, image))
        black = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        cv2.putText(black, "C0.4", (105, 840), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 3)
        self.assertFalse(is_red_lower_note_fragment(row, black))

    def test_plain_leading_zero_duplicate_is_replaced_by_diameter(self):
        plain = {
            "Measurement Type": "plain_dimension", "Extracted Value": "025",
            "X": 103, "Y": 104, "Width": 95, "Height": 165,
        }
        diameter = {
            "Measurement Type": "diameter", "Extracted Value": "Ø25",
            "X": 100, "Y": 100, "Width": 102, "Height": 184,
        }
        self.assertTrue(is_plain_duplicate_of_specialized_measurement(plain, [plain, diameter]))

    def test_damaged_alphanumeric_plain_duplicate_is_replaced_by_thickness(self):
        plain = {
            "Measurement Type": "plain_dimension", "Extracted Value": "0E1",
            "X": 102, "Y": 101, "Width": 51, "Height": 88,
        }
        thickness = {
            "Measurement Type": "thickness", "Extracted Value": "t30",
            "X": 100, "Y": 100, "Width": 51, "Height": 89,
        }
        self.assertTrue(is_plain_duplicate_of_specialized_measurement(plain, [plain, thickness]))

    def test_multiplied_through_hole_does_not_receive_general_tolerance(self):
        measurement = {
            "Source File": "original.png",
            "Measurement Type": "hole_callout",
            "Extracted Value": "6X 5.6 THRU",
            "OCR Text": "6X 5.6 THRU",
            "OCR Confidence": 0.9,
            "X": 100,
            "Y": 100,
            "Width": 180,
            "Height": 38,
        }
        rows, _ = build_characteristics([measurement], "original.png")
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["Tolerance -"] == "" for row in rows))
        self.assertTrue(all(row["Tolerance +"] == "" for row in rows))

    def test_single_through_hole_still_receives_general_tolerance(self):
        measurement = {
            "Source File": "original.png",
            "Measurement Type": "hole_callout",
            "Extracted Value": "5.6 THRU",
            "OCR Text": "5.6 THRU",
            "OCR Confidence": 0.9,
            "X": 100,
            "Y": 100,
            "Width": 180,
            "Height": 38,
        }
        rows, _ = build_characteristics([measurement], "original.png")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tolerance -"], "0.1")
        self.assertEqual(rows[0]["Tolerance +"], "0.1")

    def test_gdt_datum_cell_repairs_z_read_as_trailing_two(self):
        self.assertEqual(repair_gdt_value_with_datum("0.052", "Z"), "0.05 Z")
        self.assertEqual(repair_gdt_value_with_datum("0.012", "Z"), "0.01 Z")
        self.assertEqual(repair_gdt_value_with_datum("0.01", "Y"), "0.01 Y")
        self.assertEqual(repair_gdt_value_with_datum("0.025", ""), "0.025")

    def test_gdt_datum_glyph_fallback_distinguishes_xyz(self):
        z = np.full((50, 40), 255, dtype=np.uint8)
        cv2.line(z, (8, 8), (32, 8), 0, 2)
        cv2.line(z, (32, 8), (8, 42), 0, 2)
        cv2.line(z, (8, 42), (32, 42), 0, 2)
        self.assertEqual(classify_gdt_datum_glyph(z), "Z")

        x = np.full((50, 40), 255, dtype=np.uint8)
        cv2.line(x, (8, 8), (32, 42), 0, 2)
        cv2.line(x, (32, 8), (8, 42), 0, 2)
        self.assertEqual(classify_gdt_datum_glyph(x), "X")

        y = np.full((50, 40), 255, dtype=np.uint8)
        cv2.line(y, (8, 8), (20, 24), 0, 2)
        cv2.line(y, (32, 8), (20, 24), 0, 2)
        cv2.line(y, (20, 24), (20, 42), 0, 2)
        self.assertEqual(classify_gdt_datum_glyph(y), "Y")

    def test_low_confidence_gdt_detector_is_used_when_candidate_mode_enables_it(self):
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
                "Confidence": 0.30,
                "X": 100,
                "Y": 100,
                "Width": 180,
                "Height": 50,
            }
        ]
        with (
            patch("auto_ballooning.YOLO_GDT_OCR_MIN_DETECTOR_CONFIDENCE", 0.20),
            patch("auto_ballooning.infer_gdt_frame_symbol", return_value="//"),
        ):
            rows = create_gdt_characteristic_rows(values, symbols, "original.png", source_image=image)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Specification"], "// 0.05 Z")

    def test_validated_detector_single_digit_is_not_rejected_as_fragment(self):
        detector = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "6",
            "OCR Confidence": 0.90,
            "X": 100,
            "Y": 100,
            "Width": 30,
            "Height": 35,
            "OCR Orientation": "detector_recognition_normal_dimension_text",
            "Detector OCR Validated": "YES",
        }
        nearby = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "16",
            "X": 130,
            "Y": 100,
            "Width": 45,
            "Height": 35,
        }
        self.assertFalse(is_numeric_fragment(detector, [detector, nearby]))

    def test_tight_detector_number_shadows_wrong_page_ocr_reading(self):
        page = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "55",
            "OCR Confidence": 0.93,
            "X": 100,
            "Y": 100,
            "Width": 50,
            "Height": 60,
            "OCR Orientation": "normal",
        }
        detector = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "50",
            "OCR Confidence": 0.90,
            "X": 106,
            "Y": 106,
            "Width": 38,
            "Height": 48,
            "OCR Orientation": "detector_recognition_cw_dimension_text",
        }
        self.assertTrue(is_shadowed_by_detector_measurement(page, [page, detector]))

    def test_compound_counterbore_and_depth_receive_separate_boxes(self):
        measurement = {"X": 100, "Y": 50, "Width": 220, "Height": 34, "Review Reason": ""}
        counterbore = compound_component_measurement(
            measurement, {"group": "counterbore"}, "CBORE12 DP10"
        )
        depth = compound_component_measurement(measurement, {"group": "depth"}, "CBORE12 DP10")
        self.assertEqual((counterbore["X"], counterbore["Width"]), (100, 140))
        self.assertEqual((depth["X"], depth["Width"]), (240, 80))

    def test_high_recall_detector_box_is_kept_after_valid_crop_ocr(self):
        image = np.full((120, 240, 3), 255, dtype=np.uint8)
        symbol = {
            "Symbol Class": "dimension_text",
            "Confidence": 0.20,
            "X": 60,
            "Y": 35,
            "Width": 45,
            "Height": 35,
        }
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "drawing.png"
            cv2.imwrite(str(image_path), image)
            with (
                patch("auto_ballooning.YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE", 0.20),
                patch("auto_ballooning.create_paddle_text_recognizer", return_value=object()),
                patch("auto_ballooning.recognition_only_result", return_value=("6", 0.99)),
            ):
                rows = extract_yolo_text_box_rows(image_path, [symbol], [])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Extracted Value"], "6")
        self.assertEqual(rows[0]["OCR Confidence"], 0.9)
        self.assertIn("High-recall detector confidence 0.20", rows[0]["Review Reason"])

    def test_high_recall_detector_box_without_valid_engineering_ocr_is_rejected(self):
        image = np.full((120, 240, 3), 255, dtype=np.uint8)
        symbol = {
            "Symbol Class": "dimension_text",
            "Confidence": 0.20,
            "X": 60,
            "Y": 35,
            "Width": 45,
            "Height": 35,
        }
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "drawing.png"
            cv2.imwrite(str(image_path), image)
            with (
                patch("auto_ballooning.YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE", 0.20),
                patch("auto_ballooning.create_paddle_text_recognizer", return_value=object()),
                patch("auto_ballooning.recognition_only_result", return_value=("NOTE", 0.99)),
            ):
                rows = extract_yolo_text_box_rows(image_path, [symbol], [])

        self.assertEqual(rows, [])

    def test_ultralow_rescue_proposal_requires_high_confidence_crop_ocr(self):
        image = np.full((120, 240, 3), 255, dtype=np.uint8)
        symbol = {
            "Symbol Class": "dimension_text",
            "Confidence": 0.02,
            "Detector": "local_yolo_ensemble_rescue",
            "X": 60, "Y": 35, "Width": 45, "Height": 35,
        }
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "drawing.png"
            cv2.imwrite(str(image_path), image)
            with (
                patch("auto_ballooning.YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE", 0.01),
                patch("auto_ballooning.create_paddle_text_recognizer", return_value=object()),
                patch("auto_ballooning.recognition_only_result", return_value=("4H8+0.018", 0.89)),
            ):
                rows = extract_yolo_text_box_rows(image_path, [symbol], [])
        self.assertEqual(rows, [])

    def test_ultralow_vertical_rescue_uses_tight_high_confidence_fit_crop(self):
        image = np.full((300, 200, 3), 255, dtype=np.uint8)
        symbol = {
            "Symbol Class": "dimension_text",
            "Confidence": 0.02,
            "Detector": "local_yolo_ensemble_rescue",
            "X": 20, "Y": 20, "Width": 50, "Height": 200,
        }

        def recognize(_recognizer, crop):
            if 150 <= crop.shape[1] <= 170 and crop.shape[0] < 50:
                return "4H8+0.018\u6df1", 0.93
            return "4E8+0.018\u6df15", 0.80

        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "drawing.png"
            cv2.imwrite(str(image_path), image)
            with (
                patch("auto_ballooning.YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE", 0.01),
                patch("auto_ballooning.create_paddle_text_recognizer", return_value=object()),
                patch("auto_ballooning.recognition_only_result", side_effect=recognize),
            ):
                rows = extract_yolo_text_box_rows(image_path, [symbol], [])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Extracted Value"], "4H8+0.018 0")
        self.assertEqual(rows[0]["OCR Orientation"], "detector_recognition_rescue_trim_cw_dimension_text")
        self.assertEqual((rows[0]["X"], rows[0]["Y"]), (24, 62))

    def test_slightly_vertical_dimension_tries_rotated_ocr(self):
        image = np.full((160, 240, 3), 255, dtype=np.uint8)
        symbol = {
            "Symbol Class": "dimension_text",
            "Confidence": 0.80,
            "X": 60,
            "Y": 35,
            "Width": 51,
            "Height": 57,
        }

        def recognize(_recognizer, crop):
            # Rotating the mildly vertical crop makes it wider than tall.
            if crop.shape[1] > crop.shape[0]:
                return "16", 0.99
            return "10", 0.60

        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "drawing.png"
            cv2.imwrite(str(image_path), image)
            with (
                patch("auto_ballooning.create_paddle_text_recognizer", return_value=object()),
                patch("auto_ballooning.recognition_only_result", side_effect=recognize),
            ):
                rows = extract_yolo_text_box_rows(image_path, [symbol], [])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Extracted Value"], "16")
        self.assertEqual(rows[0]["OCR Orientation"], "detector_recognition_cw_dimension_text")

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
            rescued_row = dict(
                fresh_row,
                **{
                    "Extracted Value": "21.0",
                    "OCR Text": "21.0",
                    "OCR Orientation": "vertical_decimal_rescue",
                    "X": 20,
                },
            )
            with patch("auto_ballooning.content_measurement_cache_path", return_value=cache_path), patch(
                "auto_ballooning.run_ocr_measurements", return_value=[fresh_row]
            ) as fresh_ocr, patch(
                "auto_ballooning.run_rescue_measurements", return_value=[rescued_row]
            ) as final_rescue:
                rows, source = load_or_run_content_measurements(
                    pdf_path,
                    root,
                    image_path,
                    allow_cache=False,
                )

            fresh_ocr.assert_called_once_with(image_path)
            final_rescue.assert_called_once_with(
                image_path,
                [fresh_row],
                include_single_digit=False,
                mandatory_vertical_only=True,
            )
            self.assertEqual(source, "fresh_ocr")
            self.assertEqual(rows[0]["Extracted Value"], "195.5")
            self.assertEqual(rows[1]["Extracted Value"], "21.0")

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

    def test_spaced_nominal_digits_are_repaired_in_tolerance_callout(self):
        measurement_type, extracted = classify_measurement("3 2+/-0.2")
        self.assertEqual(measurement_type, "plain_dimension")
        self.assertEqual(extracted, "32+/-0.2")

        rows, rejected = build_characteristics(
            [
                {
                    "Measurement Type": "tolerance",
                    "Extracted Value": "'+/-0.2",
                    "OCR Text": "3 2+/-0.2",
                    "OCR Confidence": 0.83,
                    "X": 100,
                    "Y": 100,
                    "Width": 120,
                    "Height": 47,
                    "OCR Orientation": "normal",
                }
            ],
            "drawing.png",
        )
        self.assertEqual(rejected, [])
        self.assertEqual(rows[0]["Dimension"], "32")

    def test_vertical_leading_zero_reading_is_restored_at_boundary_ratio(self):
        row = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "09",
            "OCR Text": "09",
            "OCR Confidence": 0.8052,
            "X": 1013,
            "Y": 1811,
            "Width": 48,
            "Height": 60,
            "OCR Orientation": "normal",
        }
        self.assertEqual(corrected_measurement_specification(row), "90")
        self.assertFalse(is_report_excluded(row, image_shape=(3306, 4678, 3)))

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

    def test_wider_detector_crop_allows_moderate_confidence_when_suffix_matches(self):
        partial = (1.20, 0.83, "normal", "plain_dimension", "6.0 +0 -0.01", "6.0 -0.01")
        complete = (1.10, 0.72, "normal", "plain_dimension", "86.0 +0 -0.01", "86.0 +0 -0.01")
        self.assertTrue(detector_ocr_candidate_is_better(partial, complete))

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

        source = {
            "Source File": "drawing.png",
            "Measurement Type": "plain_dimension",
            "Extracted Value": "4 H8 +0.018 / 0",
            "OCR Text": "4 H8 +0.018 / 0",
            "OCR Confidence": 0.99,
            "X": 100,
            "Y": 100,
            "Width": 80,
            "Height": 180,
            "OCR Orientation": "detector_recognition_rescue_trim_cw_dimension_text",
        }
        rows, rejected = build_characteristics([source], "drawing.png")
        self.assertEqual(rejected, [])
        self.assertEqual(rows[0]["Measurement Type"], "plain_dimension")
        self.assertEqual(rows[0]["Symbol"], "")

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

    def test_split_rotated_iso_fit_is_rejoined_before_tolerance_grouping(self):
        rows = repair_split_iso_fit_measurements(
            [
                {
                    "Measurement Type": "diameter",
                    "Extracted Value": "Ø34.5",
                    "OCR Text": "Ø34.5g",
                    "X": 4917,
                    "Y": 2830,
                    "Width": 90,
                    "Height": 327,
                    "OCR Orientation": "rotated_cw",
                },
                {
                    "Measurement Type": "plain_dimension",
                    "Extracted Value": "6-0.025",
                    "OCR Text": "6-0.025",
                    "X": 4925,
                    "Y": 2602,
                    "Width": 106,
                    "Height": 274,
                    "OCR Orientation": "rotated_cw",
                },
                {
                    "Measurement Type": "tolerance",
                    "Extracted Value": "-0.009",
                    "OCR Text": "-0.009",
                    "X": 4902,
                    "Y": 2607,
                    "Width": 64,
                    "Height": 173,
                    "OCR Orientation": "rotated_cw",
                },
            ]
        )
        self.assertEqual(len(rows), 2)
        grouped = group_split_tolerance_measurements(rows)
        diameter = next(row for row in grouped if row["Measurement Type"] == "diameter")
        self.assertEqual(diameter["Extracted Value"], "Ø34.5g6-0.025")
        self.assertEqual(diameter["Grouped Tolerance -"], "0.025")
        self.assertEqual(diameter["Grouped Tolerance +"], "-0.009")

    def test_complete_nonzero_tolerance_wins_over_partial_zero_duplicate(self):
        source = {
            "Source File": "drawing.png",
            "Measurement Type": "plain_dimension",
            "OCR Confidence": 0.8748,
            "X": 100,
            "Y": 100,
            "Width": 160,
            "Height": 50,
            "OCR Orientation": "detector_recognition_normal_dimension_text",
        }
        complete = dict(source, **{"Extracted Value": "2.7+0.25 0", "OCR Text": "2.7+0.25 0"})
        partial = dict(source, **{"Extracted Value": "2.7+0 0", "OCR Text": "2.7+0", "OCR Confidence": 0.9})
        rows, rejected = build_characteristics([complete, partial], "drawing.png")
        self.assertEqual(rejected, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tolerance -"], "0")
        self.assertEqual(rows[0]["Tolerance +"], "0.25")

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

    def test_compound_subrows_keep_parent_balloon_number(self):
        rows = [
            {
                "X": 100,
                "Y": 100,
                "Width": 200,
                "Height": 50,
                "Specification": "CBORE 12 DEPTH 10",
                "Multiplier Count": 1,
                "Subrow Count": 2,
                "Subrow Index": index,
            }
            for index in (1, 2)
        ]
        assign_stable_balloon_numbers(rows)
        self.assertEqual([row["Balloon No"] for row in rows], ["1", "1"])
        self.assertEqual([row["Display Balloon No"] for row in rows], ["1", "1"])

    def test_separated_compound_subrows_keep_parent_balloon_number(self):
        rows = [
            {
                "X": 100,
                "Y": 100,
                "Width": 100,
                "Height": 30,
                "Specification": "CBORE 11 DEPTH 7",
                "Multiplier Count": 1,
                "Subrow Count": 2,
                "Subrow Index": 1,
            },
            {
                "X": 120,
                "Y": 60,
                "Width": 180,
                "Height": 30,
                "Specification": "6X 5.5 THRU",
                "Multiplier Count": 6,
                "Multiplier Index": 1,
                "Subrow Count": 1,
                "Subrow Index": "",
            },
            {
                "X": 220,
                "Y": 100,
                "Width": 50,
                "Height": 30,
                "Specification": "CBORE 11 DEPTH 7",
                "Multiplier Count": 1,
                "Subrow Count": 2,
                "Subrow Index": 2,
            },
        ]
        assign_stable_balloon_numbers(rows)
        self.assertEqual([row["Balloon No"] for row in rows], ["1", "2.1", "1"])
        self.assertEqual([row["Display Balloon No"] for row in rows], ["1", "2", "1"])

        layout = build_balloon_layout_diagnostics(rows, (500, 500, 3))
        self.assertEqual(layout["record_count"], 2)
        self.assertEqual([record["balloon_no"] for record in layout["records"]], ["1", "2"])

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

    def test_same_crop_radius_and_diameter_are_one_characteristic(self):
        rows = remove_duplicate_characteristics(
            [
                {
                    "Measurement Type": "radius",
                    "Specification": "R9.5",
                    "Symbol": "R",
                    "Dimension": "9.5",
                    "AI Confidence": 0.90,
                    "X": 2003,
                    "Y": 1535,
                    "Width": 191,
                    "Height": 134,
                },
                {
                    "Measurement Type": "diameter",
                    "Specification": "Ø9.5",
                    "Symbol": "Ø",
                    "Dimension": "9.5",
                    "AI Confidence": 0.49,
                    "X": 2005,
                    "Y": 1539,
                    "Width": 188,
                    "Height": 129,
                },
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Measurement Type"], "radius")
        self.assertEqual(rows[0]["Specification"], "R9.5")

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

    def test_gdt_characteristic_uses_complete_tight_frame_detector_box(self):
        image = np.full((600, 800, 3), 255, dtype=np.uint8)
        values = [
            {
                "Measurement Type": "plain_dimension",
                "Extracted Value": "0.01 Z",
                "OCR Confidence": 0.99,
                "X": 60,
                "Y": 85,
                "Width": 330,
                "Height": 90,
            }
        ]
        symbols = [
            {
                "Symbol Class": "gdt_frame_symbol",
                "Confidence": 0.95,
                "X": 100,
                "Y": 100,
                "Width": 280,
                "Height": 70,
            }
        ]
        with patch("auto_ballooning.infer_gdt_frame_symbol", return_value="//"):
            rows = create_gdt_characteristic_rows(values, symbols, "original.png", source_image=image)
        self.assertEqual(len(rows), 1)
        self.assertLess(rows[0]["X"], 100)
        self.assertGreater(rows[0]["X"] + rows[0]["Width"], 380)
        self.assertGreater(rows[0]["X"], 80)
        self.assertLess(rows[0]["Width"], 310)

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

    def test_stacked_wide_thread_and_short_depth_frames_separate_vertically(self):
        rows = [
            {"X": 100, "Y": 100, "Width": 340, "Height": 36, "Balloon Rotation": 0},
            {"X": 105, "Y": 135, "Width": 165, "Height": 29, "Balloon Rotation": 0},
        ]
        frames = [(90, 93, 450, 143), (98, 129, 277, 171)]
        adjusted = separate_mild_frame_overlaps(rows, frames)
        self.assertLess(adjusted[0][3], adjusted[1][1])

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


    def test_detector_depth_fragment_keeps_its_own_tight_geometry(self):
        rows = normalize_compound_callout_rows(
            [
                {
                    "Measurement Type": "metric_thread",
                    "Extracted Value": "M5x0.8 - v15",
                    "OCR Text": "M5x0.8 - v15",
                    "X": 700,
                    "Y": 1600,
                    "Width": 240,
                    "Height": 70,
                },
                {
                    "Measurement Type": "thickness",
                    "Extracted Value": "T15",
                    "OCR Text": "T15",
                    "OCR Orientation": "detector_recognition_normal_dimension_text",
                    "X": 988,
                    "Y": 1590,
                    "Width": 152,
                    "Height": 86,
                },
            ]
        )
        depths = [row for row in rows if row["Measurement Type"] == "hole_callout"]
        self.assertEqual(len(depths), 1)
        self.assertEqual(depths[0]["Extracted Value"], "DEPTH 15")
        self.assertEqual((depths[0]["X"], depths[0]["Width"]), (988, 152))

    def test_compound_thread_depth_uses_suffix_geometry_without_separate_box(self):
        rows = normalize_compound_callout_rows(
            [
                {
                    "Measurement Type": "metric_thread",
                    "Extracted Value": "M4x0.7 - v12",
                    "OCR Text": "M4x0.7 - v12",
                    "X": 2500,
                    "Y": 1600,
                    "Width": 420,
                    "Height": 60,
                }
            ]
        )
        depth = next(row for row in rows if row["Measurement Type"] == "hole_callout")
        self.assertGreater(depth["X"], 2500)
        self.assertLess(depth["Width"], 420)

    def test_generic_dimension_crop_canonicalizes_chamfer_letter_o(self):
        self.assertEqual(
            classify_yolo_text_box("dimension_text", "CO.5"),
            ("chamfer", "C0.5"),
        )

    def test_incomplete_reference_parenthesis_stays_reference_dimension(self):
        self.assertEqual(
            classify_yolo_text_box("dimension_text", "(5.3"),
            ("reference_dimension", "(5.3)"),
        )

    def test_nonzero_explicit_tolerance_wins_over_zero_only_candidate(self):
        correct = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "2.7 +0.25 0",
            "OCR Confidence": 0.87,
            "OCR Orientation": "detector_recognition_normal_dimension_text",
        }
        incomplete = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "2.7 +0 0",
            "OCR Confidence": 0.90,
            "OCR Orientation": "detector_recognition_normal_dimension_text",
        }
        self.assertGreater(candidate_quality_score(correct), candidate_quality_score(incomplete))

    def test_low_confidence_generic_detector_is_excluded_from_title_table(self):
        row = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "11",
            "OCR Orientation": "detector_recognition_normal_dimension_text",
            "Detector Confidence": 0.02,
            "X": 3300,
            "Y": 2500,
            "Width": 80,
            "Height": 40,
        }
        self.assertTrue(is_report_excluded(row, image_shape=(3000, 4000, 3)))

    def test_primary_detector_can_survive_template_exclusion_zone(self):
        row = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "11",
            "OCR Orientation": "detector_recognition_normal_dimension_text",
            "Detector Confidence": 0.61,
            "X": 3300,
            "Y": 2500,
            "Width": 80,
            "Height": 40,
        }
        self.assertFalse(is_report_excluded(row, image_shape=(3000, 4000, 3)))

    def test_saved_chamfer_row_canonicalizes_letter_o(self):
        self.assertEqual(
            corrected_measurement_specification(
                {"Measurement Type": "chamfer", "Extracted Value": "CO.5"}
            ),
            "C0.5",
        )

    def test_gdt_triangle_index_is_not_a_plain_dimension(self):
        self.assertTrue(
            is_report_excluded(
                {
                    "Measurement Type": "plain_dimension",
                    "Extracted Value": "1",
                    "OCR Orientation": "local_gdt_frame_symbol",
                }
            )
        )

    def test_detector_anchored_bottom_gdt_value_is_not_page_excluded(self):
        self.assertFalse(
            is_report_excluded(
                {
                    "Measurement Type": "plain_dimension",
                    "Extracted Value": "0.05 X",
                    "OCR Orientation": "local_gdt_group",
                    "X": 1337,
                    "Y": 2905,
                    "Width": 233,
                    "Height": 63,
                },
                image_shape=(3306, 4678, 3),
            )
        )

    def test_vertical_decimal_rescue_confirms_slashed_diameter_glyph(self):
        image = np.full((300, 100, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (50, 235), (25, 18), 0, 0, 360, (0, 0, 0), 5)
        cv2.line(image, (25, 255), (75, 215), (0, 0, 0), 5)
        measurement = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "21.0",
            "OCR Orientation": "vertical_decimal_rescue",
            "X": 10,
            "Y": 20,
            "Width": 80,
            "Height": 260,
        }
        self.assertTrue(vertical_rescue_has_leading_diameter_glyph(image, measurement))

    def test_high_confidence_vertical_decimal_is_not_mistaken_for_revision_date(self):
        item = {
            "text": "21.0",
            "confidence": 0.925,
            "box": (1941, 2324, 2021, 2542),
            "orientation": "vertical_decimal_rescue",
        }
        self.assertEqual(filter_junk_and_notes([item]), [item])

        ordinary_revision = dict(item, orientation="normal")
        self.assertEqual(filter_junk_and_notes([ordinary_revision]), [])

        # The generic text guard remains conservative; the measurement runner
        # is responsible for bypassing it only for validated vertical rescue
        # rows.
        self.assertTrue(measurement_extraction.should_skip_text("21.0"))

    def test_lower_middle_vertical_fallback_survives_normal_crop_limit(self):
        image = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        with patch.object(
            measurement_extraction,
            "VERTICAL_DECIMAL_RESCUE_MAX_CROPS",
            0,
        ):
            crops = measurement_extraction.find_vertical_decimal_text_crops(image)

        self.assertTrue(
            any(
                crop["x1"] == 380
                and crop["y1"] == 660
                and crop["x2"] == 480
                and crop["y2"] == 830
                for crop in crops
            )
        )
        self.assertEqual(
            (crops[0]["x1"], crops[0]["y1"], crops[0]["x2"], crops[0]["y2"]),
            (380, 660, 480, 830),
        )

    def test_detector_numeric_drill_removes_japanese_operation_suffix(self):
        self.assertEqual(clean_detector_engineering_text("6.6キリ"), "6.6 DRILL")
        self.assertEqual(clean_detector_engineering_text("4X6.6キリ"), "4X6.6")
        self.assertEqual(
            classify_yolo_text_box("dimension_text", "6.6キリ"),
            ("hole_callout", "6.6 DRILL"),
        )

    def test_real_japanese_drill_size_is_normalized_without_japanese_text(self):
        rows = normalize_compound_callout_rows(
            [
                {
                    "Measurement Type": "hole_callout",
                    "Extracted Value": "4X6.6キリ",
                    "OCR Text": "4X6.6キリ",
                    "X": 10,
                    "Y": 10,
                    "Width": 100,
                    "Height": 30,
                }
            ]
        )
        self.assertEqual(rows[0]["Extracted Value"], "4X6.6")
        self.assertNotIn("キリ", rows[0]["Extracted Value"])


    def test_left_quantity_prefix_is_recovered_and_expands_box(self):
        image = np.full((200, 400, 3), 255, dtype=np.uint8)
        with patch("auto_ballooning.recognition_only_result", return_value=("4X1", 0.93)):
            text, x1, reason = recover_left_quantity_prefix(
                object(), image, 180, 60, 120, 70, "hole_callout", "6.6 DRILL"
            )
        self.assertEqual(text, "4X 6.6 DRILL")
        self.assertLess(x1, 180)
        self.assertEqual(reason, "Recovered left quantity prefix")

    def test_low_confidence_quantity_prefix_is_not_invented(self):
        image = np.full((200, 400, 3), 255, dtype=np.uint8)
        with patch("auto_ballooning.recognition_only_result", return_value=("4X", 0.65)):
            text, x1, reason = recover_left_quantity_prefix(
                object(), image, 180, 60, 120, 70, "hole_callout", "6.6 DRILL"
            )
        self.assertEqual((text, x1, reason), ("6.6 DRILL", 180, ""))

    def test_adjacent_english_depth_replaces_translated_crop_only_with_same_value(self):
        image = np.full((200, 600, 3), 255, dtype=np.uint8)
        with patch("auto_ballooning.recognition_only_result", return_value=("DEPTH 6", 0.91)):
            text, x2, reason = prefer_adjacent_english_depth(
                object(), image, 100, 60, 140, 55, "hole_callout", "深さ 6"
            )
        self.assertEqual(text, "DEPTH 6")
        self.assertGreater(x2, 240)
        self.assertEqual(reason, "Preferred adjacent English depth callout")

    def test_detector_single_digit_fragment_of_reference_is_rejected(self):
        fragment = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "3",
            "OCR Text": "3",
            "Detector OCR Validated": "YES",
            "OCR Orientation": "detector_recognition_normal_dimension_text",
            "OCR Confidence": 0.92,
            "X": 100,
            "Y": 100,
            "Width": 45,
            "Height": 70,
        }
        reference = {
            "Measurement Type": "reference_dimension",
            "Extracted Value": "(5.3)",
            "OCR Text": "(5.3)",
            "X": 95,
            "Y": 150,
            "Width": 100,
            "Height": 70,
        }
        self.assertTrue(is_numeric_fragment(fragment, [fragment, reference]))

    def test_partial_reference_detector_box_is_rejected_beside_complete_reference(self):
        partial = {
            "Measurement Type": "reference_dimension",
            "Extracted Value": "(5)",
            "X": 100,
            "Y": 170,
            "Width": 60,
            "Height": 65,
            "OCR Confidence": 0.91,
        }
        complete = {
            "Measurement Type": "reference_dimension",
            "Extracted Value": "(5.3)",
            "OCR Orientation": "detector_recognition_cw_dimension_text",
            "X": 95,
            "Y": 110,
            "Width": 95,
            "Height": 130,
            "OCR Confidence": 0.90,
        }
        from auto_ballooning import is_nested_reference_fragment

        self.assertTrue(is_nested_reference_fragment(partial, [partial, complete]))

    def test_short_diameter_fragment_inside_complete_tolerance_is_rejected(self):
        fragment = {
            "Measurement Type": "diameter",
            "Extracted Value": "Ø3",
            "X": 120,
            "Y": 240,
            "Width": 65,
            "Height": 100,
        }
        complete = {
            "Measurement Type": "diameter",
            "Extracted Value": "Ø34.5G6-0.025",
            "Grouped Tolerance -": "0.025",
            "Grouped Tolerance +": "-0.009",
            "X": 100,
            "Y": 100,
            "Width": 125,
            "Height": 400,
        }
        self.assertTrue(is_nested_specialized_fragment(fragment, [fragment, complete]))

    def test_horizontal_surface_finish_frame_keeps_complete_text_span(self):
        row = {
            "Measurement Type": "surface_finish",
            "Symbol": "Ra",
            "Dimension": "12.5",
            "X": 100,
            "Y": 100,
            "Width": 120,
            "Height": 55,
        }
        x1, _, x2, _ = tight_balloon_frame_box(row, 1000, 1000)
        self.assertLessEqual(x1, 100)
        self.assertGreaterEqual(x2 - x1, 200)

    def test_unsigned_fragment_inside_tolerance_box_cannot_steal_deviation(self):
        fragment = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "95",
            "OCR Text": "95",
            "X": 100,
            "Y": 100,
            "Width": 70,
            "Height": 45,
        }
        deviation = {
            "Measurement Type": "tolerance",
            "Extracted Value": "-0.009",
            "OCR Text": "-0.009",
            "X": 90,
            "Y": 90,
            "Width": 90,
            "Height": 80,
        }
        nominal = {
            "Measurement Type": "diameter",
            "Extracted Value": "Ø34.5",
            "OCR Text": "Ø34.5",
            "X": 95,
            "Y": 210,
            "Width": 85,
            "Height": 170,
        }
        grouped = group_split_tolerance_measurements([fragment, deviation, nominal])
        self.assertFalse(any(row.get("Extracted Value") == "95" for row in grouped))

    def test_detector_confirmed_nominal_inside_tolerance_crop_is_preserved(self):
        nominal = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "25",
            "OCR Text": "25",
            "OCR Orientation": "detector_recognition_normal_dimension_text",
            "X": 110,
            "Y": 110,
            "Width": 60,
            "Height": 40,
        }
        tolerance = {
            "Measurement Type": "tolerance",
            "Extracted Value": "+0.25",
            "OCR Text": "+0.25",
            "X": 90,
            "Y": 90,
            "Width": 110,
            "Height": 90,
        }
        grouped = group_split_tolerance_measurements([nominal, tolerance])
        self.assertTrue(any(row.get("Extracted Value") == "25" for row in grouped))

    def test_near_square_rotated_500_is_recovered_as_c05_chamfer(self):
        measurement = {
            "Measurement Type": "plain_dimension",
            "Extracted Value": "500",
            "OCR Text": "500",
            "OCR Orientation": "rotated_cw",
            "X": 100,
            "Y": 100,
            "Width": 250,
            "Height": 252,
            "OCR Confidence": 0.82,
        }
        self.assertEqual(corrected_measurement_specification(measurement), "C0.5")
        rows, _ = build_characteristics([measurement], "original.png")
        self.assertEqual(rows[0]["Symbol"], "C")
        self.assertEqual(rows[0]["Dimension"], "0.5")


if __name__ == "__main__":
    unittest.main()
