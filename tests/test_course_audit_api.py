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
from backend.app.models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseModule,
    Dataset,
    Document,
)
from backend.app.services.course_audit import CourseAuditService


def _client():
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
    return TestClient(app), Session, engine


def _audited_course(db):
    dataset = Dataset(name="api-audit")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="API Course", source_type="manual")
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, title="Module", position=1)
    db.add(module)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title="objectives.txt",
        source="test://objectives",
        status="ready",
        source_metadata={"document_type": "learning_objectives"},
    )
    db.add(document)
    db.flush()
    text = "После модуля студент сможет анализировать алгоритмы сортировки."
    db.add(
        Chunk(
            document_id=document.id,
            idx=0,
            text=text,
            meta={"source_start": 0, "source_end": len(text)},
        )
    )
    run = AuditRun(
        course_id=course.id,
        status="queued",
        pipeline_version="test",
        extractor_version="test",
        classifier_version="test",
        embedding_model="hash:test",
        relation_model="test",
        config={},
        metrics={},
    )
    db.add(run)
    db.commit()
    CourseAuditService(db).run(course.id, run.id)
    return course.id, run.id


def test_audit_read_and_finding_review_api():
    client, Session, engine = _client()
    db = Session()
    course_id, run_id = _audited_course(db)
    db.close()

    report = client.get(f"/audits/{run_id}/report")
    assert report.status_code == 200
    assert report.json()["summary"]["objectives_total"] == 1
    canvas_evaluation = client.get(f"/audits/{run_id}/canvas-alignment")
    assert canvas_evaluation.status_code == 200
    assert canvas_evaluation.json()["available"] is False
    calibration = client.get(f"/audits/{run_id}/canvas-alignment/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["available"] is False
    invalid_threshold = client.post(
        f"/courses/{course_id}/audits",
        json={"config": {"min_relation_score": 1.5, "top_k": 5}},
    )
    assert invalid_threshold.status_code == 422
    wrong_calibration_source = client.post(
        f"/courses/{course_id}/audits",
        json={"config": {"calibration_source_audit_id": 999999}},
    )
    assert wrong_calibration_source.status_code == 422
    finding = report.json()["findings"][0]
    assert finding["evidence"]

    reviewed = client.patch(
        f"/findings/{finding['id']}",
        json={"status": "confirmed", "reviewed_by": "teacher@example.org"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "confirmed"

    invalid = client.patch(
        f"/findings/{finding['id']}",
        json={"status": "new", "reviewed_by": "teacher@example.org"},
    )
    assert invalid.status_code == 422

    history = client.get(f"/findings/{finding['id']}/history")
    assert history.status_code == 200
    assert history.json()[0]["from_status"] == "new"
    assert history.json()[0]["to_status"] == "confirmed"

    app.dependency_overrides.clear()
    engine.dispose()


def test_optional_write_key_protects_mutations(monkeypatch):
    client, Session, engine = _client()
    monkeypatch.setenv("API_WRITE_KEY", "secret-test-key")
    rejected = client.post("/courses", json={"title": "Protected"})
    assert rejected.status_code == 401
    accepted = client.post(
        "/courses",
        json={"title": "Protected"},
        headers={"X-API-Key": "secret-test-key"},
    )
    assert accepted.status_code == 201
    assert client.get("/courses").status_code == 200
    app.dependency_overrides.clear()
    engine.dispose()
