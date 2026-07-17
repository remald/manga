class MangaOcrReader:
    """Wrapper around manga-ocr (TrOCR fine-tuned on manga). Lazy-loaded;
    call only from the worker thread."""

    def __init__(self):
        self._mocr = None

    def _ensure_loaded(self):
        if self._mocr is None:
            from manga_ocr import MangaOcr
            self._mocr = MangaOcr()

    def read(self, pil_image) -> str:
        self._ensure_loaded()
        return self._mocr(pil_image)
