import argparse
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
from pdf2image import convert_from_path

from config import BASE_DIR, DATASET_IMAGES_DIR, PDF_DPI, RAW_PDF_FOLDER, ensure_directories


YOLO_DIR = BASE_DIR / "dataset" / "yolo_titleblock"
YOLO_IMAGES_ALL = YOLO_DIR / "images" / "all"
YOLO_LABELS_ALL = YOLO_DIR / "labels" / "all"
CLASS_NAMES = ["title_block"]


def safe_stem(filename):
    return Path(filename).stem.replace(" ", "_")


def write_classes_file():
    (YOLO_DIR / "classes.txt").write_text("\n".join(CLASS_NAMES) + "\n", encoding="utf-8")


def convert_missing_pdf_images():
    ensure_directories()
    pdfs = sorted(RAW_PDF_FOLDER.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {RAW_PDF_FOLDER}")

    for pdf_path in pdfs:
        image_path = DATASET_IMAGES_DIR / f"{safe_stem(pdf_path.name)}.png"
        if image_path.exists():
            continue

        pages = convert_from_path(str(pdf_path), dpi=PDF_DPI, first_page=1, last_page=1)
        image = cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(image_path), image)
        print(f"Converted: {pdf_path.name} -> {image_path.name}")


def prepare_labeling_images():
    convert_missing_pdf_images()
    YOLO_IMAGES_ALL.mkdir(parents=True, exist_ok=True)
    YOLO_LABELS_ALL.mkdir(parents=True, exist_ok=True)
    write_classes_file()

    image_paths = sorted(DATASET_IMAGES_DIR.glob("*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No PNG images found in {DATASET_IMAGES_DIR}")

    for image_path in image_paths:
        target = YOLO_IMAGES_ALL / image_path.name
        if not target.exists():
            shutil.copy2(image_path, target)

    print(f"Prepared {len(image_paths)} images for labeling:")
    print(f"Images: {YOLO_IMAGES_ALL}")
    print(f"Labels: {YOLO_LABELS_ALL}")
    print(f"Class file: {YOLO_DIR / 'classes.txt'}")


def reset_split_dirs():
    for split in ("train", "val"):
        image_dir = YOLO_DIR / "images" / split
        label_dir = YOLO_DIR / "labels" / split
        if image_dir.exists():
            shutil.rmtree(image_dir)
        if label_dir.exists():
            shutil.rmtree(label_dir)
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)


def validate_labels(image_paths):
    missing = []
    empty = []

    for image_path in image_paths:
        label_path = YOLO_LABELS_ALL / f"{image_path.stem}.txt"
        if not label_path.exists():
            missing.append(label_path.name)
            continue
        if not label_path.read_text(encoding="utf-8").strip():
            empty.append(label_path.name)

    if missing or empty:
        lines = []
        if missing:
            lines.append("Missing label files:")
            lines.extend(f"  - {name}" for name in missing)
        if empty:
            lines.append("Empty label files:")
            lines.extend(f"  - {name}" for name in empty)
        raise RuntimeError(
            "\n".join(lines)
            + "\n\nLabel every image first. Each drawing should have one title_block box."
        )


def write_data_yaml():
    dataset_path = YOLO_DIR.as_posix()
    yaml_text = (
        f"path: {dataset_path}\n"
        "train: images/train\n"
        "val: images/val\n\n"
        "names:\n"
        "  0: title_block\n"
    )
    (YOLO_DIR / "data.yaml").write_text(yaml_text, encoding="utf-8")


def split_dataset(val_ratio, seed):
    image_paths = sorted(YOLO_IMAGES_ALL.glob("*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No labeling images found in {YOLO_IMAGES_ALL}")

    validate_labels(image_paths)
    reset_split_dirs()
    write_classes_file()
    write_data_yaml()

    rng = random.Random(seed)
    shuffled = image_paths[:]
    rng.shuffle(shuffled)

    val_count = max(1, round(len(shuffled) * val_ratio))
    val_set = {path.name for path in shuffled[:val_count]}

    for image_path in image_paths:
        split = "val" if image_path.name in val_set else "train"
        label_path = YOLO_LABELS_ALL / f"{image_path.stem}.txt"
        shutil.copy2(image_path, YOLO_DIR / "images" / split / image_path.name)
        shutil.copy2(label_path, YOLO_DIR / "labels" / split / label_path.name)

    print("YOLO dataset split complete:")
    print(f"Train images: {len(image_paths) - val_count}")
    print(f"Val images: {val_count}")
    print(f"Data YAML: {YOLO_DIR / 'data.yaml'}")


def main():
    parser = argparse.ArgumentParser(description="Prepare YOLO title-block training data.")
    parser.add_argument(
        "--stage",
        choices=("labeling", "split"),
        default="labeling",
        help="Use 'labeling' before manual annotation, then 'split' after labels are done.",
    )
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.stage == "labeling":
        prepare_labeling_images()
    else:
        split_dataset(args.val_ratio, args.seed)


if __name__ == "__main__":
    main()
