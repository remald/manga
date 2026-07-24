import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QImage, QPainter, QFont, QTextDocument, QTextOption, QColor, QPalette,
    QAbstractTextDocumentLayout,
)

from .box_layout import region_center_in_bubble
from .region_item import (
    apply_line_height,
    DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE,
)

INPAINT_PAD = 5   # px around a text box in the LaMa mask
BUBBLE_PAD = 4    # px around the bubble bbox in the segmentation crop
BUBBLE_RING = 6   # px ring around a text box that votes for the interior component
MIN_BOX_COVERAGE = 0.85  # interior must cover this share of a text box, else LaMa


def _erase_box(region: dict) -> dict:
    """The rect to erase: the originally detected text box, not the possibly
    widened/moved region rect. Hand-drawn regions have no source_box."""
    return region.get("source_box") or {
        "x": region["x"], "y": region["y"], "w": region["w"], "h": region["h"],
    }


def _bubble_of(region: dict, bubbles: list) -> int | None:
    box = _erase_box(region)
    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    for i, b in enumerate(bubbles):
        if b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]:
            return i
    return None


def _fill_bubble_interior(arr: np.ndarray, bubble: dict, regions: list) -> bool:
    """Repaints the bubble interior — the light connected component around the
    text, holes (text strokes) included — with its median tone, staying exactly
    inside the dark outline. Returns False when segmentation doesn't add up
    (inverted/open bubble, text sticking out): caller falls back to LaMa."""
    h, w = arr.shape[:2]
    x0 = max(0, int(bubble["x"]) - BUBBLE_PAD)
    y0 = max(0, int(bubble["y"]) - BUBBLE_PAD)
    x1 = min(w, int(bubble["x"] + bubble["w"]) + BUBBLE_PAD)
    y1 = min(h, int(bubble["y"] + bubble["h"]) + BUBBLE_PAD)
    crop = arr[y0:y1, x0:x1]
    if crop.size == 0:
        return False

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, light = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, labels = cv2.connectedComponents((light > 0).astype(np.uint8))

    # the interior is the light component surrounding the text boxes: collect
    # label votes from a thin ring around each box (label 0 = dark pixels)
    votes = np.zeros(labels.max() + 1, dtype=np.int64)
    ch, cw = labels.shape
    boxes = []
    for r in regions:
        box = _erase_box(r)
        bx0 = int(box["x"]) - x0
        by0 = int(box["y"]) - y0
        bx1 = int(box["x"] + box["w"]) - x0
        by1 = int(box["y"] + box["h"]) - y0
        boxes.append((bx0, by0, bx1, by1))
        rx0 = max(0, bx0 - BUBBLE_RING)
        ry0 = max(0, by0 - BUBBLE_RING)
        rx1 = min(cw, bx1 + BUBBLE_RING)
        ry1 = min(ch, by1 + BUBBLE_RING)
        ring = np.zeros((ch, cw), dtype=bool)
        ring[ry0:ry1, rx0:rx1] = True
        ring[max(0, by0):by1, max(0, bx0):bx1] = False
        votes += np.bincount(labels[ring].ravel(), minlength=len(votes))
    votes[0] = 0
    if votes.sum() == 0:
        return False

    interior = labels == votes.argmax()
    filled = ndimage.binary_fill_holes(interior)

    # a closed bubble may touch the crop border at tangent arcs, but its
    # corners always stay outside the interior; a filled corner means the
    # component leaked through a gap (tail, broken outline) onto the page
    # background — painting that would stamp a flat rectangle
    k = BUBBLE_PAD
    if (filled[:k, :k].any() or filled[:k, -k:].any()
            or filled[-k:, :k].any() or filled[-k:, -k:].any()):
        return False

    # every text box must lie (almost) fully inside the segmented interior
    for bx0, by0, bx1, by1 in boxes:
        patch = filled[max(0, by0):by1, max(0, bx0):bx1]
        if patch.size == 0 or patch.mean() < MIN_BOX_COVERAGE:
            return False

    tone = np.median(crop[interior], axis=0)
    crop[filled] = tone.astype(arr.dtype)
    return True


def export_page(image_path, regions: list[dict], bubbles: list[dict], inpainter) -> QImage:
    """Renders the translated page: in-bubble text erased by repainting the
    segmented bubble interior with its tone, everything else (and bubbles
    where segmentation fails) by one LaMa pass; translations drawn on top
    with the exact editor font settings. Regions with translation disabled
    are left untouched."""
    image = Image.open(image_path).convert("RGB")
    arr = np.array(image)
    h, w = arr.shape[:2]

    active = [r for r in regions if r["enabled"] and r["translated_text"].strip()]
    outside = [r for r in active if not region_center_in_bubble(r, bubbles)]

    # 1) erase in-bubble text by repainting each bubble's interior with its
    # median tone, exactly up to the outline
    by_bubble = {}
    for r in active:
        if r not in outside:
            by_bubble.setdefault(_bubble_of(r, bubbles), []).append(r)
    lama_regions = list(outside)
    for bi, regs in by_bubble.items():
        if bi is None or not _fill_bubble_interior(arr, bubbles[bi], regs):
            lama_regions.extend(regs)

    # 2) erase the rest with one LaMa pass over a combined mask
    if lama_regions:
        mask = np.zeros((h, w), dtype=np.uint8)
        for r in lama_regions:
            box = _erase_box(r)
            x0 = max(0, int(box["x"]) - INPAINT_PAD)
            y0 = max(0, int(box["y"]) - INPAINT_PAD)
            x1 = min(w, int(box["x"] + box["w"]) + INPAINT_PAD)
            y1 = min(h, int(box["y"] + box["h"]) + INPAINT_PAD)
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
            doc.setDefaultTextOption(QTextOption(Qt.AlignHCenter))
            doc.setPlainText(r["translated_text"])
            apply_line_height(doc)
            doc.setTextWidth(r["w"])
            # white outline everywhere: on art it's essential, in bubbles it's
            # invisible on intact white and keeps text readable on a damaged one
            outline = max(2, round(size / 10))
            # center vertically in the box, matching the editor
            ty = r["y"] + max(0.0, (r["h"] - doc.size().height()) / 2)
            _draw_document(painter, doc, r["x"], ty, outline)
    finally:
        painter.end()
    return qimage


def _draw_document(painter: QPainter, doc: QTextDocument, x: float, y: float, outline: int):
    """Draws the laid-out text; with outline > 0, stamps it in white in 8
    offset directions first, then draws the black text on top."""

    def draw_at(dx, dy, color):
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.Text, color)
        painter.save()
        painter.translate(x + dx, y + dy)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    if outline > 0:
        white = QColor("white")
        for dx in (-outline, 0, outline):
            for dy in (-outline, 0, outline):
                if dx or dy:
                    draw_at(dx, dy, white)
    draw_at(0, 0, QColor("black"))


def _fit_font_size(text: str, family: str, width: float, height: float) -> int:
    """Mirror of TextRegionItem.fit_font_size for regions that were never
    shown in the editor."""
    doc = QTextDocument()
    doc.setPlainText(text)
    apply_line_height(doc)
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
