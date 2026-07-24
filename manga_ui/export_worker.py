from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .exporter import export_page
from .i18n import t


class ExportWorker(QThread):
    """One-shot: renders the translated page in the background and saves it."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, image_path, regions, bubbles, inpainter, out_path):
        super().__init__()
        self._image_path = str(image_path)
        self._regions = regions
        self._bubbles = bubbles
        self._inpainter = inpainter
        self._out_path = out_path

    def run(self):
        try:
            qimage = export_page(self._image_path, self._regions, self._bubbles, self._inpainter)
            if not qimage.save(self._out_path):
                raise RuntimeError(t("export_save_failed", path=self._out_path))
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(self._out_path)


class BatchExportWorker(QThread):
    """Exports every page of the folder into out_dir, reporting progress."""

    progress = Signal(int, int)  # pages done, total
    finished_ok = Signal(str)    # output directory
    failed = Signal(str)

    def __init__(self, jobs, inpainter, out_dir):
        """jobs: list of (image_path, regions, bubbles) in page order."""
        super().__init__()
        self._jobs = jobs
        self._inpainter = inpainter
        self._out_dir = Path(out_dir)

    def run(self):
        errors = []
        for i, (image_path, regions, bubbles) in enumerate(self._jobs):
            src = Path(image_path)
            try:
                qimage = export_page(str(src), regions, bubbles, self._inpainter)
                out = self._out_dir / f"{src.stem}_translated.png"
                if not qimage.save(str(out)):
                    raise RuntimeError(t("export_save_failed", path=out))
            except Exception as e:
                errors.append(f"{src.name}: {e}")
            self.progress.emit(i + 1, len(self._jobs))
        if errors:
            self.failed.emit(t("export_pages_failed") + "\n" + "\n".join(errors))
        else:
            self.finished_ok.emit(str(self._out_dir))
