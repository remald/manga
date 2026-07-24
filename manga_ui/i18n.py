"""Minimal in-app i18n: a current-language global and a t(key, **kwargs)
lookup. English is the fallback for any missing key. Language names for the
source/target dropdowns are localized separately via lang_name()."""

UI_LANGUAGES = [("en", "English"), ("ru", "Русский")]

_current = "en"

_STRINGS = {
    "en": {
        # toolbar
        "open_folder": "Open folder...",
        "prev_page": "< Prev",
        "next_page": "Next >",
        "add_box": "Add box",
        "delete_box": "Delete box",
        "export_page": "Export page...",
        "export_all": "Export all...",
        "source_label": " Source: ",
        "target_label": " Target: ",
        "ui_label": " UI: ",
        "retranslate": "Retranslate",
        # sidebar
        "fragments_header": "Fragments on page:",
        "original_label": "Original:",
        "translation_label": "Translation:",
        "font_label": "Font:",
        "size_label": "Size:",
        "enabled_checkbox": "Translation enabled for this fragment",
        "uppercase_checkbox": "UPPERCASE",
        "empty_region": "(empty)",
        # dialogs
        "choose_folder_title": "Choose the folder with pages",
        "no_images_title": "No images",
        "no_images_body": "No images found in the folder.",
        "export_page_title": "Export page",
        "export_dir_title": "Export folder",
        "images_filter": "Images (*.png *.jpg *.webp)",
        "export_error_title": "Export error",
        # status bar
        "status_detected": "Page {page}: text found — {texts}, bubbles — {bubbles}",
        "status_nothing_to_translate": "Nothing to translate: no fragments with recognized text on the page",
        "status_source_changed": "Source language: {lang}. Pages are being re-recognized.",
        "status_waiting_page_export": "Waiting for page {page} to finish before export...",
        "status_export_rendering": "Export: erasing text and rendering...",
        "status_waiting_pages": "Waiting for pages: {done} / {total}...",
        "status_export_all": "Exporting all pages...",
        "status_export_progress": "Export: page {done} / {total}",
        "status_exported": "Exported: {path}",
        # worker
        "worker_retranslating": "Re-translating page {page}...",
        "worker_ocr_new": "OCR of new fragment (page {page})...",
        "worker_ocr_new_error": "OCR error for new fragment (page {page}): {error}",
        "worker_new_not_recognized": "New fragment (page {page}): text not recognized",
        "worker_translate_new": "Translating new fragment (page {page})...",
        "worker_detecting": "Detection: page {page}...",
        "worker_detect_error": "Detection error on page {page}: {error}",
        "worker_ocr": "OCR: page {page}, fragment {i}/{n}...",
        "worker_ocr_error": "OCR error (page {page}, fragment {i}): {error}",
        "worker_translating_page": "Translating page {page}...",
        "worker_batch_unparsed": "Page {page}: batch translation not parsed, translating per fragment...",
        "worker_batch_error": "Batch translation error (page {page}): {error}",
        "worker_translate_error": "Translation error (page {page}): {error}",
        # export worker
        "export_save_failed": "failed to save {path}",
        "export_pages_failed": "Pages not exported:",
    },
    "ru": {
        "open_folder": "Открыть папку...",
        "prev_page": "< Пред.",
        "next_page": "След. >",
        "add_box": "Добавить рамку",
        "delete_box": "Удалить рамку",
        "export_page": "Экспорт страницы...",
        "export_all": "Экспортировать все...",
        "source_label": " Оригинал: ",
        "target_label": " Перевод: ",
        "ui_label": " Интерфейс: ",
        "retranslate": "Перевести заново",
        "fragments_header": "Фрагменты на странице:",
        "original_label": "Оригинал:",
        "translation_label": "Перевод:",
        "font_label": "Шрифт:",
        "size_label": "Размер:",
        "enabled_checkbox": "Перевод включён для этого фрагмента",
        "uppercase_checkbox": "ВЕРХНИЙ РЕГИСТР",
        "empty_region": "(пусто)",
        "choose_folder_title": "Выберите папку со страницами",
        "no_images_title": "Нет изображений",
        "no_images_body": "В папке не найдено изображений.",
        "export_page_title": "Экспорт страницы",
        "export_dir_title": "Папка для экспорта",
        "images_filter": "Изображения (*.png *.jpg *.webp)",
        "export_error_title": "Ошибка экспорта",
        "status_detected": "Страница {page}: найдено текста — {texts}, пузырьков — {bubbles}",
        "status_nothing_to_translate": "Нечего переводить: на странице нет фрагментов с распознанным текстом",
        "status_source_changed": "Исходный язык: {lang}. Страницы распознаются заново.",
        "status_waiting_page_export": "Ожидание обработки страницы {page} перед экспортом...",
        "status_export_rendering": "Экспорт: вырезание текста и рендеринг...",
        "status_waiting_pages": "Ожидание обработки страниц: {done} / {total}...",
        "status_export_all": "Экспорт всех страниц...",
        "status_export_progress": "Экспорт: страница {done} / {total}",
        "status_exported": "Экспортировано: {path}",
        "worker_retranslating": "Повторный перевод страницы {page}...",
        "worker_ocr_new": "OCR нового фрагмента (стр. {page})...",
        "worker_ocr_new_error": "Ошибка OCR нового фрагмента (стр. {page}): {error}",
        "worker_new_not_recognized": "Новый фрагмент (стр. {page}): текст не распознан",
        "worker_translate_new": "Перевод нового фрагмента (стр. {page})...",
        "worker_detecting": "Детекция: страница {page}...",
        "worker_detect_error": "Ошибка детекции на странице {page}: {error}",
        "worker_ocr": "OCR: страница {page}, фрагмент {i}/{n}...",
        "worker_ocr_error": "Ошибка OCR (стр. {page}, фрагмент {i}): {error}",
        "worker_translating_page": "Перевод страницы {page}...",
        "worker_batch_unparsed": "Страница {page}: батч-перевод не разобран, перевожу по фрагментам...",
        "worker_batch_error": "Ошибка батч-перевода (стр. {page}): {error}",
        "worker_translate_error": "Ошибка перевода (стр. {page}): {error}",
        "export_save_failed": "не удалось сохранить {path}",
        "export_pages_failed": "Не экспортированы страницы:",
    },
}

# canonical language name (used internally) -> localized display name
_LANG_NAMES = {
    "en": {
        "Japanese": "Japanese", "English": "English", "Chinese": "Chinese",
        "Korean": "Korean", "Spanish": "Spanish", "French": "French",
        "German": "German", "Portuguese": "Portuguese", "Italian": "Italian",
        "Russian": "Russian", "Turkish": "Turkish",
    },
    "ru": {
        "Japanese": "Японский", "English": "Английский", "Chinese": "Китайский",
        "Korean": "Корейский", "Spanish": "Испанский", "French": "Французский",
        "German": "Немецкий", "Portuguese": "Португальский", "Italian": "Итальянский",
        "Russian": "Русский", "Turkish": "Турецкий",
    },
}


def set_language(lang: str):
    global _current
    if lang in _STRINGS:
        _current = lang


def get_language() -> str:
    return _current


def default_language() -> str:
    """System locale if we translate it, English otherwise."""
    try:
        from PySide6.QtCore import QLocale
        return "ru" if QLocale.system().name().startswith("ru") else "en"
    except Exception:
        return "en"


def t(key: str, **kwargs) -> str:
    s = _STRINGS.get(_current, {}).get(key) or _STRINGS["en"].get(key, key)
    return s.format(**kwargs) if kwargs else s


def lang_name(canonical: str) -> str:
    return _LANG_NAMES.get(_current, {}).get(canonical, canonical)
