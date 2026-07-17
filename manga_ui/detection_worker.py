import queue
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import QThread, Signal


class DetectionWorker(QThread):
    """Runs the page pipeline in a background thread: detection first (boxes
    show up immediately), then OCR + translation region by region."""

    page_detected = Signal(int, dict)  # page index, detector result
    region_translated = Signal(int, str, str, str)  # page index, region id, source, translation
    page_done = Signal(int)  # page index whose full pipeline finished (even with errors)
    status_changed = Signal(str)

    def __init__(self, detector, ocr_reader, translator):
        super().__init__()
        self._detector = detector
        self._ocr = ocr_reader
        self._translator = translator
        self._queue = queue.Queue()

    def enqueue(self, page_index: int, image_path):
        self._queue.put(("detect", page_index, str(image_path)))

    def enqueue_retranslation(self, page_index: int, fragments):
        """fragments: list of (region_id, source_text) to run through the
        translator again (e.g. after a target-language switch)."""
        self._queue.put(("retranslate", page_index, fragments))

    def stop(self):
        self._queue.put(None)

    def run(self):
        while True:
            task = self._queue.get()
            if task is None:
                break
            if task[0] == "detect":
                self._run_detection(task[1], task[2])
            else:
                self._run_retranslation(task[1], task[2])

    def _run_retranslation(self, index: int, fragments):
        for i, (region_id, source) in enumerate(fragments):
            try:
                self.status_changed.emit(
                    f"Повторный перевод: страница {index + 1}, фрагмент {i + 1}/{len(fragments)}..."
                )
                translation = self._translator.translate(source)
            except Exception as e:
                self.status_changed.emit(f"Ошибка перевода (стр. {index + 1}, фрагмент {i + 1}): {e}")
                continue
            self.region_translated.emit(index, region_id, source, translation)
        self.status_changed.emit("")

    def _run_detection(self, index: int, path: str):
        try:
            self._run_detection_inner(index, path)
        finally:
            self.page_done.emit(index)

    def _run_detection_inner(self, index: int, path: str):
        try:
            self.status_changed.emit(f"Детекция: страница {index + 1}...")
            result = self._detector.detect(path)
        except Exception as e:
            self.status_changed.emit(f"Ошибка детекции на странице {index + 1}: {e}")
            return

        for det in result["texts"]:
            det["id"] = uuid4().hex
        self.page_detected.emit(index, result)

        texts = result["texts"]
        if texts:
            image = Image.open(path).convert("RGB")
            for i, det in enumerate(texts):
                try:
                    self.status_changed.emit(
                        f"OCR + перевод: страница {index + 1}, фрагмент {i + 1}/{len(texts)}..."
                    )
                    crop = image.crop((
                        int(det["x"]), int(det["y"]),
                        int(det["x"] + det["w"]), int(det["y"] + det["h"]),
                    ))
                    source = self._ocr.read(crop)
                    translation = self._translator.translate(source)
                except Exception as e:
                    self.status_changed.emit(
                        f"Ошибка OCR/перевода (стр. {index + 1}, фрагмент {i + 1}): {e}"
                    )
                    continue
                self.region_translated.emit(index, det["id"], source, translation)
        self.status_changed.emit("")
