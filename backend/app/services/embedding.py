from __future__ import annotations

from .embedding_provider import STORAGE_DIM, get_embedding_provider


def embed_texts(
    texts: list[str],
    dim: int = STORAGE_DIM,
    *,
    timeout_seconds: float | None = None,
) -> list[list[float]]:
    """
    Returns embeddings as Python lists.
    Storage is fixed to 1536 dims (pgvector column vector(1536)).
    """
    if dim != STORAGE_DIM:
        raise ValueError(f"dim must be {STORAGE_DIM} for current storage")
    provider = get_embedding_provider()
    embed_with_timeout = getattr(provider, "embed_with_timeout", None)
    if callable(embed_with_timeout):
        return embed_with_timeout(texts, timeout_seconds=timeout_seconds)
    return provider.embed(texts)
