from datetime import datetime, timedelta, timezone

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
    Chunk,
    Course,
    CourseCopilotSuggestion,
    CourseMembership,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Document,
    User,
)
from backend.app.services.teacher_workspace import tutor_quality_signal


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("COURSE_COPILOT_PROVIDER", "template")
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
    return TestClient(app), engine


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def test_teacher_attention_queue_and_authenticated_review(monkeypatch):
    client, engine = _client(monkeypatch)
    try:
        client.post("/identity/development/bootstrap", json={})
        demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
        assert demo.status_code == 201
        course_id = demo.json()["course_id"]

        workspace = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        )
        assert workspace.status_code == 200
        payload = workspace.json()
        assert payload["latest_audit"]["status"] == "done"
        assert payload["health"]["objectives_total"] == 1
        assert payload["health"]["findings_total"] == 2
        assert payload["findings"][0]["severity"] == "high"
        assert payload["findings"][0]["attention_label"] == "Сначала"
        assert payload["findings"][0]["confidence_label"]
        assert payload["findings"][0]["evidence"]
        assert set(payload["findings"][0]["evidence"][0]) == {
            "object_type",
            "object_id",
            "document_id",
            "quote",
            "source_start",
            "source_end",
        }

        finding_id = payload["findings"][0]["id"]
        reviewed = client.patch(
            f"/findings/{finding_id}",
            headers=_headers("instructor@local.test"),
            json={
                "status": "confirmed",
                "reviewed_by": "spoofed@example.test",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewed_by"] == "instructor@local.test"
        history = client.get(
            f"/findings/{finding_id}/history",
            headers=_headers("instructor@local.test"),
        )
        assert history.json()[0]["reviewed_by"] == "instructor@local.test"

        refreshed = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        ).json()
        assert refreshed["health"]["findings_reviewed"] == 1
        assert any(
            item["id"] == finding_id and item["status"] == "confirmed"
            for item in refreshed["findings"]
        )

        unconfirmed_id = next(
            item["id"] for item in refreshed["findings"] if item["status"] == "new"
        )
        unconfirmed_draft = client.post(
            f"/findings/{unconfirmed_id}/copilot",
            headers=_headers("instructor@local.test"),
            json={"top_k": 5, "language": "ru"},
        )
        assert unconfirmed_draft.status_code == 409

        generated = client.post(
            f"/findings/{finding_id}/copilot",
            headers=_headers("instructor@local.test"),
            json={"top_k": 5, "language": "ru"},
        )
        assert generated.status_code == 201
        suggestion = generated.json()
        assert suggestion["status"] == "draft"
        assert suggestion["citations"]
        edited_draft = suggestion["draft"] + "\n\nПроверено преподавателем."
        accepted = client.patch(
            f"/copilot/suggestions/{suggestion['id']}",
            headers=_headers("instructor@local.test"),
            json={
                "status": "accepted",
                "reviewed_by": "spoofed@example.test",
                "draft": edited_draft,
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["draft"] == edited_draft
        assert accepted.json()["reviewed_by"] == "instructor@local.test"

        insufficient = client.post(
            f"/findings/{finding_id}/copilot",
            headers=_headers("instructor@local.test"),
            json={"top_k": 5, "language": "ru"},
        )
        assert insufficient.status_code == 201
        with sessionmaker(bind=engine, future=True)() as db:
            stored = db.get(CourseCopilotSuggestion, insufficient.json()["id"])
            stored.insufficient_context = True
            stored.citations = []
            db.commit()
        blocked_accept = client.patch(
            f"/copilot/suggestions/{insufficient.json()['id']}",
            headers=_headers("instructor@local.test"),
            json={"status": "accepted", "draft": "This must not be saved."},
        )
        assert blocked_accept.status_code == 409
        with sessionmaker(bind=engine, future=True)() as db:
            stored = db.get(CourseCopilotSuggestion, insufficient.json()["id"])
            assert stored.status == "draft"
            assert stored.reviewed_by is None

        student_denied = client.post(
            f"/findings/{finding_id}/copilot",
            headers=_headers("student@local.test"),
            json={"top_k": 5, "language": "ru"},
        )
        assert student_denied.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_teacher_workspace_has_safe_empty_state_and_denies_students(monkeypatch):
    client, engine = _client(monkeypatch)
    try:
        client.post("/identity/development/bootstrap", json={})
        created = client.post(
            "/courses",
            headers=_headers("instructor@local.test"),
            json={"title": "Новый курс без аудита"},
        )
        course_id = created.json()["id"]
        empty = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        )
        assert empty.status_code == 200
        assert empty.json()["latest_audit"] is None
        assert empty.json()["findings"] == []
        assert empty.json()["tutor_quality"]["questions_total"] == 0
        assert empty.json()["tutor_quality"]["signal"] == "empty"

        client.post("/identity/development/bootstrap", json={})
        denied = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("student@local.test"),
        )
        assert denied.status_code == 404
        assert denied.json()["detail"] == "resource not found"
        designer_denied = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("designer@local.test"),
        )
        assert designer_denied.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_teacher_tutor_quality_is_aggregate_student_service_data(monkeypatch):
    client, engine = _client(monkeypatch)
    try:
        client.post("/identity/development/bootstrap", json={})
        demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
        course_id = demo.json()["course_id"]
        other_course = client.post(
            "/courses",
            headers=_headers("instructor@local.test"),
            json={"title": "Other course"},
        ).json()

        with sessionmaker(bind=engine, future=True)() as db:
            course = db.get(Course, course_id)
            assert course is not None and course.organization_id is not None
            student = db.query(User).filter(User.email == "student@local.test").one()
            instructor = (
                db.query(User).filter(User.email == "instructor@local.test").one()
            )
            chunk, document = (
                db.query(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .filter(Document.dataset_id == course.dataset_id)
                .order_by(Chunk.id)
                .first()
            )
            valid_citation = {
                "source_id": "S1",
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_title": document.title,
                "quote": " ".join(chunk.text.split())[:900],
                "score": 0.9,
            }
            course_membership = CourseMembership(
                organization_id=course.organization_id,
                course_id=course_id,
                user_id=student.id,
                role="student",
                is_active=True,
            )
            former = User(
                email="former-student@local.test",
                display_name="Former Student",
                is_active=True,
            )
            db.add_all([course_membership, former])
            db.flush()
            db.add(
                CourseMembership(
                    organization_id=course.organization_id,
                    course_id=course_id,
                    user_id=former.id,
                    role="student",
                    is_active=False,
                )
            )
            db.add(
                CourseMembership(
                    organization_id=course.organization_id,
                    course_id=other_course["id"],
                    user_id=student.id,
                    role="student",
                    is_active=True,
                )
            )
            rows = [
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="private supported question",
                    answer="private supported answer",
                    citations=[dict(valid_citation)],
                    confidence=0.9,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                    feedback_status="helpful",
                    feedback_comment="private feedback",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="private assessment request",
                    answer="private guidance",
                    citations=[],
                    confidence=0.8,
                    retrieval_method="policy",
                    generation_provider="test",
                    response_mode="guidance",
                    feedback_status="helpful",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="private unsupported question",
                    answer="private abstention",
                    citations=[],
                    confidence=0.1,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    insufficient_context=True,
                    response_mode="abstained",
                    feedback_status="unhelpful",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="private uncited question",
                    answer="private uncited answer",
                    citations=[{**valid_citation, "quote": "tampered quote"}],
                    confidence=0.8,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                    feedback_status="helpful",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="private weak question",
                    answer="private weak answer",
                    citations=[{**valid_citation, "source_id": "S2"}],
                    confidence=0.3,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=instructor.id,
                    question="staff test question",
                    answer="staff test answer",
                    citations=[{"source_id": "S3"}],
                    confidence=1.0,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=former.id,
                    question="former student question",
                    answer="former student answer",
                    citations=[{"source_id": "S4"}],
                    confidence=1.0,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                ),
                CourseQuestionAnswer(
                    course_id=other_course["id"],
                    asked_by_user_id=student.id,
                    question="other course question",
                    answer="other course answer",
                    citations=[{"source_id": "S5"}],
                    confidence=1.0,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                ),
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question="old student question",
                    answer="old student answer",
                    citations=[{"source_id": "S6"}],
                    confidence=1.0,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                    created_at=datetime.now(timezone.utc) - timedelta(days=31),
                ),
            ]
            db.add_all(rows)
            db.flush()
            db.add_all(
                [
                    CourseQaFeedbackEvent(
                        answer_id=rows[index].id,
                        course_id=course_id,
                        reviewed_by_user_id=student.id,
                        from_status="unreviewed",
                        to_status=rows[index].feedback_status,
                        reviewed_by=student.email,
                    )
                    for index in range(3)
                ]
                + [
                    CourseQaFeedbackEvent(
                        answer_id=rows[3].id,
                        course_id=course_id,
                        reviewed_by_user_id=instructor.id,
                        from_status="unreviewed",
                        to_status="helpful",
                        reviewed_by=instructor.email,
                    ),
                    CourseQaFeedbackEvent(
                        answer_id=rows[0].id,
                        course_id=course_id,
                        reviewed_by_user_id=instructor.id,
                        from_status="helpful",
                        to_status="unhelpful",
                        reviewed_by=instructor.email,
                    ),
                    CourseQaFeedbackEvent(
                        answer_id=rows[1].id,
                        course_id=course_id,
                        reviewed_by_user_id=student.id,
                        from_status="helpful",
                        to_status="unhelpful",
                        reviewed_by=student.email,
                    ),
                ]
            )
            rows[0].feedback_status = "unhelpful"
            rows[1].feedback_status = "unhelpful"
            db.commit()

        response = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        )
        assert response.status_code == 200
        quality = response.json()["tutor_quality"]
        assert quality == {
            "period_days": 30,
            "minimum_feedback_sample": 3,
            "signal": "review",
            "questions_total": 5,
            "answer_responses": 3,
            "supported_answers": 2,
            "guidance_answers": 1,
            "abstained_answers": 1,
            "answers_needing_review": 2,
            "rated_answers": 3,
            "helpful_answers": 1,
            "helpful_rate": 0.3333,
        }
        assert "private" not in str(quality).lower()
        assert {
            "question",
            "answer",
            "asked_by_user_id",
            "citations",
            "feedback_comment",
            "reviewed_by",
            "email",
        }.isdisjoint(quality)

        methodologist = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("methodologist@local.test"),
        )
        assert methodologist.status_code == 404
        client.post("/identity/development/bootstrap", json={})
        methodologist = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("methodologist@local.test"),
        )
        assert methodologist.status_code == 200
        assert methodologist.json()["tutor_quality"] == quality
        admin = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("admin@local.test"),
        )
        assert admin.status_code == 200
        for denied_identity in ("student@local.test", "designer@local.test"):
            denied = client.get(
                f"/courses/{course_id}/teacher-workspace",
                headers=_headers(denied_identity),
            )
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_teacher_tutor_helpfulness_waits_for_minimum_sample(monkeypatch):
    client, engine = _client(monkeypatch)
    try:
        client.post("/identity/development/bootstrap", json={})
        demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
        course_id = demo.json()["course_id"]
        client.post("/identity/development/bootstrap", json={})
        with sessionmaker(bind=engine, future=True)() as db:
            student = db.query(User).filter(User.email == "student@local.test").one()
            answers = [
                CourseQuestionAnswer(
                    course_id=course_id,
                    asked_by_user_id=student.id,
                    question=f"Question {index}",
                    answer="Answer",
                    citations=[],
                    confidence=0.9,
                    retrieval_method="hybrid",
                    generation_provider="test",
                    response_mode="answer",
                    feedback_status="helpful",
                )
                for index in range(2)
            ]
            db.add_all(answers)
            db.flush()
            db.add_all(
                [
                    CourseQaFeedbackEvent(
                        answer_id=answer.id,
                        course_id=course_id,
                        reviewed_by_user_id=student.id,
                        from_status="unreviewed",
                        to_status="helpful",
                        reviewed_by=student.email,
                    )
                    for answer in answers
                ]
            )
            db.commit()
        quality = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        ).json()["tutor_quality"]
        assert quality["rated_answers"] == 2
        assert quality["helpful_answers"] is None
        assert quality["helpful_rate"] is None
        assert quality["signal"] == "early"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {
                "questions_total": 5,
                "answer_responses": 0,
                "abstained_answers": 0,
                "answers_needing_review": 0,
            },
            "limited",
        ),
        (
            {
                "questions_total": 100,
                "answer_responses": 59,
                "abstained_answers": 40,
                "answers_needing_review": 1,
            },
            "coverage",
        ),
        (
            {
                "questions_total": 5,
                "answer_responses": 5,
                "abstained_answers": 0,
                "answers_needing_review": 1,
            },
            "review",
        ),
        (
            {
                "questions_total": 5,
                "answer_responses": 5,
                "abstained_answers": 0,
                "answers_needing_review": 0,
            },
            "steady",
        ),
    ],
)
def test_tutor_quality_signal_prioritizes_systemic_conditions(values, expected):
    assert tutor_quality_signal(**values) == expected
