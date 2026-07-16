from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsView, QGraphicsRectItem


class PageView(QGraphicsView):
    """Displays the current page and, in draw mode, lets the user drag out
    a new text-region rectangle by hand (stand-in for detection-model output)."""

    region_created = Signal(QRectF)

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.draw_mode = False
        self._draw_start = None
        self._draw_rect_item = None

    def set_draw_mode(self, enabled: bool):
        self.draw_mode = enabled
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.RubberBandDrag)

    def mousePressEvent(self, event):
        if self.draw_mode and event.button() == Qt.LeftButton:
            self._draw_start = self.mapToScene(event.pos())
            self._draw_rect_item = QGraphicsRectItem(QRectF(self._draw_start, self._draw_start))
            self._draw_rect_item.setPen(QPen(QColor("#3498db"), 2, Qt.DashLine))
            self.scene().addItem(self._draw_rect_item)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.draw_mode and self._draw_rect_item is not None:
            current = self.mapToScene(event.pos())
            self._draw_rect_item.setRect(QRectF(self._draw_start, current).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.draw_mode and self._draw_rect_item is not None:
            rect = self._draw_rect_item.rect()
            self.scene().removeItem(self._draw_rect_item)
            self._draw_rect_item = None
            if rect.width() > 5 and rect.height() > 5:
                self.region_created.emit(rect)
            return
        super().mouseReleaseEvent(event)
