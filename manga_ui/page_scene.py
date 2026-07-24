from PySide6.QtCore import Signal, QRectF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from .region_item import TextRegionItem, DEFAULT_FONT_FAMILY


class PageScene(QGraphicsScene):
    region_double_clicked = Signal(object)
    region_autofit = Signal(object)  # region whose font size was auto-fitted

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
        font_size=None,
        uppercase=True,
    ):
        item = TextRegionItem(
            rect, translated_text, source_text, enabled, font_family, font_size, uppercase
        )
        self.addItem(item)
        self.regions.append(item)
        if item.auto_fit:
            item.fit_font_size()  # first fit ran before the item had a scene
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
