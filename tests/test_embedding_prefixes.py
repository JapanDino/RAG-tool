import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.services.embedding_provider import LocalProvider


@pytest.mark.parametrize(
    "name,e5",
    [
        ("intfloat/multilingual-e5-large", True),
        ("C:/cache/e5-small", True),
        ("sentence-transformers/all-MiniLM-L6-v2", False),
    ],
)
def test_search_uses_model_specific_query_and_passage_format(monkeypatch, name, e5):
    calls = []

    def encode(texts, **kwargs):
        calls.append(texts)
        return np.ones((len(texts), 384), dtype=np.float32)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(
            SentenceTransformer=lambda *args, **kwargs: SimpleNamespace(encode=encode),
        ),
    )
    provider = LocalProvider(name)
    passage = provider.embed(["Световая фаза"])[0]
    query = provider.embed_query("Где происходит фотосинтез?")
    assert calls == [
        [("passage: " if e5 else "") + "Световая фаза"],
        [("query: " if e5 else "") + "Где происходит фотосинтез?"],
    ]
    assert len(passage) == len(query) == 1536
    assert np.linalg.norm(passage) == pytest.approx(1)
    # Never search pre-fix document vectors with the new query format.
    assert (":e5-prefix-v1:" in provider.embedding_model) == e5
