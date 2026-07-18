"""Geometry adjustments for detected text boxes before they become regions."""

MARGIN_RATIO = 0.15  # bubble width fraction kept clear on each side
BOX_GAP = 4.0        # minimal horizontal gap between neighboring boxes


def region_center_in_bubble(region: dict, bubbles: list) -> bool:
    cx = region["x"] + region["w"] / 2
    cy = region["y"] + region["h"] / 2
    return any(
        b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]
        for b in bubbles
    )


def widen_boxes_in_bubbles(texts: list, bubbles: list) -> list:
    """Japanese bubble text is often narrow and vertical; horizontal-script
    translations need width. Returns copies of `texts` where each box inside
    a bubble is widened toward the bubble edges (minus margin), clamped so it
    never overlaps another box. Boxes outside bubbles are left as-is."""
    rects = [dict(t) for t in texts]
    for i, t in enumerate(rects):
        cx = t["x"] + t["w"] / 2
        cy = t["y"] + t["h"] / 2
        bubble = next(
            (b for b in bubbles
             if b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]),
            None,
        )
        if bubble is None:
            continue
        margin = bubble["w"] * MARGIN_RATIO
        left = bubble["x"] + margin
        right = bubble["x"] + bubble["w"] - margin

        # clamp against any box sharing a horizontal band with this one
        for j, o in enumerate(rects):
            if j == i:
                continue
            if o["y"] < t["y"] + t["h"] and t["y"] < o["y"] + o["h"]:
                if o["x"] + o["w"] <= t["x"]:
                    left = max(left, o["x"] + o["w"] + BOX_GAP)
                elif o["x"] >= t["x"] + t["w"]:
                    right = min(right, o["x"] - BOX_GAP)

        if right - left > t["w"]:
            t["x"] = left
            t["w"] = right - left
    return rects
