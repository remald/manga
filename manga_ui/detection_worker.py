import queue
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import QThread, Signal

from .box_layout import region_center_in_bubble


def sort_reading_order(texts: list, page_height: int) -> list:
    """Manga reading order: top-to-bottom in horizontal bands, right-to-left
    within a band. Approximate, but good enough for translation context."""
    band = max(1.0, page_height * 0.12)
    return sorted(
        texts,
        key=lambda t: (int((t["y"] + t["h"] / 2) // band), -(t["x"] + t["w"] / 2)),
    )


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
        self.status_changed.emit(f"Повторный перевод страницы {index + 1}...")
        sources = [source for _, source in fragments]
        translations = self._translate_fragments(index, sources)
        for (region_id, source), translation in zip(fragments, translations):
            if source and translation:
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

        image = Image.open(path).convert("RGB")
        ordered = sort_reading_order(result["texts"], image.height)
        # dialogue first, out-of-bubble text (SFX/signs) last, so it doesn't
        # break dialogue context in the numbered translation batch
        bubbles = result["bubbles"]
        result["texts"] = (
            [t for t in ordered if region_center_in_bubble(t, bubbles)]
            + [t for t in ordered if not region_center_in_bubble(t, bubbles)]
        )
        for det in result["texts"]:
            det["id"] = uuid4().hex
        self.page_detected.emit(index, result)

        texts = result["texts"]
        if not texts:
            self.status_changed.emit("")
            return

        sources = [""] * len(texts)
        for i, det in enumerate(texts):
            try:
                self.status_changed.emit(
                    f"OCR: страница {index + 1}, фрагмент {i + 1}/{len(texts)}..."
                )
                crop = image.crop((
                    int(det["x"]), int(det["y"]),
                    int(det["x"] + det["w"]), int(det["y"] + det["h"]),
                ))
                sources[i] = self._ocr.read(crop)
            except Exception as e:
                self.status_changed.emit(f"Ошибка OCR (стр. {index + 1}, фрагмент {i + 1}): {e}")

        self.status_changed.emit(f"Перевод страницы {index + 1}...")
        translations = self._translate_fragments(index, sources)
        for det, source, translation in zip(texts, sources, translations):
            if source:
                self.region_translated.emit(index, det["id"], source, translation)
        self.status_changed.emit("")

    def _translate_fragments(self, index: int, sources: list) -> list:
        """One numbered-list call for the whole page (cross-bubble context);
        falls back to per-fragment calls if the model breaks the list."""
        if hasattr(self._translator, "translate_batch"):
            try:
                result = self._translator.translate_batch(sources)
                if result is not None:
                    return result
                self.status_changed.emit(
                    f"Страница {index + 1}: батч-перевод не разобран, перевожу по фрагментам..."
                )
            except Exception as e:
                self.status_changed.emit(f"Ошибка батч-перевода (стр. {index + 1}): {e}")
        translations = []
        for source in sources:
            try:
                translations.append(self._translator.translate(source) if source else "")
            except Exception as e:
                self.status_changed.emit(f"Ошибка перевода (стр. {index + 1}): {e}")
                translations.append("")
        return translations
