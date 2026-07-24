from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QToolBar, QSplitter, QListWidget,
    QListWidgetItem, QWidget, QVBoxLayout, QLabel, QMessageBox, QSizePolicy,
    QComboBox, QProgressBar,
)

from .appfonts import load_bundled_fonts
from .box_layout import widen_boxes_in_bubbles
from .detection_worker import DetectionWorker
from .detector import MangaDetector
from .export_worker import ExportWorker, BatchExportWorker
from .inpainter import LamaInpainter
from .ocr import OcrRouter
from .translator import MangaTranslator
from .page_scene import PageScene
from .page_view import PageView
from .sidebar import RegionEditorPanel

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PLACEHOLDER_TEXT = "Translation not ready"

# hieroglyphic targets read fine in narrow vertical boxes — skip widening
CJK_TARGETS = {"Chinese"}

# display label -> full English name; keys must exist in ocr.EASYOCR_CODES
# (except Japanese, which goes through Manga OCR)
SOURCE_LANGUAGES = {
    "Японский": "Japanese",
    "Английский": "English",
    "Китайский": "Chinese",
    "Корейский": "Korean",
    "Испанский": "Spanish",
    "Французский": "French",
    "Немецкий": "German",
    "Португальский": "Portuguese",
    "Итальянский": "Italian",
    "Русский": "Russian",
}

# display label -> full English name for the HY-MT prompt
TARGET_LANGUAGES = {
    "Русский": "Russian",
    "Английский": "English",
    "Китайский": "Chinese",
    "Корейский": "Korean",
    "Испанский": "Spanish",
    "Французский": "French",
    "Немецкий": "German",
    "Португальский": "Portuguese",
    "Итальянский": "Italian",
    "Турецкий": "Turkish",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        load_bundled_fonts()  # register the bundled comic font before any region renders
        self.setWindowTitle("Manga Translator")
        self.resize(1400, 900)

        self.page_paths = []
        self.current_page = -1
        self.page_regions = {}  # page index -> list[dict], keeps edits when flipping pages
        self.page_detections = {}  # page index -> raw detector result {"texts": [...], "bubbles": [...]}
        self._detection_queued = set()  # page indices already sent to the worker
        self._pages_done = set()  # pages whose detect+OCR+translate pipeline finished
        self._pipeline_gen = 0  # bumped on folder open / source-language switch; stale worker results are dropped
        self._pending_export_dir = None  # batch export waiting for the pipeline
        self._pending_single_export = None  # (page index, out path) waiting for the pipeline

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
        self.export_progress = QProgressBar()
        self.export_progress.setMaximumWidth(220)
        self.export_progress.hide()
        self.statusBar().addPermanentWidget(self.export_progress)

        self.inpainter = LamaInpainter()
        self._export_worker = None
        self.translator = MangaTranslator()
        self.ocr = OcrRouter()
        self.detection_worker = DetectionWorker(MangaDetector(), self.ocr, self.translator)
        self.detection_worker.page_detected.connect(self._on_page_detected)
        self.detection_worker.region_translated.connect(self._on_region_translated)
        self.detection_worker.page_done.connect(self._on_page_pipeline_done)
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

        self.export_all_action = QAction("Экспортировать все...", self)
        self.export_all_action.triggered.connect(self.export_all_pages)
        tb.addAction(self.export_all_action)
        tb.addSeparator()

        tb.addWidget(QLabel(" Оригинал: "))
        self.source_language_combo = QComboBox()
        self.source_language_combo.addItems(SOURCE_LANGUAGES.keys())
        self.source_language_combo.currentTextChanged.connect(self._on_source_language_changed)
        tb.addWidget(self.source_language_combo)

        tb.addWidget(QLabel(" Перевод: "))
        self.language_combo = QComboBox()
        self.language_combo.addItems(TARGET_LANGUAGES.keys())
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        tb.addWidget(self.language_combo)

        retranslate_action = QAction("Перевести заново", self)
        retranslate_action.triggered.connect(self.retranslate_current_page)
        tb.addAction(retranslate_action)

    # --- folder / page navigation ----------------------------------------
    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку со страницами")
        if not folder:
            return
        paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if not paths:
            QMessageBox.warning(self, "Нет изображений", "В папке не найдено изображений.")
            return
        self.detection_worker.clear_pending()
        self._pipeline_gen += 1
        self.page_paths = paths
        self.page_regions = {}
        self.page_detections = {}
        self._detection_queued = set()
        self._pages_done = set()
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
            self.detection_worker.enqueue(index, self.page_paths[index], self._pipeline_gen)

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
    def _on_page_detected(self, generation: int, index: int, result: dict):
        if generation != self._pipeline_gen:
            return  # task from before a folder open / source-language switch
        self.page_detections[index] = result

        # widen copies only: the worker still crops OCR from the original boxes
        originals = result["texts"]
        texts = originals
        if self.translator.target_language not in CJK_TARGETS:
            texts = widen_boxes_in_bubbles(originals, result["bubbles"])

        if index == self.current_page:
            for orig, det in zip(originals, texts):
                rect = QRectF(det["x"], det["y"], det["w"], det["h"])
                item = self.scene.add_region(rect, translated_text=PLACEHOLDER_TEXT)
                item.region_id = det["id"]
                item.source_box = {k: orig[k] for k in ("x", "y", "w", "h")}
            self._refresh_region_list()
        else:
            # page not on screen: stash regions as dicts, they materialize on load_page
            stored = self.page_regions.setdefault(index, [])
            for orig, det in zip(originals, texts):
                stored.append({
                    "region_id": det["id"],
                    "source_box": {k: orig[k] for k in ("x", "y", "w", "h")},
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

    def retranslate_current_page(self):
        """Re-runs translation for the current page from the stored OCR
        sources (no detection/OCR pass), e.g. after a language switch."""
        if self.current_page < 0:
            return
        fragments = [
            (r.region_id, r.source_text)
            for r in self.scene.regions
            if r.region_id and r.source_text.strip()
        ]
        if not fragments:
            self.statusBar().showMessage(
                "Нечего переводить: на странице нет фрагментов с распознанным текстом", 5000
            )
            return
        self.detection_worker.enqueue_retranslation(self.current_page, fragments)

    def _on_source_language_changed(self, label: str):
        lang = SOURCE_LANGUAGES[label]
        self.ocr.source_language = lang
        self.translator.source_language = lang
        if not self.page_paths:
            return
        # everything OCR'd so far is in the wrong language: drop queued work
        # and stored results, reprocess pages as they are visited
        self.detection_worker.clear_pending()
        self._pipeline_gen += 1
        self.page_regions = {}
        self.page_detections = {}
        self._detection_queued = set()
        self._pages_done = set()
        current = self.current_page
        self.current_page = -1  # load_page must not save the stale regions
        self.load_page(current)
        self.statusBar().showMessage(
            f"Исходный язык: {label}. Страницы распознаются заново.", 5000
        )

    def _on_language_changed(self, label: str):
        # a plain str assignment is atomic, safe to do while the worker runs;
        # applies to fragments translated from now on
        self.translator.target_language = TARGET_LANGUAGES[label]

    def _on_detection_status(self, message: str):
        if message:
            self.statusBar().showMessage(message)

    # --- export ------------------------------------------------------------
    def _set_export_running(self, running: bool, determinate_total: int | None = None):
        self.export_action.setEnabled(not running)
        self.export_all_action.setEnabled(not running)
        if running:
            if determinate_total:
                self.export_progress.setRange(0, determinate_total)
                self.export_progress.setValue(0)
            else:
                self.export_progress.setRange(0, 0)  # busy indicator
            self.export_progress.show()
        else:
            self.export_progress.hide()

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
        if self.current_page not in self._pages_done:
            # page is still in the pipeline: export starts when it finishes
            self._pending_single_export = (self.current_page, out_path)
            self._set_export_running(True)
            self.statusBar().showMessage(
                f"Ожидание обработки страницы {self.current_page + 1} перед экспортом..."
            )
            return
        self._start_single_export(self.current_page, out_path)

    def _start_single_export(self, index: int, out_path: str):
        if index == self.current_page:
            regions = [r.to_dict() for r in self.scene.regions]
        else:
            regions = self.page_regions.get(index, [])
        bubbles = self.page_detections.get(index, {}).get("bubbles", [])
        self._set_export_running(True)
        self.statusBar().showMessage("Экспорт: вырезание текста и рендеринг...")
        self._export_worker = ExportWorker(
            self.page_paths[index], regions, bubbles, self.inpainter, out_path
        )
        self._export_worker.finished_ok.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def export_all_pages(self):
        if not self.page_paths:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для экспорта")
        if not out_dir:
            return
        pending = [i for i in range(len(self.page_paths)) if i not in self._pages_done]
        if pending:
            # finish the pipeline over every unprocessed page first
            for i in pending:
                if i not in self._detection_queued:
                    self._detection_queued.add(i)
                    self.detection_worker.enqueue(i, self.page_paths[i], self._pipeline_gen)
            self._pending_export_dir = out_dir
            self._set_export_running(True, determinate_total=len(self.page_paths))
            self.export_progress.setValue(len(self._pages_done))
            self.statusBar().showMessage(
                f"Ожидание обработки страниц: {len(self._pages_done)} / {len(self.page_paths)}..."
            )
        else:
            self._start_batch_export(out_dir)

    def _on_page_pipeline_done(self, generation: int, index: int):
        if generation != self._pipeline_gen:
            return
        self._pages_done.add(index)
        if self._pending_single_export is not None and self._pending_single_export[0] == index:
            _, out_path = self._pending_single_export
            self._pending_single_export = None
            self._start_single_export(index, out_path)
            return
        if self._pending_export_dir is None:
            return
        done = len([i for i in self._pages_done if i < len(self.page_paths)])
        self.export_progress.setValue(done)
        self.statusBar().showMessage(
            f"Ожидание обработки страниц: {done} / {len(self.page_paths)}..."
        )
        if done >= len(self.page_paths):
            out_dir = self._pending_export_dir
            self._pending_export_dir = None
            self._start_batch_export(out_dir)

    def _start_batch_export(self, out_dir: str):
        self._save_current_page_regions()
        jobs = []
        for i, path in enumerate(self.page_paths):
            if i == self.current_page:
                regions = [r.to_dict() for r in self.scene.regions]
            else:
                regions = self.page_regions.get(i, [])
            bubbles = self.page_detections.get(i, {}).get("bubbles", [])
            jobs.append((path, regions, bubbles))
        self._set_export_running(True, determinate_total=len(jobs))
        self.statusBar().showMessage("Экспорт всех страниц...")
        self._export_worker = BatchExportWorker(jobs, self.inpainter, out_dir)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished_ok.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_progress(self, done: int, total: int):
        self.export_progress.setRange(0, total)
        self.export_progress.setValue(done)
        self.statusBar().showMessage(f"Экспорт: страница {done} / {total}")

    def _on_export_done(self, path: str):
        self._set_export_running(False)
        self.statusBar().showMessage(f"Экспортировано: {path}", 8000)

    def _on_export_failed(self, error: str):
        self._set_export_running(False)
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
        item.source_box = data.get("source_box")
        item.setPos(data["x"], data["y"])

    # --- region editing ----------------------------------------------------
    def _on_region_created(self, rect):
        item = self.scene.add_region(rect, translated_text=PLACEHOLDER_TEXT, source_text="")
        self._refresh_region_list()
        self.draw_action.setChecked(False)
        if self.current_page < 0:
            return
        item.region_id = uuid4().hex
        item.source_box = {"x": rect.x(), "y": rect.y(), "w": rect.width(), "h": rect.height()}
        self.detection_worker.enqueue_region(
            self.current_page, self.page_paths[self.current_page],
            item.region_id, item.source_box,
        )

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
