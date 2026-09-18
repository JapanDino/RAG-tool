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
from backend.app.models.models import Course, Document


def test_demo_course_is_idempotent_and_ready_for_copilot(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("ENABLE_DEMO_SEED", "1")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    first = client.post("/courses/demo")
    assert first.status_code == 201
    assert first.json()["created"] is True
    second = client.post("/courses/demo")
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["course_id"] == first.json()["course_id"]
    assert second.json()["audit_run_id"] == first.json()["audit_run_id"]

    report = client.get(f"/audits/{first.json()['audit_run_id']}/report")
    assert report.status_code == 200
    assert report.json()["summary"]["objectives_total"] == 1
    assert report.json()["summary"]["assessments_total"] == 1
    assert {item["finding_type"] for item in report.json()["findings"]} >= {
        "bloom_mismatch"
    }
    with Session() as db:
        course = db.get(Course, first.json()["course_id"])
        assert course.source_metadata["demo"] is True
        assert (
            db.query(Document).filter(Document.dataset_id == course.dataset_id).count()
            == 3
        )
    app.dependency_overrides.clear()
    engine.dispose()
