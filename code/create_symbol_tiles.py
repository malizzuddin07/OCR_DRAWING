import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATASET_DIR, DATASET_IMAGES_DIR, RAW_PDF_FOLDER


OUTPUT_DIR = DATASET_DIR / "symbol_training_images"
OUTPUT_IMAGES_DIR = OUTPUT_DIR / "images"
METADATA_PATH = OUTPUT_DIR / "tiles_metadata.csv"


def clean_stem(path):
    return Path(path).stem.replace(" ", "_")


def load_pdf_first_page(pdf_path, dpi):
    pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=1, last_page=1)
    return cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR)


def load_image(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")
    return image


def pad_tile(tile, tile_size):
    height, width = tile.shape[:2]
    if height == tile_size and width == tile_size:
        return tile

    padded = np.full((tile_size, tile_size, 3), 255, dtype=np.uint8)
    padded[:height, :width] = tile
    return padded


def ink_ratio(tile):
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    return cv2.countNonZero(binary) / max(1, binary.size)


def edge_ratio(tile):
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    return cv2.countNonZero(edges) / max(1, edges.size)


def should_keep_tile(tile, min_ink_ratio, min_edge_ratio):
    return ink_ratio(tile) >= min_ink_ratio or edge_ratio(tile) >= min_edge_ratio


def tile_image(image, tile_size, overlap):
    height, width = image.shape[:2]
    step = max(1, int(tile_size * (1.0 - overlap)))

    xs = list(range(0, max(1, width - tile_size + 1), step))
    ys = list(range(0, max(1, height - tile_size + 1), step))

    if not xs or xs[-1] != max(0, width - tile_size):
        xs.append(max(0, width - tile_size))
    if not ys or ys[-1] != max(0, height - tile_size):
        ys.append(max(0, height - tile_size))

    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            x2 = min(width, x + tile_size)
            y2 = min(height, y + tile_size)
            tile = image[y:y2, x:x2]
            yield row, col, x, y, x2, y2, pad_tile(tile, tile_size)


def iter_sources(source, limit):
    if source == "pdf":
        paths = sorted(RAW_PDF_FOLDER.glob("*.pdf"))
    else:
        paths = sorted(DATASET_IMAGES_DIR.glob("*.png"))

    if limit:
        paths = paths[:limit]

    return paths


def clear_output_folder():
    OUTPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_IMAGES_DIR.glob("*.png"):
        path.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Create cropped/tiled images for Roboflow symbol detection training."
    )
    parser.add_argument(
        "--source",
        choices=("pdf", "images"),
        default="pdf",
        help="Use original PDFs at the requested DPI, or existing dataset/images PNG files.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF conversion DPI when --source pdf is used.")
    parser.add_argument("--tile-size", type=int, default=1280, help="Square tile size in pixels.")
    parser.add_argument("--overlap", type=float, default=0.25, help="Tile overlap ratio from 0.0 to 0.8.")
    parser.add_argument("--min-ink-ratio", type=float, default=0.0015, help="Skip near-blank tiles below this ink ratio.")
    parser.add_argument("--min-edge-ratio", type=float, default=0.0010, help="Skip near-blank tiles below this edge ratio.")
    parser.add_argument("--limit", type=int, help="Process only the first N files.")
    parser.add_argument("--keep-existing", action="store_true", help="Do not delete existing output tiles first.")
    args = parser.parse_args()

    if not 0 <= args.overlap < 0.8:
        raise ValueError("--overlap must be between 0.0 and 0.8")

    OUTPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not args.keep_existing:
        clear_output_folder()

    rows = []
    kept_count = 0
    skipped_count = 0
    source_paths = iter_sources(args.source, args.limit)

    if not source_paths:
        print(f"No source files found for source={args.source}")
        return

    print(f"Creating symbol training tiles from {len(source_paths)} file(s)...")
    print(f"Output folder: {OUTPUT_IMAGES_DIR}")

    for source_path in source_paths:
        print(f"Processing: {source_path.name}")
        if args.source == "pdf":
            image = load_pdf_first_page(source_path, args.dpi)
        else:
            image = load_image(source_path)

        source_stem = clean_stem(source_path)
        image_height, image_width = image.shape[:2]

        for row, col, x1, y1, x2, y2, tile in tile_image(image, args.tile_size, args.overlap):
            tile_ink_ratio = ink_ratio(tile)
            tile_edge_ratio = edge_ratio(tile)

            if not should_keep_tile(tile, args.min_ink_ratio, args.min_edge_ratio):
                skipped_count += 1
                continue

            output_name = f"{source_stem}_tile_r{row:02d}_c{col:02d}.png"
            output_path = OUTPUT_IMAGES_DIR / output_name
            cv2.imwrite(str(output_path), tile)
            kept_count += 1
            rows.append(
                {
                    "tile_file": output_name,
                    "source_file": source_path.name,
                    "source_type": args.source,
                    "dpi": args.dpi if args.source == "pdf" else "",
                    "source_width": image_width,
                    "source_height": image_height,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "tile_size": args.tile_size,
                    "ink_ratio": round(tile_ink_ratio, 6),
                    "edge_ratio": round(tile_edge_ratio, 6),
                }
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("w", newline="", encoding="utf-8") as metadata_file:
        writer = csv.DictWriter(
            metadata_file,
            fieldnames=[
                "tile_file",
                "source_file",
                "source_type",
                "dpi",
                "source_width",
                "source_height",
                "x1",
                "y1",
                "x2",
                "y2",
                "tile_size",
                "ink_ratio",
                "edge_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Done. Kept tiles: {kept_count}")
    print(f"Skipped near-blank tiles: {skipped_count}")
    print(f"Upload this folder to Roboflow: {OUTPUT_IMAGES_DIR}")
    print(f"Metadata saved to: {METADATA_PATH}")


if __name__ == "__main__":
    main()
