# Placeholder embeddings; replace with real model later.
import numpy as np
def embed_texts(texts, dim=1536):
    rng = np.random.default_rng(42)
    vecs = rng.normal(size=(len(texts), dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)+1e-9
    return (vecs / norms).tolist()
