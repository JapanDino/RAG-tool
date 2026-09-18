import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.models import (
    CanvasOutcomeAlignment,
    Chunk,
    Course,
    CourseModule,
    Document,
)
from backend.app.services.canvas_import import (
    html_to_text,
    persist_canvas_course,
    validate_canvas_base_url,
)


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session()


def _payload(page_body="<p>Алгоритмы сортировки и их временная сложность.</p>"):
    return {
        "course": {
            "id": 42,
            "name": "Algorithms",
            "course_code": "CS101",
            "workflow_state": "available",
            "html_url": "https://canvas.example.edu/courses/42",
            "syllabus_body": "<p>После курса студент сможет анализировать алгоритмы.</p>",
        },
        "modules": [
            {
                "id": 7,
                "name": "Sorting",
                "position": 1,
                "state": "active",
                "published": True,
                "items": [
                    {
                        "id": 70,
                        "title": "Sorting overview",
                        "type": "Page",
                        "page_url": "sorting",
                        "position": 1,
                        "published": True,
                        "html_url": "https://canvas.example.edu/courses/42/pages/sorting",
                    },
                    {
                        "id": 71,
                        "title": "External visualization",
                        "type": "ExternalUrl",
                        "position": 2,
                        "published": True,
                        "external_url": "https://example.org/sorting",
                    },
                ],
            }
        ],
        "pages": [
            {
                "page_id": 8,
                "url": "sorting",
                "title": "Sorting",
                "published": True,
                "body": page_body,
                "module_external_id": "7",
                "html_url": "https://canvas.example.edu/courses/42/pages/sorting",
            }
        ],
        "assignments": [
            {
                "id": 9,
                "name": "Compare",
                "published": True,
                "description": "<p>Сравните quicksort и mergesort.</p>",
                "module_external_id": "7",
                "html_url": "https://canvas.example.edu/courses/42/assignments/9",
            }
        ],
        "quizzes": [],
        "outcome_links": [
            {
                "outcome": {
                    "id": 3,
                    "title": "Analyze algorithms",
                    "description": "<p>Анализировать сложность алгоритмов</p>",
                }
            }
        ],
        "outcome_alignments": [
            {
                "id": 3,
                "assignment_id": 9,
                "title": "Compare",
                "url": "https://canvas.example.edu/courses/42/assignments/9",
                "submission_types": ["online_text_entry"],
            }
        ],
        "outcome_alignments_available": True,
    }


def test_canvas_html_and_ssrf_validation(monkeypatch):
    assert html_to_text("<p>Hello <strong>world</strong></p>") == "Hello world"
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert (
        validate_canvas_base_url("https://canvas.example.edu/")
        == "https://canvas.example.edu"
    )
    with pytest.raises(ValueError, match="HTTPS"):
        validate_canvas_base_url("http://canvas.example.edu")
    with pytest.raises(ValueError, match="local"):
        validate_canvas_base_url("https://localhost")


def test_canvas_import_is_read_only_idempotent_and_version_aware():
    engine, db = _db()
    first = persist_canvas_course(db, _payload(), "https://canvas.example.edu")
    assert first["modules_imported"] == 1
    assert first["documents_created"] == 4
    assert first["explicit_alignments_imported"] == 1
    assert db.query(Course).count() == 1
    assert db.query(CourseModule).count() == 1
    assert db.query(Document).count() == 4
    assert db.query(Chunk).count() >= 4
    assert db.query(CanvasOutcomeAlignment).count() == 1
    outcome_document = (
        db.query(Document).filter(Document.external_id == "canvas:outcome:3").one()
    )
    assignment_document = (
        db.query(Document).filter(Document.external_id == "canvas:assignment:9").one()
    )
    page_document = (
        db.query(Document).filter(Document.external_id == "canvas:page:8").one()
    )
    assert outcome_document.source_metadata["canvas_outcome_id"] == "3"
    assert assignment_document.source_metadata["canvas_assignment_id"] == "9"
    assert page_document.source_metadata["student_visible"] is True
    assert assignment_document.source_metadata["student_visible"] is True
    module = db.query(CourseModule).one()
    assert [item["type"] for item in module.meta["course_map_items"]] == [
        "Page",
        "ExternalUrl",
    ]
    assert module.meta["course_map_items"][1]["external_url"] == (
        "https://example.org/sorting"
    )
    assert "token" not in str(db.query(Course).first().source_metadata).lower()

    legacy = Document(
        dataset_id=first["dataset_id"],
        external_id="canvas:course:42:outcomes",
        title="Legacy outcomes",
        source="canvas",
    )
    db.add(legacy)
    db.flush()
    db.add(Chunk(document_id=legacy.id, idx=0, text="legacy duplicate"))
    db.commit()

    second = persist_canvas_course(db, _payload(), "https://canvas.example.edu")
    assert second["course_id"] == first["course_id"]
    assert second["documents_created"] == 0
    assert second["documents_updated"] == 0
    assert db.query(Document).count() == 4
    assert db.query(CanvasOutcomeAlignment).count() == 1

    changed = persist_canvas_course(
        db,
        _payload("<p>Обновлённый материал о quicksort, mergesort и сложности.</p>"),
        "https://canvas.example.edu",
    )
    assert changed["documents_updated"] == 1
    assert db.query(Document).count() == 4

    unavailable = _payload()
    unavailable["outcome_alignments"] = []
    unavailable["outcome_alignments_available"] = False
    persist_canvas_course(db, unavailable, "https://canvas.example.edu")
    assert db.query(CanvasOutcomeAlignment).count() == 1

    available_empty = _payload()
    available_empty["outcome_alignments"] = []
    available_empty["outcome_alignments_available"] = True
    persist_canvas_course(db, available_empty, "https://canvas.example.edu")
    assert db.query(CanvasOutcomeAlignment).count() == 0
    db.close()
    engine.dispose()


def test_canvas_import_persists_visibility_and_lock_metadata():
    engine, db = _db()
    payload = _payload()
    payload["pages"].extend(
        [
            {
                "page_id": 10,
                "url": "hidden",
                "title": "Hidden page",
                "published": False,
                "body": "<p>Teacher-only draft.</p>",
                "module_external_id": "7",
                "html_url": "https://canvas.example.edu/courses/42/pages/hidden",
            },
            {
                "page_id": 11,
                "url": "future",
                "title": "Future page",
                "published": True,
                "unlock_at": "2099-01-01T00:00:00Z",
                "body": "<p>Future student material.</p>",
                "module_external_id": "7",
                "html_url": "https://canvas.example.edu/courses/42/pages/future",
            },
            {
                "page_id": 12,
                "url": "prerequisite-locked",
                "title": "Prerequisite locked page",
                "published": True,
                "body": "<p>Content after a prerequisite.</p>",
                "module_external_id": "7",
                "item": {
                    "published": True,
                    "module_state": "locked",
                    "module_prerequisite_ids": [6],
                    "module_require_sequential_progress": True,
                },
                "html_url": "https://canvas.example.edu/courses/42/pages/prerequisite-locked",
            },
        ]
    )
    persist_canvas_course(db, payload, "https://canvas.example.edu")

    hidden = db.query(Document).filter(Document.external_id == "canvas:page:10").one()
    future = db.query(Document).filter(Document.external_id == "canvas:page:11").one()
    prerequisite_locked = (
        db.query(Document).filter(Document.external_id == "canvas:page:12").one()
    )
    assert hidden.source_metadata["student_visible"] is False
    assert future.source_metadata["student_visible"] is True
    assert future.source_metadata["unlock_at"] == "2099-01-01T00:00:00Z"
    assert prerequisite_locked.source_metadata["student_visible"] is False
    assert prerequisite_locked.source_metadata["module_state"] == "locked"
    assert prerequisite_locked.source_metadata["module_prerequisite_ids"] == [6]
    db.close()
    engine.dispose()


def test_canvas_import_reconciles_removed_modules_from_learner_topology():
    engine, db = _db()
    payload = _payload()
    first = persist_canvas_course(db, payload, "https://canvas.example.edu")
    module = db.query(CourseModule).one()
    assert module.meta["course_map_items"]

    without_modules = _payload()
    without_modules["modules"] = []
    without_modules["pages"] = []
    without_modules["assignments"] = []
    persist_canvas_course(db, without_modules, "https://canvas.example.edu")

    db.refresh(module)
    assert module.meta["course_map_removed"] is True
    assert module.meta["course_map_items"] == []
    assert first["course_id"] is not None
    db.close()
    engine.dispose()
