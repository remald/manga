from PySide6.QtCore import Signal, QRectF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from .region_item import TextRegionItem, DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE


class PageScene(QGraphicsScene):
    region_double_clicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.pixmap_item = None
        self.regions = []

    def set_page_image(self, pixmap):
        self.clear()
        self.regions = []
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.addItem(self.pixmap_item)
        self.setSceneRect(QRectF(pixmap.rect()))

    def add_region(
        self,
        rect,
        translated_text="",
        source_text="",
        enabled=True,
        font_family=DEFAULT_FONT_FAMILY,
        font_size=DEFAULT_FONT_SIZE,
    ):
        item = TextRegionItem(rect, translated_text, source_text, enabled, font_family, font_size)
        self.addItem(item)
        self.regions.append(item)
        return item

    def remove_region(self, item):
        if item in self.regions:
            self.regions.remove(item)
        self.removeItem(item)

    def mouseDoubleClickEvent(self, event):
        views = self.views()
        transform = views[0].transform() if views else QTransform()
        item = self.itemAt(event.scenePos(), transform)
        if isinstance(item, TextRegionItem):
            self.region_double_clicked.emit(item)
        super().mouseDoubleClickEvent(event)
