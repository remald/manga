"""Headless batch mode: the full pipeline over a folder in one run."""
from pathlib import Path

from .box_layout import widen_boxes_in_bubbles
from .detection_worker import DetectionWorker
from .detector import MangaDetector
from .exporter import export_page
from .inpainter import LamaInpainter
from .main_window import CJK_TARGETS, IMAGE_EXTS
from .ocr import OcrRouter
from .translator import MangaTranslator


def translate_folder(
    input_dir,
    output_dir,
    source_language: str = "Japanese",
    target_language: str = "Russian",
    log=print,
) -> list[str]:
    """Detect -> OCR -> translate -> inpaint+render for every image in
    input_dir, saving <name>_translated.png into output_dir. Returns per-page
    error strings (empty when everything exported). Needs a QGuiApplication:
    the renderer uses Qt fonts."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    paths = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not paths:
        raise ValueError(f"в папке нет изображений: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    translator = MangaTranslator(
        target_language=target_language, source_language=source_language
    )
    ocr = OcrRouter()
    ocr.source_language = source_language
    # used as a synchronous engine: the thread never starts, signals are
    # direct connections into the dicts below
    worker = DetectionWorker(MangaDetector(), ocr, translator)
    inpainter = LamaInpainter()

    detections = {}
    translations = {}
    worker.page_detected.connect(lambda gen, idx, res: detections.update({idx: res}))
    worker.region_translated.connect(lambda idx, rid, src, tr: translations.update({rid: tr}))
    worker.status_changed.connect(lambda m: log(f"  {m}") if m else None)

    errors = []
    for i, path in enumerate(paths):
        log(f"[{i + 1}/{len(paths)}] {path.name}")
        try:
            worker.process_page(i, path)
            result = detections.pop(i, {"texts": [], "bubbles": []})
            originals = result["texts"]
            widened = originals
            if target_language not in CJK_TARGETS:
                widened = widen_boxes_in_bubbles(originals, result["bubbles"])
            regions = [
                {
                    "source_box": {k: orig[k] for k in ("x", "y", "w", "h")},
                    "x": det["x"], "y": det["y"], "w": det["w"], "h": det["h"],
                    "translated_text": translations.pop(det["id"], ""),
                    "enabled": True,
                }
                for orig, det in zip(originals, widened)
            ]
            qimage = export_page(str(path), regions, result["bubbles"], inpainter)
            out = output_dir / f"{path.stem}_translated.png"
            if not qimage.save(str(out)):
                raise RuntimeError(f"не удалось сохранить {out}")
            log(f"  -> {out}")
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            log(f"  ошибка: {e}")
    return errors
