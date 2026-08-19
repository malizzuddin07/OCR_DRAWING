import os

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
CODE_DIR = ROOT_DIR / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from roboflow_workflow_client import (  # noqa: E402
    ROBOFLOW_WORKFLOW_OUTPUT_KEYS,
    assert_engineering_symbol_output_shape,
    run_engineering_symbol_workflow,
)


def detect_symbols(image_path):
    if not os.getenv("ROBOFLOW_API_KEY"):
        raise RuntimeError("ROBOFLOW_API_KEY is not set")

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    result = run_engineering_symbol_workflow(str(image_path), timeout_seconds=120)
    assert_engineering_symbol_output_shape(result)
    return result


if __name__ == "__main__":
    result = detect_symbols(
        ROOT_DIR
        / "dataset"
        / "symbol_training_images"
        / "images"
        / "FAB-C-3060-010-9100_W3-C100807301-00_tile_r00_c04.png"
    )

    predictions = result[0]["model_output"]["predictions"]

    print("Roboflow workflow smoke test passed.")
    print("Prediction count:", len(predictions))
    print("First prediction:", predictions[0] if predictions else None)
