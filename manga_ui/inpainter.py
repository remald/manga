class LamaInpainter:
    """LaMa inpainting (simple-lama-inpainting) for erasing text outside
    bubbles. Lazy-loaded; the weights are downloaded on first use."""

    def __init__(self):
        self._lama = None

    def _ensure_loaded(self):
        if self._lama is None:
            from simple_lama_inpainting import SimpleLama
            self._lama = SimpleLama()

    def inpaint(self, pil_image, pil_mask):
        """mask: L-mode image, 255 = area to fill."""
        self._ensure_loaded()
        return self._lama(pil_image, pil_mask)
