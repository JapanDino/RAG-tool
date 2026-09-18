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
    CourseFinding,
    Dataset,
    Document,
    LearningObjective,
)


def test_copilot_endpoint_returns_grounded_draft(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    dataset = Dataset(name="copilot-api")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="API Course", source_type="manual")
    db.add(course)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        title="sorting.md",
        source="test://sorting",
        status="ready",
        source_metadata={"document_type": "lecture_material"},
    )
    db.add(document)
    db.flush()
    db.add(
        Chunk(
            document_id=document.id,
            idx=0,
            text="Алгоритмы сравнивают по времени и памяти.",
            meta={},
        )
    )
    run = AuditRun(
        course_id=course.id,
        status="done",
        pipeline_version="test",
        extractor_version="test",
        classifier_version="test",
        embedding_model="hash",
        relation_model="test",
        config={},
        metrics={},
    )
    db.add(run)
    db.flush()
    objective = LearningObjective(
        course_id=course.id,
        document_id=document.id,
        audit_run_id=run.id,
        text="Анализировать сложность алгоритмов",
        normalized_text="анализировать сложность алгоритмов",
        bloom_vector=[0, 0, 0, 1, 0, 0],
        top_bloom_levels=["analyze"],
        confidence=0.9,
    )
    db.add(objective)
    db.flush()
    finding = CourseFinding(
        course_id=course.id,
        audit_run_id=run.id,
        finding_type="objective_without_assessment",
        severity="high",
        title="Нет задания",
        description="Цель не проверяется.",
        evidence=[
            {
                "object_type": "learning_objective",
                "object_id": objective.id,
                "quote": objective.text,
            }
        ],
        recommendation="Добавьте задание",
        confidence=0.8,
        uncertainty_reasons=[],
        status="confirmed",
        model_info={},
    )
    db.add(finding)
    db.commit()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("COURSE_COPILOT_PROVIDER", "template")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)
    response = client.post(
        f"/findings/{finding.id}/copilot", json={"top_k": 3, "language": "ru"}
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"]
    assert payload["status"] == "draft"
    assert payload["action_type"] == "create_assessment"
    assert payload["citations"][0]["document_id"] == document.id
    assert payload["citations"][0]["quote"]

    history = client.get(f"/findings/{finding.id}/copilot")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [payload["id"]]

    accepted = client.patch(
        f"/copilot/suggestions/{payload['id']}",
        json={"status": "accepted", "reviewed_by": "teacher@example.org"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["review_reason"] == "teacher_accepted"
    assert accepted.json()["reviewed_by"] == "teacher@example.org"

    second = client.post(
        f"/findings/{finding.id}/copilot", json={"top_k": 3, "language": "ru"}
    )
    assert second.status_code == 201
    second_id = second.json()["id"]
    accepted_second = client.patch(
        f"/copilot/suggestions/{second_id}",
        json={"status": "accepted", "reviewed_by": "methodist@example.org"},
    )
    assert accepted_second.status_code == 200
    reviewed_history = client.get(f"/findings/{finding.id}/copilot").json()
    assert reviewed_history[0]["status"] == "accepted"
    assert reviewed_history[1]["status"] == "rejected"
    assert reviewed_history[1]["review_reason"] == "superseded"

    report = client.get(f"/audits/{run.id}/report")
    assert report.status_code == 200
    assert len(report.json()["copilot_suggestions"]) == 2
    assert {item["status"] for item in report.json()["copilot_suggestions"]} == {
        "accepted",
        "rejected",
    }
    download = client.get(f"/audits/{run.id}/report/download")
    assert download.status_code == 200
    assert (
        download.headers["content-disposition"]
        == f'attachment; filename="course-audit-{run.id}.json"'
    )
    assert download.json()["copilot_suggestions"][1]["status"] == "accepted"
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
