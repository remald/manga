from PySide6.QtCore import QThread, Signal

from .exporter import export_page


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
                raise RuntimeError(f"не удалось сохранить {self._out_path}")
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(self._out_path)
