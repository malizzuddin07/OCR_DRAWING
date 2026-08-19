import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

import vision_tools  # noqa: E402


def detection(symbol_class, box, confidence, detector):
    x, y, width, height = box
    return {
        "Symbol Class": symbol_class,
        "Confidence": confidence,
        "X": x,
        "Y": y,
        "Width": width,
        "Height": height,
        "Box": f"{x},{y},{x + width},{y + height}",
        "Detector": detector,
    }


class VisionToolsDetectorEnsembleTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((100, 100, 3), dtype=np.uint8)
        self.v3_model = object()
        self.v5_model = object()

    def run_detection(self, baseline, addition, addition_model=True):
        def fake_predict(model, *_args, **_kwargs):
            return baseline if model is self.v3_model else addition

        with (
            patch("vision_tools.get_yolo_symbol_model", return_value=self.v3_model),
            patch(
                "vision_tools.get_yolo_symbol_addition_model",
                return_value=self.v5_model if addition_model else None,
            ),
            patch("vision_tools._predict_symbols_with_model", side_effect=fake_predict),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES", ()),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES", ()),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE", 0.50),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED", False),
        ):
            return vision_tools.detect_symbols_with_yolo(self.image)

    def test_default_single_model_path_is_unchanged(self):
        baseline = [
            detection("dimension", [10, 10, 20, 20], 0.8, "local_yolo")
        ]
        result = self.run_detection(baseline, [], addition_model=False)
        self.assertEqual(result, baseline)

    def test_v3_duplicate_is_preserved(self):
        baseline = [
            detection("dimension", [10, 10, 20, 20], 0.61, "local_yolo")
        ]
        addition = [
            detection(
                "dimension",
                [11, 11, 20, 20],
                0.99,
                "local_yolo_ensemble_addition",
            )
        ]
        result = self.run_detection(baseline, addition)
        self.assertEqual(result, baseline)

    def test_non_duplicate_v5_detection_is_added(self):
        baseline = [
            detection("dimension", [10, 10, 20, 20], 0.8, "local_yolo")
        ]
        addition = [
            detection(
                "dimension",
                [70, 70, 20, 20],
                0.9,
                "local_yolo_ensemble_addition",
            )
        ]
        result = self.run_detection(baseline, addition)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item["Detector"] for item in result},
            {"local_yolo", "local_yolo_ensemble_addition"},
        )

    def test_baseline_and_addition_use_separate_confidence_thresholds(self):
        calls = []

        def fake_predict(model, _image, confidence, _image_size, _detector_name):
            calls.append((model, confidence))
            return []

        with (
            patch("vision_tools.get_yolo_symbol_model", return_value=self.v3_model),
            patch("vision_tools.get_yolo_symbol_addition_model", return_value=self.v5_model),
            patch("vision_tools._predict_symbols_with_tiling", side_effect=fake_predict),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_ADDITION_CONFIDENCE", 0.50),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED", False),
        ):
            vision_tools.detect_symbols_with_yolo(self.image, confidence=0.60)

        self.assertEqual(calls, [(self.v3_model, 0.60), (self.v5_model, 0.50)])

    def test_rescue_model_adds_only_configured_classes_after_normal_ensemble(self):
        rescue_model = object()
        baseline = [detection("gdt_frame_symbol", [10, 10, 20, 20], 0.8, "local_yolo")]
        addition = [detection("surface_finish_text", [40, 10, 20, 20], 0.7, "local_yolo_ensemble_addition")]
        rescue = [
            detection("dimension_text", [70, 10, 20, 20], 0.02, "local_yolo_ensemble_rescue"),
            detection("radius", [10, 70, 20, 20], 0.02, "local_yolo_ensemble_rescue"),
        ]

        def fake_predict(model, *_args, **_kwargs):
            if model is self.v3_model:
                return baseline
            if model is self.v5_model:
                return addition
            return rescue

        with (
            patch("vision_tools.get_yolo_symbol_model", return_value=self.v3_model),
            patch("vision_tools.get_yolo_symbol_addition_model", return_value=self.v5_model),
            patch("vision_tools.get_yolo_symbol_rescue_model", return_value=rescue_model),
            patch("vision_tools._predict_symbols_with_model", side_effect=fake_predict),
            patch.object(vision_tools, "YOLO_SYMBOL_RESCUE_CLASSES", ("dimension_text",)),
            patch.object(vision_tools, "YOLO_SYMBOL_RESCUE_CONFIDENCE", 0.01),
            patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_CONTAINMENT_ENABLED", False),
        ):
            result = vision_tools.detect_symbols_with_yolo(self.image)

        self.assertEqual(
            {item["Detector"] for item in result},
            {"local_yolo", "local_yolo_ensemble_addition", "local_yolo_ensemble_rescue"},
        )
        self.assertNotIn("radius", {item["Symbol Class"] for item in result})

    def test_runtime_uses_only_normalized_specialist_classes(self):
        baseline = [
            detection("dimension_text", [10, 10, 20, 20], 0.8, "local_yolo"),
            detection("gdt_frame_symbol", [40, 40, 20, 20], 0.8, "local_yolo"),
        ]
        addition = [
            detection(
                "dimension_text",
                [70, 10, 20, 20],
                0.9,
                "local_yolo_ensemble_addition",
            ),
            detection(
                "gdt_frame_symbol",
                [41, 41, 20, 20],
                0.7,
                "local_yolo_ensemble_addition",
            ),
        ]

        def fake_predict(model, *_args, **_kwargs):
            return baseline if model is self.v3_model else addition

        with (
            patch("vision_tools.get_yolo_symbol_model", return_value=self.v3_model),
            patch("vision_tools.get_yolo_symbol_addition_model", return_value=self.v5_model),
            patch("vision_tools._predict_symbols_with_model", side_effect=fake_predict),
            patch.object(
                vision_tools,
                "YOLO_SYMBOL_ENSEMBLE_ADDITION_CLASSES",
                ("gdt_frame",),
            ),
            patch.object(
                vision_tools,
                "YOLO_SYMBOL_ENSEMBLE_PREFERRED_CLASSES",
                ("gdt_frame",),
            ),
        ):
            result = vision_tools.detect_symbols_with_yolo(self.image)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], baseline[0])
        self.assertEqual(result[1], addition[1])

    def test_tile_grid_covers_far_edges(self):
        tiles = vision_tools.build_yolo_symbol_tiles(
            (2500, 2600, 3),
            tile_size=1280,
            overlap=320,
        )
        self.assertIn((0, 0, 1280, 1280), tiles)
        self.assertIn((1320, 1220, 1280, 1280), tiles)
        self.assertEqual(max(x + width for x, _y, width, _height in tiles), 2600)
        self.assertEqual(max(y + height for _x, y, _width, height in tiles), 2500)

    def test_tile_detection_is_translated_to_page_coordinates(self):
        translated = vision_tools._translate_tile_detection(
            detection("dimension", [100, 200, 30, 40], 0.8, "local_yolo"),
            (960, 640, 1280, 1280),
            (3000, 3000, 3),
            edge_margin=2,
        )
        self.assertEqual(translated["X"], 1060)
        self.assertEqual(translated["Y"], 840)
        self.assertEqual(translated["Box"], "1060,840,1090,880")

    def test_partial_detection_touching_internal_tile_edge_is_rejected(self):
        translated = vision_tools._translate_tile_detection(
            detection("dimension", [0, 200, 30, 40], 0.8, "local_yolo"),
            (960, 640, 1280, 1280),
            (3000, 3000, 3),
            edge_margin=2,
        )
        self.assertIsNone(translated)

    def test_overlapping_tile_duplicates_keep_highest_confidence(self):
        low = detection("gdt_frame_symbol", [100, 100, 80, 30], 0.7, "local_yolo")
        high = detection("gdt_frame_symbol", [102, 101, 80, 30], 0.9, "local_yolo")
        result = vision_tools.deduplicate_tiled_symbol_detections([low, high])
        self.assertEqual(result, [high])

    def test_large_image_uses_tiles_and_restores_page_coordinates(self):
        image = np.zeros((1500, 1500, 3), dtype=np.uint8)
        model = object()

        def fake_predict(_model, crop, *_args, **_kwargs):
            self.assertLessEqual(crop.shape[0], 1280)
            self.assertLessEqual(crop.shape[1], 1280)
            return [
                detection(
                    "dimension",
                    [100, 100, 20, 20],
                    0.8,
                    "local_yolo",
                )
            ]

        with (
            patch("vision_tools._predict_symbols_with_model", side_effect=fake_predict),
            patch.object(vision_tools, "YOLO_SYMBOL_TILING_ENABLED", True),
            patch.object(vision_tools, "YOLO_SYMBOL_TILE_SIZE", 1280),
            patch.object(vision_tools, "YOLO_SYMBOL_TILE_OVERLAP", 320),
        ):
            result = vision_tools._predict_symbols_with_tiling(
                model,
                image,
                0.6,
                1280,
                "local_yolo",
            )

        self.assertEqual(len(result), 4)
        self.assertEqual(
            {(item["X"], item["Y"]) for item in result},
            {(100, 100), (320, 100), (100, 320), (320, 320)},
        )


if __name__ == "__main__":
    unittest.main()
