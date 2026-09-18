from datetime import UTC, datetime, timedelta

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
    Dataset,
    LtiBindingCandidate,
    LtiBindingEvent,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services.lti_binding import (
    capture_unbound_candidates,
    expire_overdue_binding_candidates,
)
from backend.app.tasks.celery_app import celery_app


@pytest.fixture()
def binding_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
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
    with Session() as db:
        school = Organization(slug="binding-school", name="Binding School")
        other = Organization(slug="binding-other", name="Other School")
        first_dataset = Dataset(name="binding-course")
        other_dataset = Dataset(name="binding-other-course")
        db.add_all([school, other, first_dataset, other_dataset])
        db.flush()
        course = Course(
            organization_id=school.id,
            dataset_id=first_dataset.id,
            title="Algorithms",
            source_type="manual",
        )
        other_course = Course(
            organization_id=other.id,
            dataset_id=other_dataset.id,
            title="Hidden course",
            source_type="manual",
        )
        db.add_all([course, other_course])
        db.flush()
        users = {}
        for email, organization_id, role in (
            ("admin@binding.test", school.id, "administrator"),
            ("teacher@binding.test", school.id, "instructor"),
            ("other-admin@binding.test", other.id, "administrator"),
        ):
            user = User(email=email, display_name=email, is_active=True)
            db.add(user)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=user.id,
                    role=role,
                    is_active=True,
                )
            )
            users[email] = user.id
        db.add(
            CourseMembership(
                organization_id=school.id,
                course_id=course.id,
                user_id=users["teacher@binding.test"],
                role="instructor",
                is_active=True,
            )
        )
        registration = LtiRegistration(
            organization_id=school.id,
            issuer="https://canvas.school.test",
            client_id="binding-client",
            deployment_id="binding-deployment",
            authorization_endpoint="https://canvas.school.test/api/lti/authorize",
            jwks_url="https://canvas.school.test/api/lti/security/jwks",
            tool_launch_url="https://tool.school.test/integrations/lti/launch",
            is_active=True,
            is_development=False,
        )
        db.add(registration)
        db.commit()
        values = {
            "organization_id": school.id,
            "other_organization_id": other.id,
            "course_id": course.id,
            "other_course_id": other_course.id,
            "registration_id": registration.id,
            "teacher_id": users["teacher@binding.test"],
            "user_count": db.query(User).count(),
            "course_count": db.query(Course).count(),
            "membership_count": db.query(OrganizationMembership).count()
            + db.query(CourseMembership).count(),
        }
    yield TestClient(app), Session, values
    app.dependency_overrides.clear()
    engine.dispose()


def _headers(email="admin@binding.test"):
    return {"X-Dev-User": email}


def _base(values):
    return (
        f"/integrations/lti/organizations/{values['organization_id']}"
        f"/registrations/{values['registration_id']}/binding-candidates"
    )


def _capture(Session, values, *, subject="opaque-subject", context="opaque-context"):
    with Session() as db:
        registration = db.get(LtiRegistration, values["registration_id"])
        assert registration is not None
        capture_unbound_candidates(
            db, registration=registration, subject=subject, context_id=context
        )
        db.commit()


def test_candidates_are_masked_deduplicated_and_scoped(binding_client):
    client, Session, values = binding_client
    _capture(Session, values)
    _capture(Session, values)

    response = client.get(_base(values), headers=_headers())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["candidate_type"] for item in payload["candidates"]} == {
        "subject",
        "context",
    }
    assert all(len(item["identifier_hint"]) == 12 for item in payload["candidates"])
    assert all(item["seen_count"] == 2 for item in payload["candidates"])
    assert "opaque-subject" not in response.text
    assert "opaque-context" not in response.text
    assert {item["email"] for item in payload["users"]} == {
        "admin@binding.test",
        "teacher@binding.test",
    }
    assert payload["courses"] == [{"id": values["course_id"], "title": "Algorithms"}]

    denied = client.get(_base(values), headers=_headers("teacher@binding.test"))
    assert denied.status_code == 404
    cross = client.get(
        _base(values).replace(
            f"organizations/{values['organization_id']}",
            f"organizations/{values['other_organization_id']}",
        ),
        headers=_headers("other-admin@binding.test"),
    )
    assert cross.status_code == 404


def test_explicit_binding_clears_plaintext_and_creates_no_domain_objects(
    binding_client,
):
    client, Session, values = binding_client
    _capture(Session, values)
    payload = client.get(_base(values), headers=_headers()).json()
    subject = next(
        item for item in payload["candidates"] if item["candidate_type"] == "subject"
    )
    context = next(
        item for item in payload["candidates"] if item["candidate_type"] == "context"
    )

    subject_result = client.post(
        f"{_base(values)}/{subject['id']}/bind",
        headers=_headers(),
        json={"target_id": values["teacher_id"]},
    )
    context_result = client.post(
        f"{_base(values)}/{context['id']}/bind",
        headers=_headers(),
        json={"target_id": values["course_id"]},
    )
    assert subject_result.status_code == 200, subject_result.text
    assert context_result.status_code == 200, context_result.text
    assert subject_result.json()["status"] == "bound"
    assert context_result.json()["status"] == "bound"

    with Session() as db:
        assert db.query(LtiSubjectBinding).one().platform_subject == "opaque-subject"
        assert db.query(LtiContextBinding).one().platform_context_id == "opaque-context"
        candidates = db.query(LtiBindingCandidate).all()
        assert all(item.platform_identifier is None for item in candidates)
        assert all(item.status == "bound" for item in candidates)
        assert db.query(LtiBindingEvent).count() == 2
        assert db.query(User).count() == values["user_count"]
        assert db.query(Course).count() == values["course_count"]
        assert (
            db.query(OrganizationMembership).count()
            + db.query(CourseMembership).count()
            == values["membership_count"]
        )

    repeated = client.post(
        f"{_base(values)}/{subject['id']}/bind",
        headers=_headers(),
        json={"target_id": values["teacher_id"]},
    )
    assert repeated.status_code == 409


def test_cross_scope_target_and_dismissal_fail_safe(binding_client):
    client, Session, values = binding_client
    _capture(Session, values, subject="subject-two", context="context-two")
    payload = client.get(_base(values), headers=_headers()).json()
    context = next(
        item for item in payload["candidates"] if item["candidate_type"] == "context"
    )
    cross = client.post(
        f"{_base(values)}/{context['id']}/bind",
        headers=_headers(),
        json={"target_id": values["other_course_id"]},
    )
    assert cross.status_code == 404

    dismissed = client.post(
        f"{_base(values)}/{context['id']}/dismiss", headers=_headers()
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    with Session() as db:
        row = db.get(LtiBindingCandidate, context["id"])
        assert row is not None
        assert row.platform_identifier is None
        assert row.status == "dismissed"
        assert db.query(LtiBindingEvent).one().event_type == "dismissed"


def test_expired_candidate_is_not_returned_or_resolved(binding_client):
    client, Session, values = binding_client
    _capture(Session, values)
    with Session() as db:
        candidate = (
            db.query(LtiBindingCandidate)
            .filter(LtiBindingCandidate.candidate_type == "subject")
            .one()
        )
        candidate.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        candidate_id = candidate.id
        db.commit()

    payload = client.get(_base(values), headers=_headers()).json()
    assert candidate_id not in {item["id"] for item in payload["candidates"]}
    rejected = client.post(
        f"{_base(values)}/{candidate_id}/bind",
        headers=_headers(),
        json={"target_id": values["teacher_id"]},
    )
    assert rejected.status_code == 409
    with Session() as db:
        candidate = db.get(LtiBindingCandidate, candidate_id)
        assert candidate is not None
        assert candidate.status == "expired"
        assert candidate.platform_identifier is None


def test_scheduled_expiry_clears_plaintext_without_launch_or_admin_read(
    binding_client,
):
    _, Session, values = binding_client
    _capture(Session, values)
    now = datetime.now(UTC)
    with Session() as db:
        candidates = (
            db.query(LtiBindingCandidate).order_by(LtiBindingCandidate.id).all()
        )
        candidates[0].expires_at = now - timedelta(minutes=2)
        candidates[1].expires_at = now - timedelta(minutes=1)
        db.commit()

    with Session() as db:
        assert expire_overdue_binding_candidates(db, limit=1, now=now) == 1
        db.commit()
    with Session() as db:
        rows = db.query(LtiBindingCandidate).order_by(LtiBindingCandidate.id).all()
        assert [row.status for row in rows].count("expired") == 1
        assert [row.platform_identifier for row in rows].count(None) == 1

        assert expire_overdue_binding_candidates(db, now=now) == 1
        db.commit()
        assert all(row.status == "expired" for row in rows)
        assert all(row.platform_identifier is None for row in rows)

    schedule = celery_app.conf.beat_schedule["expire-lti-binding-candidates-hourly"]
    assert schedule["task"] == "expire_lti_binding_candidates"
