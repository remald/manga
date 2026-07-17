import queue
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import QThread, Signal


class DetectionWorker(QThread):
    """Runs the page pipeline in a background thread: detection first (boxes
    show up immediately), then OCR + translation region by region."""

    page_detected = Signal(int, dict)  # page index, detector result
    region_translated = Signal(int, str, str, str)  # page index, region id, source, translation
    status_changed = Signal(str)

    def __init__(self, detector, ocr_reader, translator):
        super().__init__()
        self._detector = detector
        self._ocr = ocr_reader
        self._translator = translator
        self._queue = queue.Queue()

    def enqueue(self, page_index: int, image_path):
        self._queue.put((page_index, str(image_path)))

    def stop(self):
        self._queue.put(None)

    def run(self):
        while True:
            task = self._queue.get()
            if task is None:
                break
            index, path = task
            try:
                self.status_changed.emit(f"Детекция: страница {index + 1}...")
                result = self._detector.detect(path)
            except Exception as e:
                self.status_changed.emit(f"Ошибка детекции на странице {index + 1}: {e}")
                continue

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
