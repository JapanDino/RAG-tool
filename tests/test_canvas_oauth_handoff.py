from urllib.parse import parse_qs, urlparse

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
    CanvasOAuthAttempt,
    CanvasOAuthConfiguration,
    CanvasOAuthConnection,
    CanvasOAuthEvent,
    Course,
    CourseMembership,
    Dataset,
    LtiContextBinding,
    LtiRegistration,
    Organization,
    User,
)
from backend.app.services import canvas_oauth as canvas_oauth_service
from backend.app.services.canvas_oauth import (
    CanvasOAuthError,
    reset_development_canvas_oauth,
)
from backend.app.services.canvas_sync import CANVAS_READ_SCOPES
from backend.app.services.product_session import (
    csrf_token_for_session,
    issue_product_session,
)


@pytest.fixture()
def handoff_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    monkeypatch.setenv("LTI_TOOL_PUBLIC_URL", "http://localhost")
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "http://frontend.test")
    monkeypatch.setenv(
        "LTI_SESSION_CSRF_SECRET", "handoff-test-csrf-secret-at-least-32-chars"
    )
    reset_development_canvas_oauth()

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
        organization = Organization(
            slug="oauth-handoff-school",
            name="OAuth Handoff School",
            is_active=True,
        )
        dataset = Dataset(name="oauth-handoff-course")
        teacher = User(
            email="teacher@handoff.test",
            display_name="Canvas Teacher",
            is_active=True,
        )
        student = User(
            email="student@handoff.test",
            display_name="Canvas Student",
            is_active=True,
        )
        db.add_all([organization, dataset, teacher, student])
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            external_id="314",
            title="Applied Evidence",
            description="Bound current course",
            source_type="canvas",
            source_url="https://canvas.school.test/courses/314",
        )
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer="https://canvas.school.test",
            client_id="lti-handoff-client",
            deployment_id="lti-handoff-deployment",
            authorization_endpoint="https://canvas.school.test/authorize",
            jwks_url="https://canvas.school.test/jwks",
            tool_launch_url="http://localhost/integrations/lti/launch",
            is_active=True,
            is_development=False,
        )
        db.add_all([course, registration])
        db.flush()
        db.add_all(
            [
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=teacher.id,
                    role="instructor",
                    is_active=True,
                ),
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=student.id,
                    role="student",
                    is_active=True,
                ),
                LtiContextBinding(
                    registration_id=registration.id,
                    course_id=course.id,
                    platform_context_id="canvas-course-314",
                ),
                CanvasOAuthConfiguration(
                    registration_id=registration.id,
                    organization_id=organization.id,
                    canvas_api_origin="https://canvas.school.test",
                    oauth_client_id="canvas-read-client",
                    version=1,
                ),
            ]
        )
        db.commit()
        issued = issue_product_session(
            db,
            registration_id=registration.id,
            user_id=teacher.id,
            course_id=course.id,
            role="instructor",
        )
        values = {
            "organization_id": organization.id,
            "registration_id": registration.id,
            "course_id": course.id,
            "teacher_id": teacher.id,
            "student_id": student.id,
            "session_id": issued.row.id,
            "raw_session": issued.raw_token,
        }

    client = TestClient(app, base_url="http://localhost")
    client.cookies.set("rag_lti_session", values["raw_session"])
    yield client, Session, values
    app.dependency_overrides.clear()
    reset_development_canvas_oauth()
    engine.dispose()


def _csrf(values: dict) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token_for_session(values["raw_session"])}


def _root(values: dict) -> str:
    return f"/courses/{values['course_id']}/canvas-oauth-handoff"


def _authorization_redirect(client: TestClient, authorization_url: str, decision: str):
    parsed = urlparse(authorization_url)
    params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    consent = client.get(parsed.path, params=params)
    assert consent.status_code == 200
    assert "Canvas не вызывается" in consent.text
    return client.get(
        parsed.path,
        params={**params, "decision": decision},
        follow_redirects=False,
    )


def _start(client: TestClient, values: dict) -> str:
    response = client.post(f"{_root(values)}/start", headers=_csrf(values))
    assert response.status_code == 200
    return response.json()["authorization_url"]


def test_instructor_connects_fake_provider_preview_and_disconnects(handoff_client):
    client, Session, values = handoff_client
    status = client.get(_root(values))
    assert status.status_code == 200
    assert status.headers["cache-control"] == "no-store, max-age=0"
    assert status.json()["state"] == "ready_to_connect"

    before = client.get(f"/courses/{values['course_id']}/canvas-sync-preview")
    assert before.status_code == 200
    assert before.json()["state"] == "oauth_required"

    allowed = _authorization_redirect(client, _start(client, values), "allow")
    assert allowed.status_code == 302
    callback = client.get(allowed.headers["location"], follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == (
        f"http://frontend.test/workspace/courses/{values['course_id']}"
        "?lti=1&canvas_oauth=connected"
    )

    connected = client.get(_root(values)).json()
    assert connected["state"] == "connected"
    assert connected["connection"]["mode"] == "fake_development"
    preview = client.get(f"/courses/{values['course_id']}/canvas-sync-preview")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["state"] == "ready"
    assert payload["schema_version"] == 2
    assert payload["manifest"]["course_title"] == "Applied Evidence"
    assert payload["manifest"]["provenance"] == {
        "kind": "synthetic_development",
        "canvas_contacted": False,
        "generator_version": "canvas-manifest-v1",
    }
    totals = {group["kind"]: group["total"] for group in payload["manifest"]["groups"]}
    assert min(totals["modules"], totals["pages"], totals["assignments"]) > 0

    with Session() as db:
        attempt = db.query(CanvasOAuthAttempt).one()
        assert attempt.flow_kind == "instructor"
        assert attempt.product_session_id == values["session_id"]
        assert attempt.course_id == values["course_id"]
        assert attempt.canvas_course_id == "314"
        connection = db.query(CanvasOAuthConnection).one()
        assert connection.user_id == values["teacher_id"]
        assert db.query(CanvasOAuthEvent).filter_by(event_type="connected").count() == 1
        serialized = str(connected) + str(payload)
        assert attempt.state_digest not in serialized
        assert connection.vault_reference not in serialized

    disconnected = client.post(f"{_root(values)}/disconnect", headers=_csrf(values))
    assert disconnected.status_code == 200
    assert disconnected.json() == {"schema_version": 1, "state": "disconnected"}
    after = client.get(f"/courses/{values['course_id']}/canvas-sync-preview")
    assert after.json()["state"] == "oauth_required"
    with Session() as db:
        assert db.query(CanvasOAuthConfiguration).count() == 1
        assert db.query(CanvasOAuthConnection).one().revoked_at is not None


def test_denial_returns_to_exact_course_consumes_state_and_replay_fails(
    handoff_client,
):
    client, Session, values = handoff_client
    denied = _authorization_redirect(client, _start(client, values), "deny")
    callback_url = denied.headers["location"]
    callback = client.get(callback_url, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"].endswith(
        f"/workspace/courses/{values['course_id']}?lti=1&canvas_oauth=denied"
    )
    replay = client.get(callback_url, follow_redirects=False)
    assert replay.status_code == 400
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None


def test_handoff_requires_csrf_exact_instructor_and_configuration(handoff_client):
    client, Session, values = handoff_client
    assert client.post(f"{_root(values)}/start").status_code == 403

    with Session() as db:
        configuration = db.query(CanvasOAuthConfiguration).one()
        configuration.canvas_api_origin = "https://other-canvas.school.test"
        db.commit()
    mismatch = client.get(_root(values))
    assert mismatch.status_code == 200
    assert mismatch.json()["state"] == "configuration_mismatch"
    blocked = client.post(f"{_root(values)}/start", headers=_csrf(values))
    assert blocked.status_code == 409

    with Session() as db:
        db.query(CanvasOAuthConfiguration).delete()
        db.commit()
    required = client.get(_root(values))
    assert required.status_code == 200
    assert required.json()["state"] == "configuration_required"

    with Session() as db:
        student_session = issue_product_session(
            db,
            registration_id=values["registration_id"],
            user_id=values["student_id"],
            course_id=values["course_id"],
            role="student",
        )
    client.cookies.set("rag_lti_session", student_session.raw_token)
    student = client.post(
        f"{_root(values)}/start",
        headers={"X-CSRF-Token": csrf_token_for_session(student_session.raw_token)},
    )
    assert student.status_code == 404


@pytest.mark.parametrize("change", ["session", "source", "configuration"])
def test_callback_fails_to_exact_course_when_authorization_changes(
    handoff_client, change
):
    client, Session, values = handoff_client
    allowed = _authorization_redirect(client, _start(client, values), "allow")
    with Session() as db:
        if change == "session":
            issue_product_session(
                db,
                registration_id=values["registration_id"],
                user_id=values["teacher_id"],
                course_id=values["course_id"],
                role="instructor",
            )
        elif change == "source":
            course = db.get(Course, values["course_id"])
            course.source_url = "https://canvas.school.test/courses/999"
            db.commit()
        else:
            configuration = db.query(CanvasOAuthConfiguration).one()
            configuration.canvas_api_origin = "https://changed.school.test"
            db.commit()
    callback = client.get(allowed.headers["location"], follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"].endswith(
        f"/workspace/courses/{values['course_id']}?lti=1&canvas_oauth=failed"
    )
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None


@pytest.mark.parametrize("failure", ["invalid_code", "secret_store"])
def test_post_consumption_failure_returns_to_exact_instructor_course(
    handoff_client, monkeypatch, failure
):
    client, Session, values = handoff_client
    authorization_url = _start(client, values)
    parsed = urlparse(authorization_url)
    params = {key: items[0] for key, items in parse_qs(parsed.query).items()}
    if failure == "invalid_code":
        callback_url = (
            f"/integrations/canvas/oauth/callback?state={params['state']}"
            "&code=invalid"
        )
    else:
        callback_url = _authorization_redirect(
            client, authorization_url, "allow"
        ).headers["location"]

        def unavailable_store(reference: str, material: bytes) -> None:
            del reference, material
            raise CanvasOAuthError("secret_store_unavailable")

        monkeypatch.setattr(
            canvas_oauth_service._development_store, "put", unavailable_store
        )

    callback = client.get(callback_url, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"].endswith(
        f"/workspace/courses/{values['course_id']}?lti=1&canvas_oauth=failed"
    )
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None


@pytest.mark.parametrize(
    "granted_scopes",
    [
        list(CANVAS_READ_SCOPES[:-1]),
        [*CANVAS_READ_SCOPES, "url:GET|/api/v1/courses/:course_id/grades"],
        "not-a-scope-list",
    ],
)
def test_connected_status_rejects_non_exact_or_malformed_scopes(
    handoff_client, granted_scopes
):
    client, Session, values = handoff_client
    allowed = _authorization_redirect(client, _start(client, values), "allow")
    assert (
        client.get(allowed.headers["location"], follow_redirects=False).status_code
        == 303
    )
    with Session() as db:
        connection = db.query(CanvasOAuthConnection).one()
        connection.granted_scopes = granted_scopes
        db.commit()

    status = client.get(_root(values))
    assert status.status_code == 200
    assert status.json()["state"] == "reconnect_required"
    preview = client.get(f"/courses/{values['course_id']}/canvas-sync-preview")
    assert preview.status_code == 200
    assert preview.json()["state"] == "oauth_required"


def test_process_restart_requires_reconnect_without_disclosing_vault(handoff_client):
    client, _, values = handoff_client
    allowed = _authorization_redirect(client, _start(client, values), "allow")
    assert (
        client.get(allowed.headers["location"], follow_redirects=False).status_code
        == 303
    )
    reset_development_canvas_oauth()
    status = client.get(_root(values))
    assert status.status_code == 200
    assert status.json()["state"] == "reconnect_required"
    preview = client.get(f"/courses/{values['course_id']}/canvas-sync-preview")
    assert preview.json()["state"] == "oauth_required"


def test_local_lti_registration_can_exercise_only_the_fake_handoff(handoff_client):
    client, Session, values = handoff_client
    with Session() as db:
        registration = db.get(LtiRegistration, values["registration_id"])
        registration.is_development = True
        db.commit()
    allowed = _authorization_redirect(client, _start(client, values), "allow")
    callback = client.get(allowed.headers["location"], follow_redirects=False)
    assert callback.status_code == 303
    assert "canvas_oauth=connected" in callback.headers["location"]
    disconnected = client.post(f"{_root(values)}/disconnect", headers=_csrf(values))
    assert disconnected.status_code == 200


def test_instructor_handoff_is_visible_but_disabled_outside_safe_development(
    handoff_client, monkeypatch
):
    client, _, values = handoff_client
    monkeypatch.setenv("AUTH_MODE", "external")
    status = client.get(_root(values))
    assert status.status_code == 200
    assert status.json()["state"] == "production_disabled"
    assert status.json()["fake_flow_available"] is False
    start = client.post(f"{_root(values)}/start", headers=_csrf(values))
    assert start.status_code == 409
