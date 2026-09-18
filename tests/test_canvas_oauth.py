from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse

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
    LtiRegistration,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services import canvas_oauth as canvas_oauth_service
from backend.app.services.authorization import Principal, get_current_principal
from backend.app.services.canvas_oauth import (
    CanvasOAuthError,
    reset_development_canvas_oauth,
    validate_canvas_api_origin,
)


@pytest.fixture()
def oauth_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    monkeypatch.setenv("LTI_TOOL_PUBLIC_URL", "https://tool.school.test")
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "http://frontend.test")
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
        first = Organization(slug="oauth-school", name="Школа OAuth")
        second = Organization(slug="oauth-other", name="Другая школа")
        db.add_all([first, second])
        db.flush()
        users = []
        for email, role, organization_id in (
            ("admin@oauth.test", "administrator", first.id),
            ("teacher@oauth.test", "instructor", first.id),
            ("second-admin@oauth.test", "administrator", first.id),
            ("foreign-admin@oauth.test", "administrator", second.id),
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
        registration = LtiRegistration(
            organization_id=first.id,
            issuer="https://canvas.school.test",
            client_id="lti-client-id",
            deployment_id="deployment-1",
            authorization_endpoint="https://canvas.school.test/api/lti/authorize_redirect",
            jwks_url="https://canvas.school.test/api/lti/security/jwks",
            tool_launch_url="https://tool.school.test/integrations/lti/launch",
            is_active=True,
            is_development=False,
        )
        foreign_registration = LtiRegistration(
            organization_id=second.id,
            issuer="https://canvas.other.test",
            client_id="foreign-lti-client-id",
            deployment_id="deployment-2",
            authorization_endpoint="https://canvas.other.test/api/lti/authorize_redirect",
            jwks_url="https://canvas.other.test/api/lti/security/jwks",
            tool_launch_url="https://tool.school.test/integrations/lti/launch",
            is_active=False,
            is_development=False,
        )
        db.add_all([registration, foreign_registration])
        db.commit()
        values = {
            "organization_id": first.id,
            "foreign_organization_id": second.id,
            "registration_id": registration.id,
            "foreign_registration_id": foreign_registration.id,
            "admin_user_id": users[0].id,
            "second_admin_user_id": users[2].id,
        }
    client = TestClient(app)
    yield client, Session, values
    app.dependency_overrides.clear()
    reset_development_canvas_oauth()
    engine.dispose()


def _headers(email: str = "admin@oauth.test") -> dict[str, str]:
    return {"X-Dev-User": email}


def _root(values: dict) -> str:
    return (
        f"/integrations/canvas/oauth/organizations/{values['organization_id']}"
        f"/registrations/{values['registration_id']}"
    )


def _configuration(expected_version=None) -> dict:
    return {
        "canvas_api_origin": "https://canvas.school.test",
        "oauth_client_id": "canvas-api-client-1001",
        "expected_version": expected_version,
    }


def _save_configuration(client: TestClient, values: dict, expected_version=None):
    return client.put(
        f"{_root(values)}/configuration",
        headers=_headers(),
        json=_configuration(expected_version),
    )


def _start(client: TestClient, values: dict):
    return client.post(f"{_root(values)}/start", headers=_headers())


def _allow_redirect(client: TestClient, authorization_url: str):
    parsed = urlparse(authorization_url)
    params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    consent = client.get(parsed.path, params=params)
    assert consent.status_code == 200
    assert "Canvas не вызывается" in consent.text
    return client.get(
        parsed.path,
        params={**params, "decision": "allow"},
        follow_redirects=False,
    )


def test_canvas_api_origin_requires_one_canonical_https_origin():
    assert (
        validate_canvas_api_origin("https://canvas.school.test")
        == "https://canvas.school.test"
    )
    assert (
        validate_canvas_api_origin("https://canvas.school.test:8443")
        == "https://canvas.school.test:8443"
    )
    for value in (
        "http://canvas.school.test",
        "https://canvas.school.test/",
        " https://canvas.school.test",
        "https://Canvas.school.test",
        "https://canvas.school.test:443",
        "https://user@canvas.school.test",
        "https://canvas.school.test/courses/1",
        "https://canvas.school.test?next=other",
        "https://localhost",
        "https://%zz",
        "https://foo_bar.test",
        "https://-bad.test",
        "https://bad..test",
        "https://999.999.999.999",
        "https://127.0.0.01",
    ):
        with pytest.raises(CanvasOAuthError) as exc:
            validate_canvas_api_origin(value)
        assert exc.value.code == "canvas_api_origin_invalid"


def test_status_configuration_permissions_and_secret_shaped_fields(oauth_client):
    client, Session, values = oauth_client
    root = _root(values)

    initial = client.get(root, headers=_headers())
    assert initial.status_code == 200
    assert initial.headers["cache-control"].startswith("no-store")
    assert initial.json()["connection"]["state"] == "not_configured"
    assert initial.json()["callback_uri"] == (
        "https://tool.school.test/integrations/canvas/oauth/callback"
    )
    assert initial.json()["production_connection_enabled"] is False

    forbidden = client.get(root, headers=_headers("teacher@oauth.test"))
    assert forbidden.status_code == 404
    foreign = client.get(
        f"/integrations/canvas/oauth/organizations/{values['foreign_organization_id']}"
        f"/registrations/{values['registration_id']}",
        headers=_headers("foreign-admin@oauth.test"),
    )
    assert foreign.status_code == 404

    unexpected = client.put(
        f"{root}/configuration",
        headers=_headers(),
        json={**_configuration(), "client_secret": "must-not-be-accepted"},
    )
    assert unexpected.status_code == 422
    with Session() as db:
        assert db.query(CanvasOAuthConfiguration).count() == 0


def test_configuration_uses_optimistic_version_and_minimal_event(oauth_client):
    client, Session, values = oauth_client
    created = _save_configuration(client, values)
    assert created.status_code == 200
    assert created.json() == {
        "canvas_api_origin": "https://canvas.school.test",
        "oauth_client_id": "canvas-api-client-1001",
        "version": 1,
    }
    noop = _save_configuration(client, values, expected_version=1)
    assert noop.status_code == 200
    conflict = _save_configuration(client, values, expected_version=2)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "configuration_conflict"

    with Session() as db:
        events = db.query(CanvasOAuthEvent).all()
        assert [(event.event_type, event.actor_user_id) for event in events] == [
            ("configured", values["admin_user_id"])
        ]
        serialized = " ".join(str(event.__dict__) for event in events)
        assert "canvas.school.test" not in serialized
        assert "canvas-api-client-1001" not in serialized


def test_fake_allow_flow_connects_once_without_persisting_state_or_code(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    started = _start(client, values)
    assert started.status_code == 200
    authorization_url = started.json()["authorization_url"]
    raw_state = parse_qs(urlparse(authorization_url).query)["state"][0]

    with Session() as db:
        attempt = db.query(CanvasOAuthAttempt).one()
        assert attempt.state_digest != raw_state
        assert raw_state not in " ".join(
            str(value) for value in attempt.__dict__.values()
        )

    authorization = _allow_redirect(client, authorization_url)
    assert authorization.status_code == 302
    callback_url = authorization.headers["location"]
    code = parse_qs(urlparse(callback_url).query)["code"][0]
    callback = client.get(callback_url, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == (
        "http://frontend.test/workspace/integrations/lti?canvas_oauth=connected"
        f"&organization={values['organization_id']}"
        f"&canvas_registration={values['registration_id']}"
    )

    status = client.get(_root(values), headers=_headers())
    assert status.status_code == 200
    payload = status.json()
    assert payload["connection"]["state"] == "connected"
    assert payload["connection"]["mode"] == "fake_development"
    assert payload["connection"]["granted_scopes"] == payload["required_scopes"]
    serialized = status.text
    assert raw_state not in serialized
    assert code not in serialized
    assert "vault_reference" not in serialized

    replay = client.get(callback_url, follow_redirects=False)
    assert replay.status_code == 400
    with Session() as db:
        connection = db.query(CanvasOAuthConnection).one()
        assert connection.user_id == values["admin_user_id"]
        assert code not in " ".join(
            str(value) for value in connection.__dict__.values()
        )
        assert db.query(CanvasOAuthEvent).filter_by(event_type="connected").count() == 1


def test_denial_consumes_attempt_and_wrong_code_cannot_be_replayed(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    started = _start(client, values).json()
    parsed = urlparse(started["authorization_url"])
    params = {key: items[0] for key, items in parse_qs(parsed.query).items()}
    denied = client.get(
        parsed.path,
        params={**params, "decision": "deny"},
        follow_redirects=False,
    )
    callback = client.get(denied.headers["location"], follow_redirects=False)
    assert callback.status_code == 303
    assert "canvas_oauth=denied" in callback.headers["location"]
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None

    second = _start(client, values).json()["authorization_url"]
    second_params = parse_qs(urlparse(second).query)
    state = second_params["state"][0]
    wrong_callback = (
        "https://tool.school.test/integrations/canvas/oauth/callback?"
        + urlencode({"state": state, "code": "wrong-code"})
    )
    failed = client.get(wrong_callback, follow_redirects=False)
    assert failed.status_code == 303
    assert "canvas_oauth=failed" in failed.headers["location"]
    replay = client.get(wrong_callback, follow_redirects=False)
    assert replay.status_code == 400
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0


def test_expired_attempt_cannot_authorize_or_create_connection(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    parsed = urlparse(authorization_url)
    params = {key: items[0] for key, items in parse_qs(parsed.query).items()}
    with Session.begin() as db:
        attempt = db.query(CanvasOAuthAttempt).one()
        attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    authorize = client.get(parsed.path, params=params)
    assert authorize.status_code == 400
    callback = client.get(
        "https://tool.school.test/integrations/canvas/oauth/callback?"
        + urlencode({"state": params["state"], "code": "expired-code"}),
        follow_redirects=False,
    )
    assert callback.status_code == 400
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0


def test_scope_redirect_and_duplicate_parameter_mismatches_fail_closed(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    parsed = urlparse(authorization_url)
    params = {key: items[0] for key, items in parse_qs(parsed.query).items()}

    wrong_scope = client.get(parsed.path, params={**params, "scope": "course:read"})
    assert wrong_scope.status_code == 400
    wrong_redirect = client.get(
        parsed.path,
        params={**params, "redirect_uri": "https://tool.school.test/other"},
    )
    assert wrong_redirect.status_code == 400
    duplicate_scope = client.get(
        f"{authorization_url}&scope=course%3Aread",
        follow_redirects=False,
    )
    assert duplicate_scope.status_code == 400
    unexpected = client.get(f"{authorization_url}&prompt=consent")
    assert unexpected.status_code == 400
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is None


def test_callback_rechecks_active_administrator_membership(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    callback_url = _allow_redirect(client, authorization_url).headers["location"]
    with Session.begin() as db:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == values["organization_id"],
                OrganizationMembership.user_id == values["admin_user_id"],
            )
            .one()
        )
        membership.is_active = False

    callback = client.get(callback_url, follow_redirects=False)
    assert callback.status_code == 303
    assert "canvas_oauth=failed" in callback.headers["location"]
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None


def test_callback_rechecks_configuration_after_exchange(oauth_client, monkeypatch):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    callback_url = _allow_redirect(client, authorization_url).headers["location"]
    original_exchange = canvas_oauth_service._development_exchanger.exchange

    def exchange_after_configuration_change(**kwargs):
        with Session.begin() as db:
            configuration = db.query(CanvasOAuthConfiguration).one()
            configuration.canvas_api_origin = "https://canvas-new.school.test"
            configuration.oauth_client_id = "canvas-api-client-2002"
            configuration.version += 1
        return original_exchange(**kwargs)

    monkeypatch.setattr(
        canvas_oauth_service._development_exchanger,
        "exchange",
        exchange_after_configuration_change,
    )
    callback = client.get(callback_url, follow_redirects=False)
    assert callback.status_code == 303
    assert "canvas_oauth=failed" in callback.headers["location"]
    with Session() as db:
        assert db.query(CanvasOAuthConnection).count() == 0
        assert db.query(CanvasOAuthAttempt).one().consumed_at is not None


def test_disconnect_is_user_scoped_and_configuration_change_requires_it(oauth_client):
    client, Session, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    callback_url = _allow_redirect(client, authorization_url).headers["location"]
    assert client.get(callback_url, follow_redirects=False).status_code == 303

    blocked = client.put(
        f"{_root(values)}/configuration",
        headers=_headers(),
        json={
            "canvas_api_origin": "https://canvas-new.school.test",
            "oauth_client_id": "canvas-api-client-2002",
            "expected_version": 1,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "disconnect_before_configuration_change"

    other_disconnect = client.post(
        f"{_root(values)}/disconnect", headers=_headers("second-admin@oauth.test")
    )
    assert other_disconnect.status_code == 200
    assert (
        client.get(_root(values), headers=_headers()).json()["connection"]["state"]
        == "connected"
    )

    disconnected = client.post(f"{_root(values)}/disconnect", headers=_headers())
    assert disconnected.status_code == 200
    assert disconnected.json()["state"] == "disconnected"
    assert (
        client.get(_root(values), headers=_headers()).json()["connection"]["state"]
        == "ready_to_connect"
    )
    changed = client.put(
        f"{_root(values)}/configuration",
        headers=_headers(),
        json={
            "canvas_api_origin": "https://canvas-new.school.test",
            "oauth_client_id": "canvas-api-client-2002",
            "expected_version": 1,
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    with Session() as db:
        events = [
            row.event_type
            for row in db.query(CanvasOAuthEvent).order_by(CanvasOAuthEvent.id)
        ]
        assert events == ["configured", "connected", "disconnected", "configured"]


def test_stale_fake_vault_and_production_mode_are_truthful(oauth_client, monkeypatch):
    client, _, values = oauth_client
    assert _save_configuration(client, values).status_code == 200
    authorization_url = _start(client, values).json()["authorization_url"]
    callback_url = _allow_redirect(client, authorization_url).headers["location"]
    assert client.get(callback_url, follow_redirects=False).status_code == 303
    reset_development_canvas_oauth()
    assert (
        client.get(_root(values), headers=_headers()).json()["connection"]["state"]
        == "reconnect_required"
    )

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "external")
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=values["admin_user_id"],
        email="admin@oauth.test",
        display_name="admin@oauth.test",
        auth_mode="external",
    )
    production_status = client.get(_root(values), headers=_headers())
    assert production_status.status_code == 200
    assert production_status.json()["connection"]["state"] == "production_disabled"
    assert production_status.json()["fake_flow_available"] is False
    start = client.post(f"{_root(values)}/start", headers=_headers())
    assert start.status_code == 409
    assert start.json()["detail"]["code"] == "production_connection_disabled"
    fake_issuer = client.get("/integrations/canvas/oauth/development/authorize")
    assert fake_issuer.status_code == 404
