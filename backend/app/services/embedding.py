from __future__ import annotations

from .embedding_provider import STORAGE_DIM, get_embedding_provider


def embed_texts(texts: list[str], dim: int = STORAGE_DIM) -> list[list[float]]:
    """
    Returns embeddings as Python lists.
    Storage is fixed to 1536 dims (pgvector column vector(1536)).
    """
    if dim != STORAGE_DIM:
        raise ValueError(f"dim must be {STORAGE_DIM} for current storage")
    provider = get_embedding_provider()
    return provider.embed(texts)
