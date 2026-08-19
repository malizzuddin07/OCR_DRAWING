import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


CODE_DIR = Path(__file__).resolve().parents[1] / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

import run_golden_suite  # noqa: E402
import vision_tools  # noqa: E402


class EnsemblePreloadTests(unittest.TestCase):
    def test_preload_loads_primary_when_ensemble_is_not_required(self):
        with (
            patch.dict(os.environ, {"YOLO_SYMBOL_ENSEMBLE_REQUIRED": "0"}),
            patch("vision_tools.get_yolo_symbol_model", return_value=object()) as primary,
            patch(
                "vision_tools.get_yolo_symbol_addition_model",
                side_effect=AssertionError("addition must not load"),
            ),
        ):
            run_golden_suite.preload_required_ensemble()
        primary.assert_called_once_with()

    def test_preload_rejects_missing_primary_model(self):
        with (
            patch.dict(os.environ, {"YOLO_SYMBOL_ENSEMBLE_REQUIRED": "0"}),
            patch("vision_tools.get_yolo_symbol_model", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                run_golden_suite.preload_required_ensemble()

    def test_preload_requires_both_models(self):
        with (
            patch.dict(os.environ, {"YOLO_SYMBOL_ENSEMBLE_REQUIRED": "1"}),
            patch("vision_tools.get_yolo_symbol_model", return_value=object()),
            patch("vision_tools.get_yolo_symbol_addition_model", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                run_golden_suite.preload_required_ensemble()

    def test_preload_accepts_both_models(self):
        with (
            patch.dict(os.environ, {"YOLO_SYMBOL_ENSEMBLE_REQUIRED": "1"}),
            patch("vision_tools.get_yolo_symbol_model", return_value=object()),
            patch(
                "vision_tools.get_yolo_symbol_addition_model",
                return_value=object(),
            ),
        ):
            run_golden_suite.preload_required_ensemble()

    def test_required_prediction_failure_is_not_silenced(self):
        class BrokenModel:
            def predict(self, *_args, **_kwargs):
                raise OSError("test prediction failure")

        with patch.object(vision_tools, "YOLO_SYMBOL_ENSEMBLE_REQUIRED", True):
            with self.assertRaises(RuntimeError):
                vision_tools._predict_symbols_with_model(
                    BrokenModel(),
                    object(),
                    0.60,
                    1280,
                    "test_detector",
                )


if __name__ == "__main__":
    unittest.main()
