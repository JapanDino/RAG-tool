from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.db.session import get_db
from backend.app.models.base import Base
from backend.app.models.models import BloomAnnotation, BloomLevel, Chunk, Dataset, Document


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


def _seed_data(db):
    dataset = Dataset(name="dataset-1")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    document = Document(dataset_id=dataset.id, title="doc", source="test")
    db.add(document)
    db.commit()
    db.refresh(document)

    chunk = Chunk(document_id=document.id, idx=0, text="chunk text", meta={})
    db.add(chunk)
    db.commit()
    db.refresh(chunk)

    annotation = BloomAnnotation(
        chunk_id=chunk.id,
        level=BloomLevel.apply,
        label="label",
        rationale="rationale",
        score=0.7,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)

    return dataset, document, chunk, annotation


def test_annotation_management_endpoints():
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
    dataset, document, chunk, annotation = _seed_data(db)
    db.close()

    resp = client.get(f"/annotate/chunks/{chunk.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/annotate/chunks/{chunk.id}/levels/apply")
    assert resp.status_code == 200
    assert resp.json()["id"] == annotation.id

    resp = client.put(
        f"/annotate/chunks/{chunk.id}/levels/apply",
        json={"score": 0.8},
    )
    assert resp.status_code == 200
    assert resp.json()["score"] == 0.8
    assert resp.json()["version"] == 2

    resp = client.put(
        f"/annotate/chunks/{chunk.id}/levels/remember",
        json={"label": "x", "rationale": "y", "score": 0.2},
    )
    assert resp.status_code == 200
    assert resp.json()["level"] == "remember"

    resp = client.get(f"/annotate/datasets/{dataset.id}/annotations")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    resp = client.delete(f"/annotate/chunks/{chunk.id}/levels/apply")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    app.dependency_overrides.clear()
    engine.dispose()

