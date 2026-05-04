from __future__ import annotations

import hashlib
import os
import re
import warnings
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Sequence

import numpy as np

# multilingual-e5-large produces 1024-dim vectors; zero-padded to 1536 so the pgvector
# column type (vector(1536)) stays compatible with OpenAI text-embedding-3-small.
# Override with EMBEDDING_MODEL_LOCAL env var to use a different local model.
STORAGE_DIM = 1536


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


def _allow_hash_fallback() -> bool:
    return os.getenv("EMBEDDING_ALLOW_HASH_FALLBACK", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


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
        return f"local:{self._model_name}:padded{STORAGE_DIM}"

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
    name = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    if name == "hash":
        import logging
        logging.getLogger(__name__).warning(
            "EMBEDDING_PROVIDER=hash produces semantically meaningless embeddings. "
            "Set EMBEDDING_PROVIDER=local or EMBEDDING_PROVIDER=openai for real semantic search."
        )
        return HashingProvider()
    if name == "local":
        model = os.getenv("EMBEDDING_MODEL_LOCAL", "intfloat/multilingual-e5-large")
        try:
            return LocalProvider(model)
        except Exception as exc:
            if _allow_hash_fallback():
                warnings.warn(
                    f"Falling back to hash embeddings because local model '{model}' is unavailable: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return HashingProvider()
            raise RuntimeError(
                "Local embeddings are unavailable and hash fallback is disabled. "
                "Install the local embedding model dependencies or set "
                "EMBEDDING_ALLOW_HASH_FALLBACK=1 for an explicit degraded mode."
            ) from exc
    if name == "openai":
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIProvider(model)
    if name == "random":
        seed = int(os.getenv("EMBEDDING_RANDOM_SEED", "42"))
        return RandomProvider(seed=seed)
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER: {name}")


def current_embedding_model() -> str:
    return get_embedding_provider().embedding_model


def provider_for_embedding_model(embedding_model: str) -> EmbeddingProvider:
    model = (embedding_model or "").strip()
    if not model:
        raise RuntimeError("embedding_model is empty")
    if model == current_embedding_model():
        return get_embedding_provider()
    if model == "hash:v1:1536":
        return HashingProvider()
    if model == "random:test-only":
        seed = int(os.getenv("EMBEDDING_RANDOM_SEED", "42"))
        return RandomProvider(seed=seed)
    if model.startswith("openai:"):
        return OpenAIProvider(model.split(":", 1)[1])
    if model.startswith("local:") and model.endswith(":padded1536"):
        local_model = model[len("local:") : -len(":padded1536")]
        if not local_model:
            raise RuntimeError(f"Invalid local embedding model identifier: {model}")
        return LocalProvider(local_model)
    raise RuntimeError(f"Unsupported embedding_model: {model}")
