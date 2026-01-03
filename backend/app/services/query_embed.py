from .embedding import embed_texts

def embed_query(q: str, dim: int = 1536):
    # Реально здесь должен быть тот же эмбеддинг, что и для документов.
    return embed_texts([q], dim=dim)[0]
