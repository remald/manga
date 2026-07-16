from pathlib import Path

from PIL import Image

MODEL_PATH = Path(__file__).parent / "models" / "checkpoint_best_ema.pth"
DEFAULT_THRESHOLD = 0.5


class MangaDetector:
    """RF-DETR Medium fine-tuned on two classes: 'bubble' and 'text'.

    The model is loaded lazily on first detect() call so app startup stays
    instant; call detect() only from a single worker thread.
    """

    def __init__(self, model_path=MODEL_PATH, threshold=DEFAULT_THRESHOLD):
        self.model_path = str(model_path)
        self.threshold = threshold
        self._model = None
        self._class_names = None

    def _ensure_loaded(self):
        if self._model is None:
            from rfdetr import RFDETRMedium
            self._model = RFDETRMedium(pretrain_weights=self.model_path)
            # for fine-tuned rfdetr models class_id is a 0-based index into class_names
            self._class_names = list(self._model.class_names)

    def detect(self, image_path) -> dict:
        """Returns {"texts": [...], "bubbles": [...]}, each entry:
        {"x", "y", "w", "h", "confidence"} in image pixel coordinates."""
        self._ensure_loaded()
        image = Image.open(image_path).convert("RGB")
        dets = self._model.predict(image, threshold=self.threshold)

        result = {"texts": [], "bubbles": []}
        for (x1, y1, x2, y2), class_id, conf in zip(dets.xyxy, dets.class_id, dets.confidence):
            entry = {
                "x": float(x1),
                "y": float(y1),
                "w": float(x2 - x1),
                "h": float(y2 - y1),
                "confidence": float(conf),
            }
            name = self._class_names[int(class_id)]
            result["texts" if name == "text" else "bubbles"].append(entry)
        return result
