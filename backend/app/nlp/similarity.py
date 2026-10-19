"""Semantic similarity backends.

* ``EmbeddingBackend`` - Sentence-Transformers (default ``all-MiniLM-L6-v2``),
  L2-normalised embeddings, cosine similarity = dot product.
* ``TfidfBackend`` - fallback used when the embedding model cannot be loaded
  (no internet on first run, missing torch, ...). Character n-gram TF-IDF is
  robust to spelling mistakes but cannot understand synonyms, so results produced
  with it are flagged for careful teacher review.

Both expose ``similarity(a, b) -> np.ndarray`` of shape (len(a), len(b)).
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.nlp.config import DEFAULT_MODEL

log = logging.getLogger(__name__)

# Only PyTorch is needed. Without this, `transformers` imports TensorFlow when it
# happens to be installed globally, which is slow and can fail on protobuf versions.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class SimilarityBackend:
    name: str = "base"
    model_name: str = ""
    fallback_reason: str | None = None

    def similarity(self, a: list[str], b: list[str], remove: list[str] | None = None) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class EmbeddingBackend(SimilarityBackend):
    name = "embedding"

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_size: int = 4096):
        from sentence_transformers import SentenceTransformer  # heavy import, done lazily

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._tok_cache: OrderedDict[str, tuple[list[tuple[int, int]], np.ndarray]] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def encode(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            vecs = self._model.encode(missing, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
            with self._lock:
                for t, v in zip(missing, vecs):
                    self._cache[t] = np.asarray(v, dtype=np.float32)
                    if len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
        with self._lock:
            return np.vstack([self._cache[t] if t in self._cache else self._encode_one(t) for t in texts])

    def token_embeddings(self, text: str) -> tuple[list[tuple[int, int]], np.ndarray]:
        """Contextual token embeddings (L2-normalised) with character offsets into ``text``.
        Special tokens have offset (0, 0). Cached, so repeated concepts cost nothing."""
        with self._lock:
            hit = self._tok_cache.get(text)
        if hit is not None:
            return hit
        enc = self._model.tokenizer(text, return_offsets_mapping=True, truncation=True, max_length=self._model.max_seq_length)
        emb = self._model.encode([text], output_value="token_embeddings", convert_to_numpy=False, show_progress_bar=False)[0]
        emb = emb.detach().cpu().numpy().astype(np.float32)
        offsets = [tuple(o) for o in enc["offset_mapping"]]
        if emb.shape[0] != len(offsets):  # should not happen with the same tokenizer; be safe
            n = min(emb.shape[0], len(offsets))
            emb, offsets = emb[:n], offsets[:n]
        emb = _unit(emb)
        with self._lock:
            self._tok_cache[text] = (offsets, emb)
            if len(self._tok_cache) > self._cache_size:
                self._tok_cache.popitem(last=False)
        return offsets, emb

    def _encode_one(self, text: str) -> np.ndarray:
        return np.asarray(self._model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0], dtype=np.float32)

    def similarity(self, a: list[str], b: list[str], remove: list[str] | None = None) -> np.ndarray:
        """Cosine similarity. With ``remove``, the directions of those texts (e.g. the
        question itself) are projected out of both sides first ("topic-debiased"
        similarity), so two sentences that merely share the question's topic no
        longer look alike - only concept-specific content counts."""
        if not a or not b:
            return np.zeros((len(a), len(b)), dtype=np.float32)
        ea, eb = self.encode(a), self.encode(b)
        if remove:
            basis, _ = np.linalg.qr(self.encode(remove).T)  # orthonormal topic basis (dim x k)
            ea = _unit(ea - (ea @ basis) @ basis.T)
            eb = _unit(eb - (eb @ basis) @ basis.T)
        return np.clip(ea @ eb.T, -1.0, 1.0)


class TfidfBackend(SimilarityBackend):
    name = "tfidf"
    model_name = "tfidf-char-ngrams"

    def similarity(self, a: list[str], b: list[str], remove: list[str] | None = None) -> np.ndarray:
        # ``remove`` (topic debiasing) is not meaningful for sparse n-gram vectors and is ignored.
        if not a or not b:
            return np.zeros((len(a), len(b)), dtype=np.float32)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, sublinear_tf=True)
        try:
            m = vec.fit_transform(list(a) + list(b))
        except ValueError:  # empty vocabulary
            return np.zeros((len(a), len(b)), dtype=np.float32)
        return cosine_similarity(m[: len(a)], m[len(a) :])


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms < 1e-9, 1.0, norms)


_backend: SimilarityBackend | None = None
_backend_lock = threading.Lock()


def get_backend(preference: str | None = None, model_name: str | None = None) -> SimilarityBackend:
    """Return the process-wide similarity backend (loaded once).

    ``preference``: "auto" (default) tries the embedding model and falls back to
    TF-IDF; "embedding" behaves like auto but logs an error on failure; "tfidf"
    forces the fallback.
    """
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        preference = (preference or os.getenv("SIMILARITY_BACKEND", "auto")).lower()
        model_name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
        if preference == "tfidf":
            _backend = TfidfBackend()
            _backend.fallback_reason = "TF-IDF backend selected by configuration"
        else:
            try:
                _backend = EmbeddingBackend(model_name)
                log.info("Loaded sentence embedding model %s", model_name)
            except Exception as exc:  # noqa: BLE001 - any failure means fallback
                log.error("Could not load embedding model %s (%s); using TF-IDF fallback", model_name, exc)
                _backend = TfidfBackend()
                _backend.fallback_reason = f"Embedding model unavailable: {type(exc).__name__}"
        return _backend


def loaded_backend() -> SimilarityBackend | None:
    """The backend if it has already been loaded, without triggering a load."""
    return _backend


def set_backend(backend: SimilarityBackend | None) -> None:
    """Override the global backend (used by tests and the evaluation scripts)."""
    global _backend
    with _backend_lock:
        _backend = backend
