from pathlib import Path

GGUF_PATH = Path(__file__).parent / "models" / "HY-MT1.5-1.8B-Q4_K_M.gguf"


class MangaTranslator:
    """HY-MT1.5-1.8B (Tencent Hunyuan-MT) via llama.cpp, CPU inference.
    Lazy-loaded; call only from the worker thread."""

    def __init__(self, model_path=GGUF_PATH, target_language="Russian"):
        self.model_path = str(model_path)
        self.target_language = target_language
        self._llm = None

    def _ensure_loaded(self):
        if self._llm is None:
            from llama_cpp import Llama
            # ignored by CPU builds of llama.cpp; offloads all layers on CUDA builds
            self._llm = Llama(self.model_path, n_ctx=2048, n_gpu_layers=-1, verbose=False)

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        self._ensure_loaded()
        # official HY-MT prompt format; sampling params from the model card
        prompt = (
            f"Translate the following segment into {self.target_language}, "
            f"without additional explanation.\n\n{text}"
        )
        response = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repeat_penalty=1.05,
            max_tokens=512,
        )
        return response["choices"][0]["message"]["content"].strip()
