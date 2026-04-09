import pytest


pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.models import Dataset, KnowledgeNode, NodeLabel


def _setup_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session


def test_export_labels_does_not_hide_non_current_embedding_model():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-export")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Fractions",
        context_text="Compare simple fractions",
        prob_vector=[0.1, 0.1, 0.6, 0.1, 0.05, 0.05],
        top_levels=["apply"],
        embedding_model="local:intfloat/multilingual-e5-small:padded1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    label = NodeLabel(node_id=node.id, labels=["apply"], annotator="teacher", source="human")
    db.add(label)
    db.commit()
    db.close()

    resp = client.get(f"/datasets/{dataset.id}/labeling/export?annotator=teacher")
    assert resp.status_code == 200
    assert "Fractions" in resp.text
    assert "local:intfloat/multilingual-e5-small:padded1536" in resp.text

    app.dependency_overrides.clear()
    engine.dispose()


def test_evaluate_prefers_stored_top_levels(monkeypatch):
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-eval")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Photosynthesis",
        context_text="Explain the role of chlorophyll",
        prob_vector=[0.05, 0.8, 0.05, 0.05, 0.03, 0.02],
        top_levels=["understand"],
        embedding_model="hash:v1:1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    label = NodeLabel(node_id=node.id, labels=["understand"], annotator="teacher", source="human")
    db.add(label)
    db.commit()
    db.close()

    def should_not_be_used(*args, **kwargs):
        return {"top_levels": ["create"]}

    monkeypatch.setattr("backend.app.routers.evaluate.classify_bloom_multilabel", should_not_be_used)

    resp = client.get(f"/evaluate/metrics?dataset_id={dataset.id}&annotator=teacher")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_source"] == "stored_top_levels"
    assert body["stored_predictions"] == 1
    assert body["recomputed_predictions"] == 0
    assert body["f1_micro"] == 1.0

    app.dependency_overrides.clear()
    engine.dispose()
