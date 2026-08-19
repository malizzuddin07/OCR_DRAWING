import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2

from config import BASE_DIR


IMAGE_DIR = BASE_DIR / "dataset" / "yolo_titleblock" / "images" / "all"
LABEL_DIR = BASE_DIR / "dataset" / "yolo_titleblock" / "labels" / "all"
CLASS_ID = 0


class LabelState:
    def __init__(self):
        self.start = None
        self.current = None
        self.box = None
        self.dragging = False


def normalize_box(box, width, height):
    x1, y1, x2, y2 = box
    x1, x2 = sorted((max(0, x1), min(width - 1, x2)))
    y1, y2 = sorted((max(0, y1), min(height - 1, y2)))

    box_width = x2 - x1
    box_height = y2 - y1
    x_center = x1 + box_width / 2
    y_center = y1 + box_height / 2

    return (
        x_center / width,
        y_center / height,
        box_width / width,
        box_height / height,
    )


def denormalize_box(values, width, height):
    x_center, y_center, box_width, box_height = values
    x_center *= width
    y_center *= height
    box_width *= width
    box_height *= height

    x1 = int(x_center - box_width / 2)
    y1 = int(y_center - box_height / 2)
    x2 = int(x_center + box_width / 2)
    y2 = int(y_center + box_height / 2)
    return x1, y1, x2, y2


def label_path_for(image_path):
    return LABEL_DIR / f"{image_path.stem}.txt"


def load_existing_box(image_path, width, height):
    label_path = label_path_for(image_path)
    if not label_path.exists():
        return None

    text = label_path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    parts = text.split()
    if len(parts) != 5:
        return None

    values = [float(value) for value in parts[1:]]
    return denormalize_box(values, width, height)


def save_box(image_path, box, width, height):
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    x_center, y_center, box_width, box_height = normalize_box(box, width, height)
    text = f"{CLASS_ID} {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}\n"
    label_path_for(image_path).write_text(text, encoding="utf-8")


def delete_box(image_path):
    label_path = label_path_for(image_path)
    if label_path.exists():
        label_path.unlink()


def backup_labels():
    if not LABEL_DIR.exists():
        return

    backup_dir = LABEL_DIR.parent / "all_backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(LABEL_DIR, backup_dir)
    print(f"Backed up existing labels to: {backup_dir}")


def fit_to_screen(image, max_width, max_height):
    height, width = image.shape[:2]
    scale = min(max_width / width, max_height / height, 1.0)
    if scale == 1.0:
        return image.copy(), scale

    resized = cv2.resize(
        image,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def scale_box(box, scale):
    return tuple(int(value * scale) for value in box)


def unscale_box(box, scale):
    if scale == 1:
        return box
    return tuple(int(value / scale) for value in box)


def mouse_callback(event, x, y, flags, state):
    if event == cv2.EVENT_LBUTTONDOWN:
        state.start = (x, y)
        state.current = (x, y)
        state.dragging = True

    elif event == cv2.EVENT_MOUSEMOVE and state.dragging:
        state.current = (x, y)

    elif event == cv2.EVENT_LBUTTONUP and state.dragging:
        state.current = (x, y)
        state.box = (*state.start, *state.current)
        state.dragging = False


def draw_view(display_image, state, image_path, index, total):
    view = display_image.copy()

    box = state.box
    if state.dragging and state.start and state.current:
        box = (*state.start, *state.current)

    if box:
        x1, y1, x2, y2 = box
        cv2.rectangle(view, (x1, y1), (x2, y2), (0, 220, 0), 2)

    instructions = [
        f"{index + 1}/{total} {image_path.name}",
        "Drag title block | S save | N next | P previous | D delete | Q quit",
    ]
    y = 28
    for line in instructions:
        cv2.putText(
            view,
            line,
            (14, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            line,
            (14, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        y += 26

    return view


def main():
    parser = argparse.ArgumentParser(description="Simple YOLO title-block labeler.")
    parser.add_argument("--max-width", type=int, default=1600)
    parser.add_argument("--max-height", type=int, default=900)
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    image_paths = sorted(IMAGE_DIR.glob("*.png"))
    if not image_paths:
        raise SystemExit(f"No images found in {IMAGE_DIR}. Run prepare_yolo_dataset.py first.")

    if args.backup:
        backup_labels()

    window_name = "Title Block Labeler"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    index = 0
    while 0 <= index < len(image_paths):
        image_path = image_paths[index]
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Skipping unreadable image: {image_path}")
            index += 1
            continue

        height, width = image.shape[:2]
        display_image, scale = fit_to_screen(image, args.max_width, args.max_height)
        state = LabelState()
        existing_box = load_existing_box(image_path, width, height)
        if existing_box:
            state.box = scale_box(existing_box, scale)

        cv2.setMouseCallback(window_name, mouse_callback, state)

        while True:
            view = draw_view(display_image, state, image_path, index, len(image_paths))
            cv2.imshow(window_name, view)
            key = cv2.waitKey(20) & 0xFF

            if key in (ord("q"), 27):
                cv2.destroyAllWindows()
                return

            if key == ord("s"):
                if not state.box:
                    print(f"No box to save for {image_path.name}")
                    continue
                save_box(image_path, unscale_box(state.box, scale), width, height)
                print(f"Saved: {label_path_for(image_path).name}")

            elif key == ord("d"):
                state.box = None
                delete_box(image_path)
                print(f"Deleted label: {label_path_for(image_path).name}")

            elif key == ord("n"):
                index += 1
                break

            elif key == ord("p"):
                index = max(0, index - 1)
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
