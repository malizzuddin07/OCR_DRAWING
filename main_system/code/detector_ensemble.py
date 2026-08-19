"""Conservative detector ensemble helpers.

The baseline model always wins duplicate decisions. The addition model may
only contribute a same-class box when it does not substantially overlap an
already retained box.
"""

from __future__ import annotations


def box_iou(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    intersection = max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
        0.0, min(ay + ah, by + bh) - max(ay, by)
    )
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def intersection_over_smaller(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    intersection = max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
        0.0, min(ay + ah, by + bh) - max(ay, by)
    )
    smaller = min(aw * ah, bw * bh)
    return intersection / smaller if smaller > 0 else 0.0


def is_duplicate(first, second, iou_threshold=0.30, containment_threshold=0.70):
    if first["class_name"] != second["class_name"]:
        return False
    if box_iou(first["box"], second["box"]) >= iou_threshold:
        return True
    return (
        containment_threshold is not None
        and intersection_over_smaller(first["box"], second["box"])
        >= containment_threshold
    )


def baseline_priority_merge(
    baseline_predictions,
    addition_predictions,
    iou_threshold=0.30,
    containment_threshold=0.70,
    addition_classes=None,
    preferred_addition_classes=None,
    baseline_source="v3",
    addition_source="v5",
):
    """Merge a baseline with an optional class-specific specialist.

    Without class arguments this preserves the original baseline-priority
    behavior. ``addition_classes`` limits what the specialist may contribute.
    For ``preferred_addition_classes``, an overlapping same-class specialist
    box replaces the baseline box.
    """
    enabled_classes = set(addition_classes or ())
    preferred_classes = set(preferred_addition_classes or ())
    kept = [
        {**prediction, "source_model": baseline_source}
        for prediction in baseline_predictions
    ]
    suppressed = []
    for prediction in sorted(
        addition_predictions, key=lambda item: item["confidence"], reverse=True
    ):
        if enabled_classes and prediction["class_name"] not in enabled_classes:
            suppressed.append(
                {
                    **prediction,
                    "source_model": addition_source,
                    "suppression_reason": "class_not_enabled",
                }
            )
            continue
        duplicate = next(
            (
                existing
                for existing in kept
                if is_duplicate(
                    existing,
                    prediction,
                    iou_threshold=iou_threshold,
                    containment_threshold=containment_threshold,
                )
            ),
            None,
        )
        if duplicate is not None:
            if (
                prediction["class_name"] in preferred_classes
                and duplicate["source_model"] == baseline_source
            ):
                replacement = {**prediction, "source_model": addition_source}
                kept[kept.index(duplicate)] = replacement
                suppressed.append(
                    {
                        **duplicate,
                        "suppression_reason": "preferred_specialist_replaced_baseline",
                        "suppressed_by_source": addition_source,
                        "suppressed_by_box": prediction["box"],
                        "duplicate_iou": box_iou(duplicate["box"], prediction["box"]),
                        "intersection_over_smaller": intersection_over_smaller(
                            duplicate["box"], prediction["box"]
                        ),
                    }
                )
                continue
            suppressed.append(
                {
                    **prediction,
                    "source_model": addition_source,
                    "suppression_reason": "duplicate",
                    "suppressed_by_source": duplicate["source_model"],
                    "suppressed_by_box": duplicate["box"],
                    "duplicate_iou": box_iou(duplicate["box"], prediction["box"]),
                    "intersection_over_smaller": intersection_over_smaller(
                        duplicate["box"], prediction["box"]
                    ),
                }
            )
            continue
        kept.append({**prediction, "source_model": addition_source})
    return kept, suppressed
