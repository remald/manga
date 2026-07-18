from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsItem

HANDLE_MARGIN = 8.0
MIN_SIZE = 12.0
DEFAULT_FONT_FAMILY = "Arial"
DEFAULT_FONT_SIZE = 14
MIN_FONT_SIZE = 5   # readability floor for auto-fit only; manual choice is unrestricted
MAX_FONT_SIZE = 72

_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
}


class TextRegionItem(QGraphicsRectItem):
    """One detected text fragment: a movable/resizable box with the
    translated text rendered on top of it. Detection/inpainting results
    will populate `source_text`/`translated_text`; for now they are set
    manually through the UI.
    """

    def __init__(
        self,
        rect: QRectF,
        translated_text: str = "",
        source_text: str = "",
        enabled: bool = True,
        font_family: str = DEFAULT_FONT_FAMILY,
        font_size: int | None = None,  # None -> auto-fit to the box
    ):
        super().__init__(rect)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self.region_id = None  # links detector output to this region across page flips
        self.source_box = None  # original detected rect {x,y,w,h}: where the source text really is
        self.source_text = source_text
        self.translated_text = translated_text
        self.translation_enabled = enabled
        self.font_family = font_family
        self.auto_fit = font_size is None
        self.font_size = font_size if font_size is not None else DEFAULT_FONT_SIZE
        self._resize_dir = None

        self.text_item = QGraphicsTextItem(self)
        self.text_item.setDefaultTextColor(QColor("black"))
        self._apply_font()
        self._layout_text()
        self._refresh_text()
        self._update_style()
        if self.auto_fit:
            self.fit_font_size()

    # --- text / enable state ------------------------------------------
    def set_translated_text(self, text: str):
        self.translated_text = text
        self._refresh_text()
        if self.auto_fit:
            self.fit_font_size()

    def set_enabled_state(self, enabled: bool):
        self.translation_enabled = enabled
        self._refresh_text()
        self._update_style()
        if enabled and self.auto_fit:
            self.fit_font_size()

    def set_font_family(self, family: str):
        self.font_family = family
        self._apply_font()
        if self.auto_fit:
            self.fit_font_size()

    def set_font_size(self, size: int):
        # explicit user choice turns auto-fit off for this region, no limits applied
        self.auto_fit = False
        self.font_size = size
        self._apply_font()

    def _apply_font(self):
        self.text_item.setFont(QFont(self.font_family, self.font_size))

    # --- auto-fit -------------------------------------------------------
    def fit_font_size(self):
        """Largest size in [MIN_FONT_SIZE, MAX_FONT_SIZE] whose wrapped text
        still fits the rect; never goes below the readability floor."""
        if not self.translated_text or not self.translation_enabled:
            return
        lo, hi, best = MIN_FONT_SIZE, MAX_FONT_SIZE, MIN_FONT_SIZE
        while lo <= hi:
            mid = (lo + hi) // 2
            if self._text_fits(mid):
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        self.font_size = best
        self._apply_font()
        self._notify_autofit()

    def _text_fits(self, size: int) -> bool:
        self.text_item.setFont(QFont(self.font_family, size))
        doc = self.text_item.document()
        return doc.size().height() <= self.rect().height()

    def _notify_autofit(self):
        scene = self.scene()
        if scene is not None and hasattr(scene, "region_autofit"):
            scene.region_autofit.emit(self)

    def _refresh_text(self):
        self.text_item.setPlainText(self.translated_text if self.translation_enabled else "")

    def _layout_text(self):
        r = self.rect()
        self.text_item.setPos(r.topLeft())
        self.text_item.setTextWidth(max(r.width(), 1))

    def _update_style(self):
        if self.translation_enabled:
            # dense background so the original text underneath doesn't show through
            self.setPen(QPen(QColor("#2ecc71"), 2, Qt.SolidLine))
            self.setBrush(QBrush(QColor(255, 255, 255, 235)))
        else:
            self.setPen(QPen(QColor("#95a5a6"), 2, Qt.DashLine))
            self.setBrush(QBrush(QColor(255, 255, 255, 30)))

    # --- geometry (resize by dragging edges/corners) -------------------
    def setRect(self, rect):
        super().setRect(rect)
        self._layout_text()
        if self.auto_fit:
            self.fit_font_size()

    def _handle_at(self, pos: QPointF):
        r = self.rect()
        left = abs(pos.x() - r.left()) < HANDLE_MARGIN
        right = abs(pos.x() - r.right()) < HANDLE_MARGIN
        top = abs(pos.y() - r.top()) < HANDLE_MARGIN
        bottom = abs(pos.y() - r.bottom()) < HANDLE_MARGIN
        if not r.adjusted(-HANDLE_MARGIN, -HANDLE_MARGIN, HANDLE_MARGIN, HANDLE_MARGIN).contains(pos):
            return None
        if left and top: return "tl"
        if right and top: return "tr"
        if left and bottom: return "bl"
        if right and bottom: return "br"
        if left: return "l"
        if right: return "r"
        if top: return "t"
        if bottom: return "b"
        return None

    def hoverMoveEvent(self, event):
        handle = self._handle_at(event.pos())
        self.setCursor(_CURSORS.get(handle, Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._resize_dir = self._handle_at(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_dir:
            r = self.rect()
            p = event.pos()
            if "l" in self._resize_dir: r.setLeft(p.x())
            if "r" in self._resize_dir: r.setRight(p.x())
            if "t" in self._resize_dir: r.setTop(p.y())
            if "b" in self._resize_dir: r.setBottom(p.y())
            r = r.normalized()
            if r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                self.prepareGeometryChange()
                self.setRect(r)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_dir = None
        super().mouseReleaseEvent(event)

    # --- (de)serialization for persisting edits between page switches --
    def to_dict(self):
        r = self.rect()
        pos = self.pos()
        return {
            "region_id": self.region_id,
            "source_box": self.source_box,
            "x": pos.x() + r.x(),
            "y": pos.y() + r.y(),
            "w": r.width(),
            "h": r.height(),
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "enabled": self.translation_enabled,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "auto_fit": self.auto_fit,
        }
