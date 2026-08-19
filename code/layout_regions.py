REPORT_EXCLUSION_REGIONS = [
    # Bottom title block / revision table.
    (0.50, 0.72, 1.0, 1.0, "title/revision/table zone"),
    # Lower-left tolerance or notes table.
    (0.0, 0.78, 0.36, 1.0, "lower-left table zone"),
    # Left drawing border index strip.
    (0.0, 0.0, 0.08, 1.0, "left border index zone"),
]


MEASUREMENT_EXCLUSION_REGIONS = [
    # Common title block and revision/table areas on the engineering drawings.
    (0.50, 0.72, 1.0, 1.0, "title/revision/table zone"),
    (0.0, 0.78, 0.36, 1.0, "lower-left table zone"),
    (0.55, 0.0, 1.0, 0.18, "top title/header zone"),
    (0.70, 0.62, 1.0, 1.0, "right-side notes/title zone"),
    (0.0, 0.0, 0.08, 1.0, "left border index zone"),
]


def normalized_center_from_item(item, image_width, image_height):
    x = int(item.get("X", 0) or 0)
    y = int(item.get("Y", 0) or 0)
    width = int(item.get("Width", 0) or 0)
    height = int(item.get("Height", 0) or 0)
    return (
        (x + width / 2) / max(1, image_width),
        (y + height / 2) / max(1, image_height),
    )


def exclusion_region_label(center_x, center_y, regions):
    for left, top, right, bottom, label in regions:
        if left <= center_x <= right and top <= center_y <= bottom:
            return label
    return ""


def is_inside_exclusion_regions(center_x, center_y, regions):
    return bool(exclusion_region_label(center_x, center_y, regions))
