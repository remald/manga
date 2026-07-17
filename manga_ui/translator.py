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
        return self._complete(
            f"Translate the following segment into {self.target_language}, "
            f"without additional explanation.\n\n{text}",
            max_tokens=512,
        )

    def translate_batch(self, texts: list) -> list | None:
        """Translates all fragments of a page in one call as a numbered list,
        so the model sees cross-bubble context. Returns None if the model
        broke the list structure (caller should fall back to translate())."""
        texts = [" ".join(t.split()) for t in texts]  # keep each item on one line
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts) if t)
        if not numbered:
            return ["" for _ in texts]
        out = self._complete(
            f"Translate the following segment into {self.target_language}, "
            f"without additional explanation.\n\n{numbered}",
            max_tokens=min(2048, 128 + 96 * len(texts)),
        )
        import re
        parsed = {}
        for line in out.splitlines():
            m = re.match(r"\s*(\d+)[.)]\s*(.*)", line)
            if m:
                parsed[int(m.group(1))] = m.group(2).strip()
        result = []
        n = 0
        for t in texts:
            if not t:
                result.append("")
                continue
            n += 1
            if n not in parsed:
                return None
            result.append(parsed[n])
        if len(parsed) != n:
            return None
        return result

    def _complete(self, prompt: str, max_tokens: int) -> str:
        self._ensure_loaded()
        # official HY-MT prompt format; sampling params from the model card
        response = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repeat_penalty=1.05,
            max_tokens=max_tokens,
        )
        return response["choices"][0]["message"]["content"].strip()
