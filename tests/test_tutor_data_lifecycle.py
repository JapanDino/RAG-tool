from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile

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
    Dataset,
    Organization,
    OrganizationMembership,
    OrganizationTutorDataPolicyEvent,
    TutorDataDeletionEvent,
    User,
)
from backend.app.services.tutor_data import (
    TutorDataScopeDenied,
    delete_owned_tutor_history,
)
from backend.app.tasks.celery_app import celery_app
from backend.app.tasks.tasks import purge_expired_tutor_history_task


def _client(monkeypatch):
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
    return TestClient(app), engine, Session


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def _bootstrap_course(client: TestClient) -> tuple[int, int]:
    client.post("/identity/development/bootstrap", json={})
    demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
    assert demo.status_code == 201
    client.post("/identity/development/bootstrap", json={})
    context = client.get("/identity/me", headers=_headers("admin@local.test")).json()
    return demo.json()["course_id"], context["organizations"][0]["id"]


def _answer(
    *,
    course_id: int,
    user_id: int,
    question: str,
    created_at: datetime | None = None,
) -> CourseQuestionAnswer:
    return CourseQuestionAnswer(
        course_id=course_id,
        asked_by_user_id=user_id,
        question=question,
        answer=f"Answer for {question}",
        citations=[],
        confidence=0.8,
        retrieval_method="hybrid:test",
        generation_provider="test",
        created_at=created_at,
    )


def test_tutor_data_policy_default_update_version_and_permissions(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        course_id, organization_id = _bootstrap_course(client)

        default = client.get(
            f"/courses/{course_id}/tutor-data-policy",
            headers=_headers("student@local.test"),
        )
        assert default.status_code == 200
        assert default.json() == {
            "organization_id": organization_id,
            "course_id": course_id,
            "retention_days": 90,
            "version": 0,
            "automatic_purge": True,
            "student_self_delete": True,
            "updated_at": None,
        }
        designer = client.get(
            f"/courses/{course_id}/tutor-data-policy",
            headers=_headers("designer@local.test"),
        )
        assert designer.status_code == 404
        for identity in ("instructor@local.test", "methodologist@local.test"):
            denied = client.patch(
                f"/organizations/{organization_id}/tutor-data-policy",
                headers=_headers(identity),
                json={"retention_days": 30, "expected_version": 0},
            )
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"

        invalid = client.patch(
            f"/organizations/{organization_id}/tutor-data-policy",
            headers=_headers("admin@local.test"),
            json={"retention_days": 60, "expected_version": 0},
        )
        assert invalid.status_code == 422
        updated = client.patch(
            f"/organizations/{organization_id}/tutor-data-policy",
            headers=_headers("admin@local.test"),
            json={"retention_days": 30, "expected_version": 0},
        )
        assert updated.status_code == 200
        assert updated.json()["retention_days"] == 30
        assert updated.json()["version"] == 1
        stale = client.patch(
            f"/organizations/{organization_id}/tutor-data-policy",
            headers=_headers("admin@local.test"),
            json={"retention_days": 180, "expected_version": 0},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "tutor_data_policy_version_conflict"
        effective = client.get(
            f"/courses/{course_id}/tutor-data-policy",
            headers=_headers("student@local.test"),
        ).json()
        assert (effective["retention_days"], effective["version"]) == (30, 1)

        with Session() as db:
            events = db.query(OrganizationTutorDataPolicyEvent).all()
            assert len(events) == 1
            event = events[0]
            assert event.previous_state == {"retention_days": 90, "version": 0}
            assert event.new_state == {"retention_days": 30, "version": 1}
            assert {
                "question",
                "answer",
                "citations",
                "comment",
                "source_text",
            }.isdisjoint(event.previous_state | event.new_state)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_student_deletes_only_owned_history_and_content_free_receipt(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        course_id, organization_id = _bootstrap_course(client)
        created = client.post(
            f"/courses/{course_id}/qa",
            headers=_headers("student@local.test"),
            json={"question": "Как работает quicksort?", "language": "ru"},
        )
        assert created.status_code == 201
        own_answer_id = created.json()["id"]
        feedback = client.patch(
            f"/qa/answers/{own_answer_id}",
            headers=_headers("student@local.test"),
            json={"status": "helpful", "comment": "Private feedback text"},
        )
        assert feedback.status_code == 200

        with Session() as db:
            student = db.query(User).filter(User.email == "student@local.test").one()
            peer = User(
                email="peer-delete@local.test",
                display_name="Peer Delete",
                is_active=True,
            )
            db.add(peer)
            db.flush()
            db.add_all(
                [
                    OrganizationMembership(
                        organization_id=organization_id,
                        user_id=peer.id,
                        role="student",
                        is_active=True,
                    ),
                    CourseMembership(
                        organization_id=organization_id,
                        course_id=course_id,
                        user_id=peer.id,
                        role="student",
                        is_active=True,
                    ),
                    _answer(
                        course_id=course_id,
                        user_id=peer.id,
                        question="Peer private question",
                    ),
                ]
            )
            db.commit()
            student_id = student.id

        invalid = client.request(
            "DELETE",
            f"/courses/{course_id}/qa/history",
            headers=_headers("student@local.test"),
            json={"confirmation": "delete_everything"},
        )
        assert invalid.status_code == 422
        staff_denied = client.request(
            "DELETE",
            f"/courses/{course_id}/qa/history",
            headers=_headers("instructor@local.test"),
            json={"confirmation": "delete_my_tutor_history"},
        )
        assert staff_denied.status_code == 404

        # Authorization is repeated at the service boundary so a caller cannot
        # delete data by pairing an unrelated organization or membership state.
        with Session() as db:
            other_org = Organization(
                slug="unrelated-delete-org",
                name="Unrelated delete org",
                is_active=True,
            )
            db.add(other_org)
            db.flush()
            with pytest.raises(TutorDataScopeDenied):
                delete_owned_tutor_history(
                    db,
                    organization_id=other_org.id,
                    course_id=course_id,
                    user_id=student_id,
                )

            membership = (
                db.query(CourseMembership)
                .filter(
                    CourseMembership.organization_id == organization_id,
                    CourseMembership.course_id == course_id,
                    CourseMembership.user_id == student_id,
                )
                .one()
            )
            membership.is_active = False
            db.flush()
            with pytest.raises(TutorDataScopeDenied):
                delete_owned_tutor_history(
                    db,
                    organization_id=organization_id,
                    course_id=course_id,
                    user_id=student_id,
                )
            assert db.get(CourseQuestionAnswer, own_answer_id) is not None
            membership.is_active = True
            db.commit()

        deleted = client.request(
            "DELETE",
            f"/courses/{course_id}/qa/history",
            headers=_headers("student@local.test"),
            json={"confirmation": "delete_my_tutor_history"},
        )
        assert deleted.status_code == 200
        payload = deleted.json()
        assert payload["reason"] == "student_request"
        assert payload["answers_deleted"] == 1
        assert payload["feedback_events_deleted"] == 1
        assert {
            "question",
            "answer",
            "citations",
            "comment",
            "actor_user_id",
            "subject_user_id",
        }.isdisjoint(payload)
        own_history = client.get(
            f"/courses/{course_id}/qa",
            headers=_headers("student@local.test"),
        )
        assert own_history.json() == []

        evidence = client.get(
            f"/courses/{course_id}/evidence-pack/download",
            headers=_headers("instructor@local.test"),
        )
        assert evidence.status_code == 200
        with ZipFile(BytesIO(evidence.content)) as archive:
            qa_history = archive.read("qa-history.json").decode("utf-8")
        assert "Как работает quicksort?" not in qa_history
        assert "Private feedback text" not in qa_history
        assert "Peer private question" in qa_history

        quality = client.get(
            f"/courses/{course_id}/teacher-workspace",
            headers=_headers("instructor@local.test"),
        ).json()["tutor_quality"]
        assert quality["questions_total"] == 1

        with Session() as db:
            assert db.get(CourseQuestionAnswer, own_answer_id) is None
            assert (
                db.query(CourseQaFeedbackEvent)
                .filter(CourseQaFeedbackEvent.answer_id == own_answer_id)
                .count()
                == 0
            )
            receipt = db.query(TutorDataDeletionEvent).one()
            assert receipt.organization_id == organization_id
            assert receipt.course_id == course_id
            assert receipt.actor_user_id == student_id
            assert receipt.subject_user_id == student_id
            assert receipt.answers_deleted == 1
            assert receipt.feedback_events_deleted == 1
            assert not hasattr(receipt, "question")
            assert not hasattr(receipt, "answer")
            assert not hasattr(receipt, "comment")

        repeated = client.request(
            "DELETE",
            f"/courses/{course_id}/qa/history",
            headers=_headers("student@local.test"),
            json={"confirmation": "delete_my_tutor_history"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["answers_deleted"] == 0
        with Session() as db:
            assert db.query(TutorDataDeletionEvent).count() == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_retention_purge_respects_cutoff_organization_and_scheduled_task(
    monkeypatch,
):
    client, engine, Session = _client(monkeypatch)
    try:
        course_id, organization_id = _bootstrap_course(client)
        policy = client.patch(
            f"/organizations/{organization_id}/tutor-data-policy",
            headers=_headers("admin@local.test"),
            json={"retention_days": 30, "expected_version": 0},
        )
        assert policy.status_code == 200
        now = datetime.now(timezone.utc)
        with Session() as db:
            student = db.query(User).filter(User.email == "student@local.test").one()
            old = _answer(
                course_id=course_id,
                user_id=student.id,
                question="Expired private question",
                created_at=now - timedelta(days=31),
            )
            recent = _answer(
                course_id=course_id,
                user_id=student.id,
                question="Recent private question",
                created_at=now - timedelta(days=29),
            )
            other_org = Organization(
                slug="other-retention-org",
                name="Other retention org",
                is_active=True,
            )
            other_dataset = Dataset(name="other-retention-dataset")
            db.add_all([old, recent, other_org, other_dataset])
            db.flush()
            other_course = Course(
                organization_id=other_org.id,
                dataset_id=other_dataset.id,
                title="Other course",
            )
            db.add(other_course)
            db.flush()
            other_old = _answer(
                course_id=other_course.id,
                user_id=student.id,
                question="Other organization private question",
                created_at=now - timedelta(days=91),
            )
            db.add(other_old)
            db.flush()
            db.add(
                CourseQaFeedbackEvent(
                    answer_id=old.id,
                    course_id=course_id,
                    reviewed_by_user_id=student.id,
                    from_status="unreviewed",
                    to_status="helpful",
                    reviewed_by=student.email,
                    comment="Expired private feedback",
                )
            )
            db.commit()
            old_id, recent_id, other_old_id = old.id, recent.id, other_old.id

        stale = client.post(
            f"/organizations/{organization_id}/tutor-data-policy/purge",
            headers=_headers("admin@local.test"),
            json={
                "confirmation": "purge_expired_tutor_history",
                "expected_version": 0,
            },
        )
        assert stale.status_code == 409
        purged = client.post(
            f"/organizations/{organization_id}/tutor-data-policy/purge",
            headers=_headers("admin@local.test"),
            json={
                "confirmation": "purge_expired_tutor_history",
                "expected_version": 1,
            },
        )
        assert purged.status_code == 200
        assert purged.json()["reason"] == "admin_purge"
        assert purged.json()["policy_version"] == 1
        assert purged.json()["answers_deleted"] == 1
        assert purged.json()["feedback_events_deleted"] == 1
        with Session() as db:
            assert db.get(CourseQuestionAnswer, old_id) is None
            assert db.get(CourseQuestionAnswer, recent_id) is not None
            assert db.get(CourseQuestionAnswer, other_old_id) is not None

        monkeypatch.setattr("backend.app.tasks.tasks.SessionLocal", Session)
        task_result = purge_expired_tutor_history_task.run()
        assert task_result == {
            "organizations_checked": 2,
            "answers_deleted": 1,
            "feedback_events_deleted": 0,
        }
        with Session() as db:
            assert db.get(CourseQuestionAnswer, other_old_id) is None
            assert db.get(CourseQuestionAnswer, recent_id) is not None
            reasons = [
                reason
                for (reason,) in db.query(TutorDataDeletionEvent.reason)
                .order_by(TutorDataDeletionEvent.id)
                .all()
            ]
            assert reasons == ["admin_purge", "automatic_retention"]

        schedule = celery_app.conf.beat_schedule["purge-expired-tutor-history-daily"]
        assert schedule["task"] == "purge_expired_tutor_history"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
