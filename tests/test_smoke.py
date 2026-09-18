import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["quality"]["extractor"]
    assert body["quality"]["embedding_model"]
    assert "embedding_degraded" in body["quality"]
    assert "llm_available" in body["quality"]
