import hashlib
import json
import math
import re
from collections import Counter


def clean_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def item_box(item):
    row = dict(item or {})
    try:
        x = int(round(float(row.get("X", 0) or 0)))
        y = int(round(float(row.get("Y", 0) or 0)))
        width = int(round(float(row.get("Width", 0) or 0)))
        height = int(round(float(row.get("Height", 0) or 0)))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def canonical_item(item):
    row = dict(item or {})
    return {
        "balloon_no": clean_value(row.get("Balloon No")),
        "symbol": clean_value(row.get("Report Symbol") or row.get("Symbol")),
        "value": clean_value(row.get("Dimension") or row.get("VALUE")),
        "minus": clean_value(row.get("Tolerance -") or row.get("-")),
        "plus": clean_value(row.get("Tolerance +") or row.get("+")),
        "minimum": clean_value(row.get("MIN")),
        "maximum": clean_value(row.get("MAX")),
        "measurement_type": clean_value(row.get("Measurement Type")),
        "review_reason": clean_value(row.get("Review Reason") or row.get("REMARK")),
        "box": item_box(row),
    }


def box_iou(left, right):
    if not left or not right:
        return 0.0
    left_x2 = left["x"] + left["width"]
    left_y2 = left["y"] + left["height"]
    right_x2 = right["x"] + right["width"]
    right_y2 = right["y"] + right["height"]
    intersection_width = max(0, min(left_x2, right_x2) - max(left["x"], right["x"]))
    intersection_height = max(0, min(left_y2, right_y2) - max(left["y"], right["y"]))
    intersection = intersection_width * intersection_height
    union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
    return intersection / union if union > 0 else 0.0


def boxes_equal(left, right, tolerance=1):
    if left is None or right is None:
        return left is None and right is None
    return all(abs(left[key] - right[key]) <= tolerance for key in ("x", "y", "width", "height"))


def _pair_score(original, corrected):
    original_item = canonical_item(original)
    corrected_item = canonical_item(corrected)
    score = box_iou(original_item["box"], corrected_item["box"]) * 0.55
    if original_item["balloon_no"] and original_item["balloon_no"] == corrected_item["balloon_no"]:
        score += 0.30
    if original_item["measurement_type"] and original_item["measurement_type"] == corrected_item["measurement_type"]:
        score += 0.05
    if original_item["symbol"] == corrected_item["symbol"]:
        score += 0.04
    if original_item["value"] and original_item["value"] == corrected_item["value"]:
        score += 0.06
    return score


def _content_equal(original, corrected):
    left = canonical_item(original)
    right = canonical_item(corrected)
    return all(left[key] == right[key] for key in left if key != "box")


def compare_characteristics(original_items, corrected_items):
    originals = [dict(item or {}) for item in original_items or []]
    corrected = [dict(item or {}) for item in corrected_items or []]
    unmatched_original = set(range(len(originals)))
    matches = []

    for corrected_index, corrected_item in enumerate(corrected):
        scored = sorted(
            (
                (_pair_score(originals[original_index], corrected_item), original_index)
                for original_index in unmatched_original
            ),
            reverse=True,
        )
        if not scored:
            continue
        best_score, original_index = scored[0]
        original_balloon = canonical_item(originals[original_index])["balloon_no"]
        corrected_balloon = canonical_item(corrected_item)["balloon_no"]
        same_balloon = bool(original_balloon and original_balloon == corrected_balloon)
        if best_score < 0.35 and not same_balloon:
            continue
        unmatched_original.remove(original_index)
        matches.append((original_index, corrected_index))

    matched_corrected = {corrected_index for _, corrected_index in matches}
    changes = []

    for original_index, corrected_index in matches:
        original = originals[original_index]
        current = corrected[corrected_index]
        position_changed = not boxes_equal(item_box(original), item_box(current))
        content_changed = not _content_equal(original, current)
        if content_changed:
            action = "edited"
        elif position_changed:
            action = "moved"
        else:
            action = "unchanged"
        changes.append(
            {
                "action": action,
                "position_changed": position_changed,
                "detector_training_eligible": item_box(current) is not None,
                "original": canonical_item(original),
                "corrected": canonical_item(current),
            }
        )

    for corrected_index, current in enumerate(corrected):
        if corrected_index not in matched_corrected:
            changes.append(
                {
                    "action": "added",
                    "position_changed": False,
                    "detector_training_eligible": item_box(current) is not None,
                    "original": None,
                    "corrected": canonical_item(current),
                }
            )

    for original_index in sorted(unmatched_original):
        changes.append(
            {
                "action": "deleted",
                "position_changed": False,
                "detector_training_eligible": item_box(originals[original_index]) is not None,
                "original": canonical_item(originals[original_index]),
                "corrected": None,
            }
        )

    changes.sort(
        key=lambda change: (change["corrected"] or change["original"] or {}).get("balloon_no", "")
    )
    return changes


def change_counts(changes):
    counts = Counter(change.get("action", "unknown") for change in changes or [])
    return {name: counts.get(name, 0) for name in ("added", "edited", "deleted", "moved", "unchanged")}


def approval_content_hash(job_id, source_sha256, corrected_items, metadata):
    payload = {
        "job_id": clean_value(job_id),
        "source_sha256": clean_value(source_sha256).lower(),
        "corrected_items": [canonical_item(item) for item in corrected_items or []],
        "metadata": metadata or {},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_identifier(value, length):
    return bool(re.fullmatch(rf"[a-f0-9]{{{int(length)}}}", clean_value(value)))
