from .embedding_provider import STORAGE_DIM, get_embedding_provider


def embed_query(q: str, dim: int = STORAGE_DIM):
    if dim != STORAGE_DIM:
        raise ValueError(f"dim must be {STORAGE_DIM} for current storage")
    return get_embedding_provider().embed_query(q)
