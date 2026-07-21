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


# EasyOCR language codes per source language; CJK models ship paired with English
EASYOCR_CODES = {
    "English": ["en"],
    "Chinese": ["ch_sim", "en"],
    "Korean": ["ko", "en"],
    "Spanish": ["es"],
    "French": ["fr"],
    "German": ["de"],
    "Portuguese": ["pt"],
    "Italian": ["it"],
    "Russian": ["ru", "en"],
}


class EasyOcrReader:
    """EasyOCR for non-Japanese sources. Lazy-loaded (downloads models on
    first use); call only from the worker thread."""

    def __init__(self, lang_codes: list):
        self._lang_codes = lang_codes
        self._reader = None

    def _ensure_loaded(self):
        if self._reader is None:
            import easyocr
            # gpu=True asks for CUDA/MPS but easyocr falls back to CPU itself
            # when neither is available, so this is safe on CPU-only machines
            self._reader = easyocr.Reader(self._lang_codes, gpu=True, verbose=False)

    def read(self, pil_image) -> str:
        self._ensure_loaded()
        import numpy as np
        lines = self._reader.readtext(np.array(pil_image), detail=0, paragraph=True)
        return " ".join(lines).strip()


class OcrRouter:
    """Dispatches to the OCR engine for the current source language:
    Manga OCR for Japanese, EasyOCR for everything else. `source_language`
    is assigned from the GUI thread (atomic), readers load lazily in the
    worker thread and are cached per language."""

    def __init__(self):
        self.source_language = "Japanese"
        self._manga = MangaOcrReader()
        self._easy = {}

    def read(self, pil_image) -> str:
        lang = self.source_language
        if lang == "Japanese":
            return self._manga.read(pil_image)
        reader = self._easy.get(lang)
        if reader is None:
            reader = self._easy[lang] = EasyOcrReader(EASYOCR_CODES[lang])
        return reader.read(pil_image)
