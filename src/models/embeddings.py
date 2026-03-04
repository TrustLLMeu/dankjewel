"""Embedding helper using sentence-transformers with LRU caching."""
from functools import lru_cache
from typing import List
import numpy as np


class Embeddings:
    """Wrapper around a sentence-transformers model.

    Lazy-loads the model on first use. Provides batch embedding with an
    LRU cache for individual texts.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None

    def _init_model(self):
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as e:
                raise RuntimeError("sentence-transformers is required for embeddings: pip install sentence-transformers")
            self.model = SentenceTransformer(self.model_name)

    @lru_cache(maxsize=8192)
    def embed_text(self, text: str) -> tuple:
        """Embed a single text and return a tuple(serialized) for cacheability."""
        self._init_model()
        vec = self.model.encode(text, convert_to_numpy=True)
        return vec.tobytes(), vec.shape

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embed a list of texts. Uses per-text cache when possible."""
        self._init_model()
        to_compute = []
        results = [None] * len(texts)
        for i, t in enumerate(texts):
            try:
                data_bytes, shape = self.embed_text(t)
                arr = np.frombuffer(data_bytes, dtype=np.float32).reshape(shape)
                results[i] = arr
            except Exception:
                to_compute.append(i)
        if to_compute:
            compute_texts = [texts[i] for i in to_compute]
            computed = self.model.encode(compute_texts, convert_to_numpy=True)
            if len(to_compute) == 1:
                computed = np.expand_dims(computed, 0)
            for j, i in enumerate(to_compute):
                results[i] = computed[j]
                # prime cache
                self.embed_text.cache_clear()
                self.embed_text(texts[i])
        return np.vstack(results)

    @staticmethod
    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        if a is None or b is None:
            return 0.0
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

