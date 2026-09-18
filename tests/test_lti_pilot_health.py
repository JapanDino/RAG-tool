import json
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
    LtiBindingCandidate,
    LtiLaunchAuditEvent,
    LtiRegistration,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services.lti_pilot_health import pilot_launch_health

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _registration(db, organization_id, suffix, *, active=True, development=False):
    row = LtiRegistration(
        organization_id=organization_id,
        issuer=f"https://canvas-{suffix}.school.test",
        client_id=f"client-{suffix}",
        deployment_id=f"deployment-{suffix}",
        authorization_endpoint=f"https://canvas-{suffix}.school.test/authorize",
        jwks_url=f"https://canvas-{suffix}.school.test/jwks",
        tool_launch_url="https://tool.school.test/integrations/lti/launch",
        is_active=active,
        is_development=development,
    )
    db.add(row)
    db.flush()
    return row


def _event(db, registration, outcome, reason, created_at, *, organization_id=None):
    row = LtiLaunchAuditEvent(
        registration_id=registration.id,
        organization_id=organization_id or registration.organization_id,
        outcome=outcome,
        reason_code=reason,
        created_at=created_at,
    )
    db.add(row)
    return row


def _candidate(
    db,
    registration,
    candidate_type,
    suffix,
    *,
    status="pending",
    expires_at=None,
):
    row = LtiBindingCandidate(
        registration_id=registration.id,
        organization_id=registration.organization_id,
        candidate_type=candidate_type,
        identifier_digest=(suffix * 64)[:64],
        platform_identifier=f"raw-platform-{suffix}",
        status=status,
        seen_count=1,
        first_seen_at=NOW - timedelta(hours=2),
        last_seen_at=NOW - timedelta(hours=1),
        expires_at=expires_at or NOW + timedelta(hours=4),
    )
    db.add(row)
    return row


@pytest.fixture()
def pilot_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as db:
        yield db
    engine.dispose()


def test_pilot_health_is_aggregate_bounded_and_content_minimal(pilot_db):
    first = Organization(slug="pilot-one", name="Pilot one", is_active=True)
    second = Organization(slug="pilot-two", name="Pilot two", is_active=True)
    pilot_db.add_all([first, second])
    pilot_db.flush()
    first_registration = _registration(pilot_db, first.id, "one")
    second_registration = _registration(pilot_db, second.id, "two")

    recent = (
        ("accepted", "launch_verified"),
        ("rejected", "binding_unavailable"),
        ("rejected", "binding_unavailable"),
        ("rejected", "token_invalid"),
        ("rejected", "future_internal_reason"),
        ("accepted", "launch_verified"),
    )
    for index, (outcome, reason) in enumerate(recent):
        _event(
            pilot_db,
            first_registration,
            outcome,
            reason,
            NOW - timedelta(hours=index + 1),
        )
    _event(
        pilot_db,
        first_registration,
        "rejected",
        "token_invalid",
        NOW - timedelta(days=8),
    )
    _event(
        pilot_db,
        second_registration,
        "accepted",
        "launch_verified",
        NOW - timedelta(minutes=30),
    )
    _candidate(pilot_db, first_registration, "subject", "a")
    _candidate(pilot_db, first_registration, "context", "b")
    _candidate(
        pilot_db,
        first_registration,
        "subject",
        "c",
        expires_at=NOW - timedelta(minutes=1),
    )
    _candidate(pilot_db, first_registration, "context", "d", status="bound")
    pilot_db.commit()

    report = pilot_launch_health(pilot_db, organization_id=first.id, now=NOW)

    assert report["state"] == "review_bindings"
    assert report["known_launches"] == 6
    assert report["accepted_launches"] == 2
    assert report["rejected_launches"] == 4
    assert report["active_registrations"] == 1
    assert report["pending_bindings"] == {
        "total": 2,
        "subjects": 1,
        "contexts": 1,
    }
    assert report["failure_families"] == [
        {"code": "binding_required", "count": 2},
        {"code": "other", "count": 1},
        {"code": "signature_or_replay", "count": 1},
    ]
    assert report["pause_triggers"] == []
    encoded = json.dumps(report, default=str)
    assert "raw-platform" not in encoded
    assert "binding_unavailable" not in encoded
    assert "token_invalid" not in encoded
    assert "future_internal_reason" not in encoded
    assert "canvas-one" not in encoded


def test_pilot_health_pause_triggers_require_repeated_evidence(pilot_db):
    organization = Organization(slug="paused-pilot", name="Paused", is_active=True)
    pilot_db.add(organization)
    pilot_db.flush()
    registration = _registration(pilot_db, organization.id, "paused")
    for index in range(5):
        _event(
            pilot_db,
            registration,
            "rejected",
            "state_invalid",
            NOW - timedelta(minutes=index + 1),
        )
    pilot_db.commit()

    report = pilot_launch_health(pilot_db, organization_id=organization.id, now=NOW)

    assert report["state"] == "review_failures"
    assert report["pause_triggers"] == [
        "no_verified_launch",
        "repeated_rejections",
    ]
    assert report["failure_families"] == [{"code": "signature_or_replay", "count": 5}]


def test_pilot_health_distinguishes_not_started_and_stable(pilot_db):
    organization = Organization(slug="quiet-pilot", name="Quiet", is_active=True)
    pilot_db.add(organization)
    pilot_db.flush()
    registration = _registration(pilot_db, organization.id, "quiet")
    pilot_db.commit()

    empty = pilot_launch_health(pilot_db, organization_id=organization.id, now=NOW)
    assert empty["state"] == "not_started"
    assert empty["known_launches"] == 0

    _event(
        pilot_db,
        registration,
        "accepted",
        "launch_verified",
        NOW - timedelta(minutes=1),
    )
    pilot_db.commit()
    stable = pilot_launch_health(pilot_db, organization_id=organization.id, now=NOW)
    assert stable["state"] == "stable"
    assert stable["pause_triggers"] == []


def test_pilot_health_excludes_development_registration_traffic(pilot_db):
    organization = Organization(slug="mixed-pilot", name="Mixed", is_active=True)
    pilot_db.add(organization)
    pilot_db.flush()
    production = _registration(
        pilot_db,
        organization.id,
        "production",
        active=False,
    )
    development = _registration(
        pilot_db,
        organization.id,
        "development",
        development=True,
    )
    _event(
        pilot_db,
        production,
        "accepted",
        "launch_verified",
        NOW - timedelta(minutes=10),
    )
    for index in range(5):
        _event(
            pilot_db,
            development,
            "rejected",
            "token_invalid",
            NOW - timedelta(minutes=index + 1),
        )
    _candidate(pilot_db, development, "subject", "x")
    pilot_db.commit()

    report = pilot_launch_health(pilot_db, organization_id=organization.id, now=NOW)

    assert report["state"] == "stable"
    assert report["known_launches"] == 1
    assert report["accepted_launches"] == 1
    assert report["rejected_launches"] == 0
    assert report["active_registrations"] == 0
    assert report["pending_bindings"]["total"] == 0
    assert report["failure_families"] == []
    assert report["pause_triggers"] == []


@pytest.fixture()
def pilot_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "development")
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
        first = Organization(slug="api-pilot-one", name="First", is_active=True)
        second = Organization(slug="api-pilot-two", name="Second", is_active=True)
        db.add_all([first, second])
        db.flush()
        users = []
        for email, organization_id, role in (
            ("admin-one@pilot.test", first.id, "administrator"),
            ("teacher-one@pilot.test", first.id, "instructor"),
            ("admin-two@pilot.test", second.id, "administrator"),
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
            users.append(user)
        first_registration = _registration(db, first.id, "api-one")
        second_registration = _registration(db, second.id, "api-two")
        _event(
            db,
            first_registration,
            "rejected",
            "token_invalid",
            datetime.now(UTC) - timedelta(minutes=2),
        )
        _event(
            db,
            second_registration,
            "accepted",
            "launch_verified",
            datetime.now(UTC) - timedelta(minutes=1),
        )
        db.commit()
        first_id = first.id
    client = TestClient(app)
    yield client, first_id
    app.dependency_overrides.clear()
    engine.dispose()


def test_pilot_health_api_is_administrator_only_and_organization_scoped(pilot_client):
    client, organization_id = pilot_client
    path = f"/integrations/lti/organizations/{organization_id}/pilot-health"

    allowed = client.get(path, headers={"X-Dev-User": "admin-one@pilot.test"})
    assert allowed.status_code == 200
    assert allowed.json()["known_launches"] == 1
    assert allowed.json()["accepted_launches"] == 0
    assert allowed.json()["failure_families"] == [
        {"code": "signature_or_replay", "count": 1}
    ]

    instructor = client.get(path, headers={"X-Dev-User": "teacher-one@pilot.test"})
    assert instructor.status_code == 404
    assert instructor.json() == {"detail": "resource not found"}

    other_admin = client.get(path, headers={"X-Dev-User": "admin-two@pilot.test"})
    assert other_admin.status_code == 404
    assert other_admin.json() == {"detail": "resource not found"}
