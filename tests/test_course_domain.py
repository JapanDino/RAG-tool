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
from backend.app.models.models import Course, CourseModule, Document


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


def test_course_domain_tables_are_registered():
    expected = {
        "courses",
        "course_modules",
        "audit_runs",
        "learning_objectives",
        "learning_materials",
        "assessment_items",
        "alignment_edges",
        "course_findings",
    }
    assert expected.issubset(Base.metadata.tables)


def test_course_crud_creates_dataset_and_modules():
    client, Session, engine = _client()
    response = client.post(
        "/courses",
        json={
            "title": "Алгоритмы",
            "description": "Демонстрационный курс",
            "source_type": "manual",
            "modules": [
                {"title": "Сортировки", "position": 1, "metadata": {"kind": "core"}}
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dataset_id"] > 0
    assert body["modules"][0]["title"] == "Сортировки"
    assert body["modules"][0]["metadata"] == {"kind": "core"}

    course_id = body["id"]
    response = client.get(f"/courses/{course_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Алгоритмы"

    response = client.patch(f"/courses/{course_id}", json={"description": "Обновлено"})
    assert response.status_code == 200
    assert response.json()["description"] == "Обновлено"

    db = Session()
    assert db.query(Course).count() == 1
    assert db.query(CourseModule).count() == 1
    db.close()

    app.dependency_overrides.clear()
    engine.dispose()


def test_course_external_id_import_is_idempotent():
    client, Session, engine = _client()
    payload = {
        "title": "Canvas course",
        "source_type": "canvas",
        "external_id": "canvas-42",
        "modules": [{"title": "Module 1", "external_id": "m1"}],
    }
    first = client.post("/courses", json=payload)
    second = client.post("/courses", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    db = Session()
    assert db.query(Course).count() == 1
    assert db.query(CourseModule).count() == 1
    db.close()

    app.dependency_overrides.clear()
    engine.dispose()


def test_course_document_upload_is_safe_and_idempotent(tmp_path, monkeypatch):
    client, Session, engine = _client()
    monkeypatch.setattr("backend.app.routers.courses.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        "backend.app.routers.courses.enqueue_or_mark", lambda db, job: None
    )
    course = client.post("/courses", json={"title": "Upload course"}).json()

    first = client.post(
        f"/courses/{course['id']}/documents",
        files={
            "file": (
                "../objectives.txt",
                "После модуля студент сможет анализировать данные.",
                "text/plain",
            )
        },
        data={"document_type": "learning_objectives"},
    )
    assert first.status_code == 201
    assert first.json()["title"] == "objectives.txt"
    assert first.json()["duplicate"] is False
    assert len(list(tmp_path.iterdir())) == 1

    second = client.post(
        f"/courses/{course['id']}/documents",
        files={
            "file": (
                "objectives.txt",
                "После модуля студент сможет анализировать данные.",
                "text/plain",
            )
        },
        data={"document_type": "learning_objectives"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duplicate"] is True
    assert len(list(tmp_path.iterdir())) == 1

    db = Session()
    failed_document = db.get(Document, first.json()["id"])
    failed_document.status = "failed"
    db.commit()
    db.close()
    retry = client.post(
        f"/courses/{course['id']}/documents",
        files={
            "file": (
                "objectives.txt",
                "После модуля студент сможет анализировать данные.",
                "text/plain",
            )
        },
        data={"document_type": "learning_objectives"},
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["duplicate"] is False

    bad = client.post(
        f"/courses/{course['id']}/documents",
        files={"file": ("payload.exe", b"bad", "application/octet-stream")},
    )
    assert bad.status_code == 415

    app.dependency_overrides.clear()
    engine.dispose()
