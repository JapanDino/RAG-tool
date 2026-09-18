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
    Course,
    CourseMembership,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Document,
    Organization,
    OrganizationMembership,
    User,
)


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def test_student_tutor_scopes_history_and_feedback_to_owner(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("COURSE_QA_PROVIDER", "template")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
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
    client = TestClient(app)
    try:
        client.post("/identity/development/bootstrap", json={})
        demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
        assert demo.status_code == 201
        course_id = demo.json()["course_id"]
        client.post("/identity/development/bootstrap", json={})

        with Session() as db:
            course = db.get(Course, course_id)
            organization = db.get(Organization, course.organization_id)
            lecture = next(
                document
                for document in db.query(Document).filter(
                    Document.dataset_id == course.dataset_id
                )
                if (document.source_metadata or {}).get("document_type")
                == "lecture_material"
            )
            lecture.source = "https://canvas.internal/courses/1/pages/lecture"
            peer = User(
                email="peer@local.test",
                display_name="Peer Student",
                is_active=True,
            )
            db.add(peer)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=peer.id,
                    role="student",
                    is_active=True,
                )
            )
            db.add(
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course_id,
                    user_id=peer.id,
                    role="student",
                    is_active=True,
                )
            )
            db.commit()

        student_answer = client.post(
            f"/courses/{course_id}/qa",
            headers=_headers("student@local.test"),
            json={
                "question": "Чем в среднем quicksort отличается от mergesort?",
                "language": "ru",
            },
        )
        assert student_answer.status_code == 201
        answer = student_answer.json()
        assert answer["response_mode"] == "answer"
        assert answer["citations"]
        assert all(citation["source_url"] is None for citation in answer["citations"])
        with Session() as db:
            stored = db.get(CourseQuestionAnswer, answer["id"])
            assert any(citation["source_url"] for citation in stored.citations)

        instructor_answer = client.post(
            f"/courses/{course_id}/qa",
            headers=_headers("instructor@local.test"),
            json={"question": "Что сказано об устойчивости?", "language": "ru"},
        )
        assert instructor_answer.status_code == 201

        own_history = client.get(
            f"/courses/{course_id}/qa",
            headers=_headers("student@local.test"),
        )
        assert own_history.status_code == 200
        assert [item["id"] for item in own_history.json()] == [answer["id"]]
        peer_history = client.get(
            f"/courses/{course_id}/qa",
            headers=_headers("peer@local.test"),
        )
        assert peer_history.status_code == 200
        assert peer_history.json() == []

        reviewed = client.patch(
            f"/qa/answers/{answer['id']}",
            headers=_headers("student@local.test"),
            json={
                "status": "helpful",
                "reviewed_by": "spoofed@example.test",
                "comment": "Понятно и по материалам курса.",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewed_by"] is None
        assert all(
            citation["source_url"] is None for citation in reviewed.json()["citations"]
        )
        with Session() as db:
            stored = db.get(CourseQuestionAnswer, answer["id"])
            assert stored.reviewed_by == "student@local.test"
            event = (
                db.query(CourseQaFeedbackEvent)
                .filter(CourseQaFeedbackEvent.answer_id == answer["id"])
                .order_by(CourseQaFeedbackEvent.id.desc())
                .first()
            )
            assert event.reviewed_by_user_id == stored.asked_by_user_id
        instructor_history = client.get(
            f"/courses/{course_id}/qa",
            headers=_headers("instructor@local.test"),
        )
        student_row = next(
            item for item in instructor_history.json() if item["id"] == answer["id"]
        )
        assert student_row["reviewed_by"] is None
        instructor_feedback_history = client.get(
            f"/qa/answers/{answer['id']}/history",
            headers=_headers("instructor@local.test"),
        )
        assert instructor_feedback_history.status_code == 200
        assert instructor_feedback_history.json()[0]["reviewed_by"] is None

        staff_review = client.patch(
            f"/qa/answers/{answer['id']}",
            headers=_headers("instructor@local.test"),
            json={"status": "unhelpful", "comment": "Staff quality review"},
        )
        assert staff_review.status_code == 200
        quality = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        ).json()["tutor_quality"]
        assert quality["rated_answers"] == 1

        peer_denied = client.patch(
            f"/qa/answers/{answer['id']}",
            headers=_headers("peer@local.test"),
            json={"status": "unhelpful"},
        )
        assert peer_denied.status_code == 404
        peer_history_denied = client.get(
            f"/qa/answers/{answer['id']}/history",
            headers=_headers("peer@local.test"),
        )
        assert peer_history_denied.status_code == 404

        designer_denied = client.post(
            f"/courses/{course_id}/qa",
            headers=_headers("designer@local.test"),
            json={"question": "Покажи вопросы студентов"},
        )
        assert designer_denied.status_code == 404
        for path in (
            f"/courses/{course_id}/evidence-pack",
            f"/courses/{course_id}/evidence-pack/download",
            f"/courses/{course_id}/ml-feedback",
            f"/courses/{course_id}/ml-feedback/download",
        ):
            response = client.get(path, headers=_headers("designer@local.test"))
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
