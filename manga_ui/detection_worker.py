import queue

from PySide6.QtCore import QThread, Signal


class DetectionWorker(QThread):
    """Runs MangaDetector in a background thread so page flips don't freeze
    the UI. Pages are processed one at a time in enqueue order."""

    page_detected = Signal(int, dict)  # page index, detector result
    status_changed = Signal(str)

    def __init__(self, detector):
        super().__init__()
        self._detector = detector
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
            self.page_detected.emit(index, result)
            self.status_changed.emit("")
