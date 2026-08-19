import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATASET_IMAGES_DIR, DEBUG_LAYOUT_DIR, LAYOUT_REGIONS_DIR, ensure_directories
from vision_tools import process_image


def main():
    parser = argparse.ArgumentParser(description="Detect drawing layout regions.")
    parser.add_argument(
        "--image",
        type=Path,
        help="Optional single image path. If omitted, all dataset/images PNG files are processed.",
    )
    args = parser.parse_args()

    ensure_directories()

    image_paths = [args.image] if args.image else sorted(DATASET_IMAGES_DIR.glob("*.png"))
    if not image_paths:
        print(f"No PNG images found in {DATASET_IMAGES_DIR}")
        return

    for image_path in image_paths:
        regions = process_image(image_path)
        detected = ", ".join(sorted(regions))
        print(f"{image_path.name}: {detected}")

    print(f"\nSaved layout JSON to: {LAYOUT_REGIONS_DIR}")
    print(f"Saved debug images to: {DEBUG_LAYOUT_DIR}")


if __name__ == "__main__":
    main()
