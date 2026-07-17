from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QToolBar, QSplitter, QListWidget,
    QListWidgetItem, QWidget, QVBoxLayout, QLabel, QMessageBox, QSizePolicy,
)

from .detection_worker import DetectionWorker
from .detector import MangaDetector
from .export_worker import ExportWorker
from .inpainter import LamaInpainter
from .ocr import MangaOcrReader
from .translator import MangaTranslator
from .page_scene import PageScene
from .page_view import PageView
from .sidebar import RegionEditorPanel

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PLACEHOLDER_TEXT = "Translation not ready"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Translator")
        self.resize(1400, 900)

        self.page_paths = []
        self.current_page = -1
        self.page_regions = {}  # page index -> list[dict], keeps edits when flipping pages
        self.page_detections = {}  # page index -> raw detector result {"texts": [...], "bubbles": [...]}
        self._detection_queued = set()  # page indices already sent to the worker

        self.scene = PageScene()
        self.view = PageView(self.scene)
        self.editor_panel = RegionEditorPanel()

        self.region_list = QListWidget()
        self.region_list.currentRowChanged.connect(self._on_region_list_row_changed)

        side_widget = QWidget()
        side_widget.setMinimumWidth(280)
        side_widget.setMaximumWidth(380)
        side_layout = QVBoxLayout(side_widget)
        side_layout.addWidget(QLabel("Фрагменты на странице:"))
        side_layout.addWidget(self.region_list, 1)
        side_layout.addWidget(self.editor_panel, 2)

        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(side_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1050, 350])
        self.setCentralWidget(self.splitter)

        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.scene.region_autofit.connect(self.editor_panel.sync_font_size)
        self.view.region_created.connect(self._on_region_created)
        self.editor_panel.region_updated.connect(self._refresh_region_list)

        self.page_label = QLabel("- / -")
        self._build_toolbar()
        self.statusBar()

        self.inpainter = LamaInpainter()
        self._export_worker = None
        self.detection_worker = DetectionWorker(MangaDetector(), MangaOcrReader(), MangaTranslator())
        self.detection_worker.page_detected.connect(self._on_page_detected)
        self.detection_worker.region_translated.connect(self._on_region_translated)
        self.detection_worker.status_changed.connect(self._on_detection_status)
        self.detection_worker.start()

    # --- toolbar ---------------------------------------------------------
    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        open_action = QAction("Открыть папку...", self)
        open_action.triggered.connect(self.open_folder)
        tb.addAction(open_action)
        tb.addSeparator()

        prev_action = QAction("< Пред.", self)
        prev_action.setShortcut(QKeySequence("Left"))
        prev_action.triggered.connect(self.prev_page)
        tb.addAction(prev_action)

        tb.addWidget(self.page_label)

        next_action = QAction("След. >", self)
        next_action.setShortcut(QKeySequence("Right"))
        next_action.triggered.connect(self.next_page)
        tb.addAction(next_action)
        tb.addSeparator()

        self.draw_action = QAction("Добавить рамку", self)
        self.draw_action.setCheckable(True)
        self.draw_action.toggled.connect(self.view.set_draw_mode)
        tb.addAction(self.draw_action)

        delete_action = QAction("Удалить рамку", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.delete_selected_region)
        tb.addAction(delete_action)
        tb.addSeparator()

        self.export_action = QAction("Экспорт страницы...", self)
        self.export_action.triggered.connect(self.export_current_page)
        tb.addAction(self.export_action)

    # --- folder / page navigation ----------------------------------------
    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку со страницами")
        if not folder:
            return
        paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if not paths:
            QMessageBox.warning(self, "Нет изображений", "В папке не найдено изображений.")
            return
        self.page_paths = paths
        self.page_regions = {}
        self.page_detections = {}
        self._detection_queued = set()
        self.current_page = -1
        self.load_page(0)

    def load_page(self, index: int):
        if not (0 <= index < len(self.page_paths)):
            return
        self._save_current_page_regions()

        self.current_page = index
        pixmap = QPixmap(str(self.page_paths[index]))
        self.scene.set_page_image(pixmap)

        for data in self.page_regions.get(index, []):
            self._add_region_from_dict(data)

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.page_label.setText(f"{index + 1} / {len(self.page_paths)}")
        self._refresh_region_list()

        if index not in self._detection_queued:
            self._detection_queued.add(index)
            self.detection_worker.enqueue(index, self.page_paths[index])

    def next_page(self):
        self.load_page(self.current_page + 1)

    def prev_page(self):
        self.load_page(self.current_page - 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene.pixmap_item is not None:
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def closeEvent(self, event):
        self.detection_worker.stop()
        self.detection_worker.wait(5000)
        if self._export_worker is not None:
            self._export_worker.wait(10000)
        super().closeEvent(event)

    # --- detection ---------------------------------------------------------
    def _on_page_detected(self, index: int, result: dict):
        self.page_detections[index] = result

        if index == self.current_page:
            for det in result["texts"]:
                rect = QRectF(det["x"], det["y"], det["w"], det["h"])
                item = self.scene.add_region(rect, translated_text=PLACEHOLDER_TEXT)
                item.region_id = det["id"]
            self._refresh_region_list()
        else:
            # page not on screen: stash regions as dicts, they materialize on load_page
            stored = self.page_regions.setdefault(index, [])
            for det in result["texts"]:
                stored.append({
                    "region_id": det["id"],
                    "x": det["x"], "y": det["y"], "w": det["w"], "h": det["h"],
                    "source_text": "", "translated_text": PLACEHOLDER_TEXT,
                    "enabled": True,
                })
        self.statusBar().showMessage(
            f"Страница {index + 1}: найдено текста — {len(result['texts'])}, "
            f"пузырьков — {len(result['bubbles'])}", 5000,
        )

    def _on_region_translated(self, index: int, region_id: str, source: str, translation: str):
        if index == self.current_page:
            for item in self.scene.regions:
                if item.region_id == region_id:
                    item.source_text = source
                    item.set_translated_text(translation)
                    if item.isSelected():
                        self.editor_panel.set_region(item)
                    self._refresh_region_list()
                    return
        # page not on screen (or region was deleted): update the stored dict
        for data in self.page_regions.get(index, []):
            if data.get("region_id") == region_id:
                data["source_text"] = source
                data["translated_text"] = translation
                return

    def _on_detection_status(self, message: str):
        if message:
            self.statusBar().showMessage(message)

    # --- export ------------------------------------------------------------
    def export_current_page(self):
        if self.current_page < 0:
            return
        src = self.page_paths[self.current_page]
        default = str(src.with_name(f"{src.stem}_translated.png"))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт страницы", default, "Изображения (*.png *.jpg *.webp)"
        )
        if not out_path:
            return
        regions = [r.to_dict() for r in self.scene.regions]
        bubbles = self.page_detections.get(self.current_page, {}).get("bubbles", [])
        self.export_action.setEnabled(False)
        self.statusBar().showMessage("Экспорт: вырезание текста и рендеринг...")
        self._export_worker = ExportWorker(src, regions, bubbles, self.inpainter, out_path)
        self._export_worker.finished_ok.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_done(self, path: str):
        self.export_action.setEnabled(True)
        self.statusBar().showMessage(f"Экспортировано: {path}", 8000)

    def _on_export_failed(self, error: str):
        self.export_action.setEnabled(True)
        self.statusBar().showMessage("")
        QMessageBox.warning(self, "Ошибка экспорта", error)

    # --- region <-> per-page storage --------------------------------------
    def _save_current_page_regions(self):
        if self.current_page < 0:
            return
        self.page_regions[self.current_page] = [r.to_dict() for r in self.scene.regions]

    def _add_region_from_dict(self, data):
        rect = QRectF(0, 0, data["w"], data["h"])
        item = self.scene.add_region(
            rect,
            translated_text=data["translated_text"],
            source_text=data["source_text"],
            enabled=data["enabled"],
            font_family=data.get("font_family", "Arial"),
            font_size=None if data.get("auto_fit", True) else data.get("font_size", 14),
        )
        item.region_id = data.get("region_id")
        item.setPos(data["x"], data["y"])

    # --- region editing ----------------------------------------------------
    def _on_region_created(self, rect):
        self.scene.add_region(rect, translated_text="", source_text="")
        self._refresh_region_list()
        self.draw_action.setChecked(False)

    def delete_selected_region(self):
        for item in list(self.scene.selectedItems()):
            self.scene.remove_region(item)
        self._refresh_region_list()

    def _refresh_region_list(self):
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for i, region in enumerate(self.scene.regions):
            label = region.translated_text.strip() or "(пусто)"
            self.region_list.addItem(QListWidgetItem(f"{i + 1}. {label[:30]}"))
        self.region_list.blockSignals(False)

    def _on_region_list_row_changed(self, row):
        if 0 <= row < len(self.scene.regions):
            item = self.scene.regions[row]
            self.scene.clearSelection()
            item.setSelected(True)

    def _on_selection_changed(self):
        selected = self.scene.selectedItems()
        region = selected[0] if selected else None
        self.editor_panel.set_region(region)
        if region in self.scene.regions:
            self.region_list.blockSignals(True)
            self.region_list.setCurrentRow(self.scene.regions.index(region))
            self.region_list.blockSignals(False)
