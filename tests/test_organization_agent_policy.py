from __future__ import annotations

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
    LtiRegistration,
    ModelInvocationEvent,
    Organization,
    OrganizationAgentPolicyEvent,
    OrganizationMembership,
    User,
)
from backend.app.schemas.organization_agent_policy import AgentPolicySettings
from backend.app.services.model_gateway import (
    COMPATIBILITY_TASK,
    ModelGateway,
    invoke_registered_model_task,
    model_gateway_configuration,
)
from backend.app.services.organization_agent_policy import update_agent_policy
from backend.app.services.product_session import (
    csrf_token_for_session,
    issue_product_session,
    session_cookie_policy,
)


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, *, settings, payload):
        self.calls.append(payload)
        return {
            "choices": [
                {"message": {"content": '{"status":"ok","detail":"host called"}'}}
            ]
        }


def _client(monkeypatch):
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
    return TestClient(app), Session, engine


def _seed(Session):
    with Session() as db:
        organization = Organization(slug="policy-school", name="Policy School")
        other = Organization(slug="policy-other", name="Other School")
        dataset = Dataset(name="policy-course-data")
        admin = User(email="policy-admin@test", display_name="Admin", is_active=True)
        teacher = User(
            email="policy-teacher@test", display_name="Teacher", is_active=True
        )
        student = User(
            email="policy-student@test", display_name="Student", is_active=True
        )
        foreign_admin = User(
            email="foreign-admin@test", display_name="Foreign", is_active=True
        )
        db.add_all(
            [organization, other, dataset, admin, teacher, student, foreign_admin]
        )
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            title="Policy Course",
        )
        db.add(course)
        db.flush()
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer="https://canvas.policy.test",
            client_id="policy-client",
            deployment_id="policy-deployment",
            authorization_endpoint="https://canvas.policy.test/auth",
            jwks_url="https://canvas.policy.test/jwks",
            tool_launch_url="http://testserver/integrations/lti/launch",
            is_active=True,
            is_development=True,
        )
        db.add(registration)
        db.flush()
        db.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=admin.id,
                    role="administrator",
                    is_active=True,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=teacher.id,
                    role="instructor",
                    is_active=True,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=student.id,
                    role="student",
                    is_active=True,
                ),
                OrganizationMembership(
                    organization_id=other.id,
                    user_id=foreign_admin.id,
                    role="administrator",
                    is_active=True,
                ),
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=student.id,
                    role="student",
                    is_active=True,
                ),
            ]
        )
        db.commit()
        return {
            "organization_id": organization.id,
            "course_id": course.id,
            "student_id": student.id,
            "registration_id": registration.id,
        }


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def _draft(**overrides):
    values = {
        "learner_enabled": False,
        "instructor_enabled": True,
        "program_enabled": False,
        "model_mode": "deterministic_only",
        "expected_version": 0,
    }
    values.update(overrides)
    return values


def test_admin_previews_and_applies_content_free_versioned_policy(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        values = _seed(Session)
        path = f"/organizations/{values['organization_id']}/agent-policy"
        default = client.get(path, headers=_headers("policy-admin@test"))
        assert default.status_code == 200
        assert default.json()["version"] == 0
        assert default.json()["learner_enabled"] is True
        assert default.json()["model_mode"] == "approved_host_with_safe_fallback"

        monkeypatch.setenv("AUTH_MODE", "disabled")
        compatibility_bypass = client.get(path)
        assert compatibility_bypass.status_code == 404
        compatibility_write = client.patch(
            path,
            json={**_draft(), "confirmation": "apply_agent_policy"},
        )
        assert compatibility_write.status_code == 404
        monkeypatch.setenv("AUTH_MODE", "development")

        for identity in ("policy-teacher@test", "foreign-admin@test"):
            denied = client.get(path, headers=_headers(identity))
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"

        preview = client.post(
            f"{path}/preview",
            headers=_headers("policy-admin@test"),
            json=_draft(),
        )
        assert preview.status_code == 200, preview.text
        assert [item["field"] for item in preview.json()["changes"]] == [
            "learner_enabled",
            "program_enabled",
            "model_mode",
        ]
        assert preview.json()["confirmation"] == "apply_agent_policy"
        with Session() as db:
            assert db.query(OrganizationAgentPolicyEvent).count() == 0

        invalid = client.patch(
            path,
            headers=_headers("policy-admin@test"),
            json={**_draft(), "confirmation": "yes", "api_key": "not-allowed"},
        )
        assert invalid.status_code == 422
        applied = client.patch(
            path,
            headers=_headers("policy-admin@test"),
            json={**_draft(), "confirmation": "apply_agent_policy"},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["version"] == 1
        assert applied.json()["learner_enabled"] is False
        assert applied.headers["cache-control"] == "no-store"

        stale = client.patch(
            path,
            headers=_headers("policy-admin@test"),
            json={
                **_draft(instructor_enabled=False),
                "confirmation": "apply_agent_policy",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "agent_policy_version_conflict"
        with Session() as db:
            event = db.query(OrganizationAgentPolicyEvent).one()
            serialized = repr(
                {"before": event.previous_state, "after": event.new_state}
            )
            assert event.version == 1
            for forbidden in ("message", "answer", "citation", "api_key", "prompt"):
                assert forbidden not in serialized.casefold()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_paused_learner_route_denies_new_and_unfinished_runs(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        values = _seed(Session)
        with Session() as db:
            issued = issue_product_session(
                db,
                registration_id=values["registration_id"],
                user_id=values["student_id"],
                course_id=values["course_id"],
                role="student",
            )
            raw_token = issued.raw_token
        client.cookies.set(session_cookie_policy().name, raw_token)
        csrf = csrf_token_for_session(raw_token)
        payload = {
            "contract_version": "agent.v1",
            "message": "Explain this material",
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "before-pause-0001"},
            json=payload,
        )
        assert accepted.status_code == 202, accepted.text

        with Session() as db:
            update_agent_policy(
                db,
                organization_id=values["organization_id"],
                proposed=AgentPolicySettings(learner_enabled=False),
                expected_version=0,
                actor_user_id=None,
            )
            db.commit()

        unfinished = client.post(
            accepted.json()["execute_url"],
            headers={"X-CSRF-Token": csrf},
            json=payload,
        )
        assert unfinished.status_code == 404
        assert unfinished.json()["error"]["code"] == "ACCESS_DENIED"
        denied = client.post(
            "/agent/v1/messages",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "after-pause-0001"},
            json=payload,
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "ACCESS_DENIED"

        governance = client.post(
            "/agent/v1/messages",
            headers={
                "X-Dev-User": "policy-admin@test",
                "Idempotency-Key": "governance-still-open-0001",
            },
            json={"contract_version": "agent.v1", "message": "integration readiness"},
        )
        assert governance.status_code == 202, governance.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_deterministic_model_mode_bypasses_supplied_school_transport(monkeypatch):
    _, Session, engine = _client(monkeypatch)
    try:
        values = _seed(Session)
        transport = RecordingTransport()
        configured = model_gateway_configuration(
            {
                "APP_ENV": "production",
                "AGENT_MODEL_ENABLED": "1",
                "AGENT_MODEL_BASE_URL": "https://models.school.test/v1",
                "AGENT_MODEL_ALLOWED_HOSTS": "models.school.test",
                "AGENT_MODEL_ID": "school-model",
                "AGENT_MODEL_API_KEY": "secret",
            }
        )
        with Session() as db:
            update_agent_policy(
                db,
                organization_id=values["organization_id"],
                proposed=AgentPolicySettings(model_mode="deterministic_only"),
                expected_version=0,
                actor_user_id=None,
            )
            outcome = invoke_registered_model_task(
                db,
                organization_id=values["organization_id"],
                task_name=COMPATIBILITY_TASK.name,
                input_data={"text": "private input"},
                gateway=ModelGateway(configured, transport=transport),
            )
            db.commit()
            event = db.query(ModelInvocationEvent).one()
        assert transport.calls == []
        assert outcome.data is None
        assert outcome.metadata.failure_class == "disabled"
        assert outcome.metadata.fallback_used is True
        assert event.status == "fallback"
        assert event.failure_class == "disabled"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
