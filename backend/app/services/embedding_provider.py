from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Sequence

import numpy as np

STORAGE_DIM = 1536  # pgvector storage is fixed to vector(1536)


class EmbeddingProvider(ABC):
    name = "base"

    @property
    @abstractmethod
    def embedding_model(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


def _pad_to_storage(vecs: np.ndarray) -> np.ndarray:
    if vecs.ndim != 2:
        raise ValueError("vecs must be 2D")
    dim = int(vecs.shape[1])
    if dim > STORAGE_DIM:
        raise ValueError(f"embedding dim {dim} exceeds storage dim {STORAGE_DIM}")
    if dim == STORAGE_DIM:
        return vecs.astype(np.float32, copy=False)
    out = np.zeros((vecs.shape[0], STORAGE_DIM), dtype=np.float32)
    out[:, :dim] = vecs.astype(np.float32, copy=False)
    return out


def _l2_normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
    return vecs / norms


_TOK_RE = re.compile(r"[\w-]+", re.UNICODE)


class HashingProvider(EmbeddingProvider):
    """
    Lightweight offline embeddings (no torch).
    Uses a signed hashing trick into STORAGE_DIM dimensions + L2 normalization.
    This is not as semantic as real transformer embeddings, but it is deterministic and
    works well enough for graph edges and search on small/medium datasets.
    """

    name = "hash"

    def __init__(self, dim: int = STORAGE_DIM):
        if dim != STORAGE_DIM:
            raise ValueError("HashingProvider only supports storage dim")
        self._dim = dim

    @property
    def embedding_model(self) -> str:
        return "hash:v1:1536"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = _TOK_RE.findall((t or "").lower())
            if not toks:
                continue
            # term frequency
            for tok in toks:
                h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
                v = int.from_bytes(h, "little", signed=False)
                idx = v % self._dim
                sign = -1.0 if (v >> 63) & 1 else 1.0
                out[i, idx] += sign
        out = _l2_normalize(out)
        return out.tolist()


class LocalProvider(EmbeddingProvider):
    name = "local"

    def __init__(self, model_name: str):
        self._model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers is required for EMBEDDING_PROVIDER=local"
            ) from e
        # CPU-only; model weights are downloaded at runtime if missing.
        self._model = SentenceTransformer(model_name, device="cpu")

    @property
    def embedding_model(self) -> str:
        # Keep it stable for filtering; include base model name.
        return f"local:{self._model_name}:padded1536"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vecs = np.asarray(vecs, dtype=np.float32)
        vecs = _pad_to_storage(vecs)
        # normalize again after padding (padding changes norm slightly)
        vecs = _l2_normalize(vecs)
        return vecs.tolist()


class OpenAIProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, model: str):
        self._model = model
        from .openai_client import embeddings  # local import to avoid hard dependency

        self._embeddings_fn = embeddings

    @property
    def embedding_model(self) -> str:
        return f"openai:{self._model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._embeddings_fn(self._model, list(texts))
        arr = np.asarray(vecs, dtype=np.float32)
        if arr.shape[1] != STORAGE_DIM:
            raise RuntimeError(
                f"OpenAI embeddings returned dim={arr.shape[1]} but storage expects {STORAGE_DIM}"
            )
        arr = _l2_normalize(arr)
        return arr.tolist()


class RandomProvider(EmbeddingProvider):
    name = "random"

    def __init__(self, seed: int = 42):
        self._seed = int(seed)

    @property
    def embedding_model(self) -> str:
        return "random:test-only"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = []
        for t in texts:
            h = hashlib.sha256((str(self._seed) + "::" + t).encode("utf-8")).digest()
            # Turn first 8 bytes into seed.
            s = int.from_bytes(h[:8], "little", signed=False)
            rng = np.random.default_rng(s)
            v = rng.normal(size=(STORAGE_DIM,)).astype(np.float32)
            v = v / (np.linalg.norm(v) + 1e-12)
            vecs.append(v.tolist())
        return vecs


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    name = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()
    if name == "hash":
        return HashingProvider()
    if name == "local":
        model = os.getenv("EMBEDDING_MODEL_LOCAL", "intfloat/multilingual-e5-small")
        return LocalProvider(model)
    if name == "openai":
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIProvider(model)
    if name == "random":
        seed = int(os.getenv("EMBEDDING_RANDOM_SEED", "42"))
        return RandomProvider(seed=seed)
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER: {name}")


def current_embedding_model() -> str:
    return get_embedding_provider().embedding_model
