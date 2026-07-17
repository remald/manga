import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPainter, QFont, QTextDocument

from .region_item import (
    DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE,
)

FILL_PAD = 3      # px around a text box when painting it over with bubble tone
INPAINT_PAD = 5   # px around a text box in the LaMa mask
RING_WIDTH = 6    # px sampling ring around a text box for the bubble tone


def region_center_in_bubble(region: dict, bubbles: list[dict]) -> bool:
    cx = region["x"] + region["w"] / 2
    cy = region["y"] + region["h"] / 2
    return any(
        b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]
        for b in bubbles
    )


def _sample_bubble_tone(arr: np.ndarray, region: dict) -> tuple:
    """Median color of a thin ring just outside the text box — mostly bubble
    background, and the median discards stray text-stroke pixels."""
    h, w = arr.shape[:2]
    x0 = max(0, int(region["x"]) - RING_WIDTH)
    y0 = max(0, int(region["y"]) - RING_WIDTH)
    x1 = min(w, int(region["x"] + region["w"]) + RING_WIDTH)
    y1 = min(h, int(region["y"] + region["h"]) + RING_WIDTH)
    ix0 = min(x1, int(region["x"]))
    iy0 = min(y1, int(region["y"]))
    ix1 = max(x0, int(region["x"] + region["w"]))
    iy1 = max(y0, int(region["y"] + region["h"]))

    ring = np.ones((h, w), dtype=bool)
    ring[:y0, :] = False
    ring[y1:, :] = False
    ring[:, :x0] = False
    ring[:, x1:] = False
    ring[iy0:iy1, ix0:ix1] = False
    pixels = arr[ring]
    if len(pixels) == 0:
        return (255, 255, 255)
    return tuple(int(v) for v in np.median(pixels, axis=0))


def export_page(image_path, regions: list[dict], bubbles: list[dict], inpainter) -> QImage:
    """Renders the translated page: original text erased (bubble-tone fill
    inside bubbles, LaMa inpainting outside), translations drawn on top with
    the exact editor font settings. Regions with translation disabled are
    left untouched."""
    image = Image.open(image_path).convert("RGB")
    arr = np.array(image)
    h, w = arr.shape[:2]

    active = [r for r in regions if r["enabled"] and r["translated_text"].strip()]
    in_bubble = [r for r in active if region_center_in_bubble(r, bubbles)]
    outside = [r for r in active if r not in in_bubble]

    # 1) erase text inside bubbles with the bubble tone
    for r in in_bubble:
        tone = _sample_bubble_tone(arr, r)
        x0 = max(0, int(r["x"]) - FILL_PAD)
        y0 = max(0, int(r["y"]) - FILL_PAD)
        x1 = min(w, int(r["x"] + r["w"]) + FILL_PAD)
        y1 = min(h, int(r["y"] + r["h"]) + FILL_PAD)
        arr[y0:y1, x0:x1] = tone

    # 2) erase text outside bubbles with one LaMa pass over a combined mask
    if outside:
        mask = np.zeros((h, w), dtype=np.uint8)
        for r in outside:
            x0 = max(0, int(r["x"]) - INPAINT_PAD)
            y0 = max(0, int(r["y"]) - INPAINT_PAD)
            x1 = min(w, int(r["x"] + r["w"]) + INPAINT_PAD)
            y1 = min(h, int(r["y"] + r["h"]) + INPAINT_PAD)
            mask[y0:y1, x0:x1] = 255
        inpainted = inpainter.inpaint(Image.fromarray(arr), Image.fromarray(mask, "L"))
        arr = np.array(inpainted.convert("RGB"))[:h, :w]

    # 3) draw translations exactly as laid out in the editor
    qimage = QImage(arr.tobytes(), w, h, 3 * w, QImage.Format_RGB888).copy()
    painter = QPainter(qimage)
    try:
        painter.setRenderHint(QPainter.TextAntialiasing)
        for r in active:
            family = r.get("font_family", DEFAULT_FONT_FAMILY)
            size = r.get("font_size")
            if size is None:
                # region never materialized in the editor (page not visited):
                # auto-fit here the same way the editor would
                size = (
                    _fit_font_size(r["translated_text"], family, r["w"], r["h"])
                    if r.get("auto_fit", True) else DEFAULT_FONT_SIZE
                )
            doc = QTextDocument()
            doc.setDefaultFont(QFont(family, size))
            doc.setPlainText(r["translated_text"])
            doc.setTextWidth(r["w"])
            painter.save()
            painter.translate(r["x"], r["y"])
            doc.drawContents(painter)
            painter.restore()
    finally:
        painter.end()
    return qimage


def _fit_font_size(text: str, family: str, width: float, height: float) -> int:
    """Mirror of TextRegionItem.fit_font_size for regions that were never
    shown in the editor."""
    doc = QTextDocument()
    doc.setPlainText(text)
    doc.setTextWidth(width)
    lo, hi, best = MIN_FONT_SIZE, MAX_FONT_SIZE, MIN_FONT_SIZE
    while lo <= hi:
        mid = (lo + hi) // 2
        doc.setDefaultFont(QFont(family, mid))
        if doc.size().height() <= height:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best
