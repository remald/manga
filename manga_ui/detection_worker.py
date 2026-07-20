import queue
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import QThread, Signal

from .box_layout import region_center_in_bubble


def sort_reading_order(texts: list, page_height: int, rtl: bool = True) -> list:
    """Reading order: top-to-bottom in horizontal bands; right-to-left within
    a band for manga (rtl), left-to-right for western comics/webtoons.
    Approximate, but good enough for translation context."""
    band = max(1.0, page_height * 0.12)
    x_sign = -1 if rtl else 1
    return sorted(
        texts,
        key=lambda t: (int((t["y"] + t["h"] / 2) // band), x_sign * (t["x"] + t["w"] / 2)),
    )


class DetectionWorker(QThread):
    """Runs the page pipeline in a background thread: detection first (boxes
    show up immediately), then OCR + translation region by region."""

    # detect signals carry the pipeline generation: the GUI bumps it on folder
    # open / source-language switch and drops results of older generations.
    # region_translated results are keyed by region id, stale ids match nothing.
    page_detected = Signal(int, int, dict)  # generation, page index, detector result
    region_translated = Signal(int, str, str, str)  # page index, region id, source, translation
    page_done = Signal(int, int)  # generation, page index whose pipeline finished (even with errors)
    status_changed = Signal(str)

    def __init__(self, detector, ocr_reader, translator):
        super().__init__()
        self._detector = detector
        self._ocr = ocr_reader
        self._translator = translator
        self._queue = queue.Queue()

    def enqueue(self, page_index: int, image_path, generation: int = 0):
        self._queue.put(("detect", page_index, (str(image_path), generation)))

    def enqueue_retranslation(self, page_index: int, fragments):
        """fragments: list of (region_id, source_text) to run through the
        translator again (e.g. after a target-language switch)."""
        self._queue.put(("retranslate", page_index, fragments))

    def enqueue_region(self, page_index: int, image_path, region_id: str, box: dict):
        """OCR + translate a single manually drawn box {x,y,w,h}."""
        self._queue.put(("region", page_index, (str(image_path), region_id, box)))

    def process_page(self, page_index: int, image_path):
        """Synchronous detect+OCR+translate for CLI batch mode: runs in the
        caller's thread, results arrive through the same signals."""
        self._run_detection(page_index, str(image_path), 0)

    def clear_pending(self):
        """Drops queued tasks (the one already running finishes anyway);
        used when a source-language switch makes them obsolete."""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def stop(self):
        self._queue.put(None)

    def run(self):
        while True:
            task = self._queue.get()
            if task is None:
                break
            if task[0] == "detect":
                self._run_detection(task[1], *task[2])
            elif task[0] == "region":
                self._run_region(task[1], *task[2])
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

    def _run_region(self, index: int, path: str, region_id: str, box: dict):
        self.status_changed.emit(f"OCR нового фрагмента (стр. {index + 1})...")
        source = ""
        try:
            image = Image.open(path).convert("RGB")
            left = max(0, int(box["x"]))
            top = max(0, int(box["y"]))
            right = min(image.width, int(box["x"] + box["w"]))
            bottom = min(image.height, int(box["y"] + box["h"]))
            if right > left and bottom > top:
                source = self._ocr.read(image.crop((left, top, right, bottom)))
        except Exception as e:
            self.status_changed.emit(f"Ошибка OCR нового фрагмента (стр. {index + 1}): {e}")
            return
        if not source:
            # clear the placeholder so the box doesn't claim a pending translation
            self.region_translated.emit(index, region_id, "", "")
            self.status_changed.emit(f"Новый фрагмент (стр. {index + 1}): текст не распознан")
            return
        self.status_changed.emit(f"Перевод нового фрагмента (стр. {index + 1})...")
        translation = self._translate_fragments(index, [source])[0]
        self.region_translated.emit(index, region_id, source, translation)
        self.status_changed.emit("")

    def _run_detection(self, index: int, path: str, generation: int):
        try:
            self._run_detection_inner(index, path, generation)
        finally:
            self.page_done.emit(generation, index)

    def _run_detection_inner(self, index: int, path: str, generation: int):
        try:
            self.status_changed.emit(f"Детекция: страница {index + 1}...")
            result = self._detector.detect(path)
        except Exception as e:
            self.status_changed.emit(f"Ошибка детекции на странице {index + 1}: {e}")
            return

        image = Image.open(path).convert("RGB")
        rtl = getattr(self._ocr, "source_language", "Japanese") == "Japanese"
        ordered = sort_reading_order(result["texts"], image.height, rtl=rtl)
        # dialogue first, out-of-bubble text (SFX/signs) last, so it doesn't
        # break dialogue context in the numbered translation batch
        bubbles = result["bubbles"]
        result["texts"] = (
            [t for t in ordered if region_center_in_bubble(t, bubbles)]
            + [t for t in ordered if not region_center_in_bubble(t, bubbles)]
        )
        for det in result["texts"]:
            det["id"] = uuid4().hex
        self.page_detected.emit(generation, index, result)

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
        falls back to per-fragment calls if the model breaks the list.
        A single fragment has no cross-bubble context and the model tends to
        answer a one-item list without numbering, so it skips the batch."""
        if sum(1 for s in sources if s) > 1 and hasattr(self._translator, "translate_batch"):
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
