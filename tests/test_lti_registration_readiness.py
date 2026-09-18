import json
import socket

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
    LtiRegistration,
    LtiRegistrationEvent,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services import lti as lti_service
from backend.app.services.lti_development import local_jwks
from backend.app.services.lti_registration import (
    LtiRegistrationConfigurationError,
    public_jwks_etag,
    public_tool_jwks,
    tool_registration_readiness,
    validate_platform_url,
)


def _configured_public_jwks() -> dict:
    first = local_jwks()["keys"][0]
    second = {**first, "kid": "next-signing-key"}
    return {"keys": [second, first]}


@pytest.fixture()
def registration_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    monkeypatch.setenv("LTI_TOOL_PUBLIC_URL", "https://tool.school.test")
    monkeypatch.setenv(
        "LTI_TOOL_JWKS_JSON",
        json.dumps(_configured_public_jwks()),
    )
    monkeypatch.setenv("LTI_ALLOWED_HOSTS", "canvas.school.test")
    monkeypatch.delenv("LTI_ALLOWED_PRIVATE_HOSTS", raising=False)
    monkeypatch.setattr(
        lti_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )

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
        first = Organization(slug="registration-school", name="Школа регистрации")
        second = Organization(slug="other-school", name="Другая школа")
        db.add_all([first, second])
        db.flush()
        users = []
        for email, role, organization_id in (
            ("admin@registration.test", "administrator", first.id),
            ("teacher@registration.test", "instructor", first.id),
            ("other-admin@registration.test", "administrator", second.id),
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
        db.commit()
        organization_id = first.id
        other_organization_id = second.id
        admin_user_id = users[0].id
    client = TestClient(app)
    yield client, Session, organization_id, other_organization_id, admin_user_id
    app.dependency_overrides.clear()
    engine.dispose()


def _headers(email="admin@registration.test"):
    return {"X-Dev-User": email}


def _draft(**overrides):
    values = {
        "issuer": "https://canvas.school.test",
        "client_id": "10000000000001",
        "deployment_id": "school-deployment-1",
        "authorization_endpoint": "https://canvas.school.test/api/lti/authorize",
        "jwks_url": "https://canvas.school.test/api/lti/security/jwks",
    }
    values.update(overrides)
    return values


def test_local_readiness_is_truthful_preview(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("LTI_TOOL_PUBLIC_URL", raising=False)
    monkeypatch.delenv("LTI_TOOL_JWKS_JSON", raising=False)

    readiness = tool_registration_readiness()

    assert readiness.configuration_ready is True
    assert readiness.production_ready is False
    assert readiness.public_origin == "http://localhost:8000"
    assert set(readiness.warnings) == {
        "development_ephemeral_key",
        "development_loopback_origin",
    }


def test_public_jwks_is_sanitized_sorted_and_rejects_private_material(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    payload = _configured_public_jwks()
    payload["keys"][0]["x-vendor-note"] = "not public output"
    monkeypatch.setenv("LTI_TOOL_JWKS_JSON", json.dumps(payload))

    jwks, fallback = public_tool_jwks()

    assert fallback is False
    assert [key["kid"] for key in jwks["keys"]] == sorted(
        key["kid"] for key in payload["keys"]
    )
    assert "x-vendor-note" not in jwks["keys"][0]
    assert all(
        set(key) == {"kty", "use", "alg", "kid", "n", "e"} for key in jwks["keys"]
    )

    payload["keys"][0]["d"] = "private"
    monkeypatch.setenv("LTI_TOOL_JWKS_JSON", json.dumps(payload))
    with pytest.raises(LtiRegistrationConfigurationError) as exc:
        public_tool_jwks()
    assert exc.value.code == "private_key_material_rejected"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda keys: keys[0].pop("kid"), "invalid_key_id"),
        (
            lambda keys: keys.append({**keys[0]}),
            "duplicate_key_id",
        ),
        (
            lambda keys: keys[0].update({"n": "not+base64"}),
            "invalid_public_key",
        ),
        (
            lambda keys: keys.extend(
                [{**keys[0], "kid": f"extra-{index}"} for index in range(5)]
            ),
            "invalid_public_jwks",
        ),
    ],
)
def test_public_jwks_rejects_ambiguous_or_excessive_keys(
    monkeypatch, mutate, expected_code
):
    monkeypatch.setenv("APP_ENV", "development")
    keys = [dict(local_jwks()["keys"][0])]
    mutate(keys)
    monkeypatch.setenv("LTI_TOOL_JWKS_JSON", json.dumps({"keys": keys}))

    with pytest.raises(LtiRegistrationConfigurationError) as exc:
        public_tool_jwks()

    assert exc.value.code == expected_code


def test_production_has_no_implicit_key_or_origin_fallback(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("LTI_TOOL_PUBLIC_URL", raising=False)
    monkeypatch.delenv("LTI_TOOL_JWKS_JSON", raising=False)

    readiness = tool_registration_readiness()

    assert readiness.configuration_ready is False
    assert readiness.production_ready is False
    assert set(readiness.blockers) == {
        "public_origin_missing",
        "public_jwks_missing",
        "platform_host_allowlist_missing",
    }


@pytest.mark.parametrize(
    "value",
    [
        "http://canvas.school.test",
        "https://user:password@canvas.school.test",
        "https://canvas.school.test/path#fragment",
        " https://canvas.school.test",
        "https://[bad",
    ],
)
def test_platform_draft_urls_require_exact_https_without_network(value):
    with pytest.raises(LtiRegistrationConfigurationError):
        validate_platform_url(value)


def test_malformed_public_origin_becomes_readiness_blocker(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LTI_TOOL_PUBLIC_URL", "https://[bad")
    monkeypatch.setenv("LTI_TOOL_JWKS_JSON", json.dumps(local_jwks()))
    monkeypatch.setenv("LTI_ALLOWED_HOSTS", "canvas.school.test")

    readiness = tool_registration_readiness()

    assert readiness.configuration_ready is False
    assert readiness.production_ready is False
    assert readiness.blockers == ("invalid_url",)


def test_public_canvas_configuration_and_conditional_jwks(registration_client):
    client, _, _, _, _ = registration_client

    configuration = client.get("/integrations/lti/configuration")
    assert configuration.status_code == 200
    data = configuration.json()
    assert data["scopes"] == []
    assert data["public_jwk_url"] == "https://tool.school.test/integrations/lti/jwks"
    extension = data["extensions"][0]
    assert extension["privacy_level"] == "anonymous"
    assert extension["settings"]["placements"] == [
        {
            "text": "Контур — помощник курса",
            "placement": "course_navigation",
            "message_type": "LtiResourceLinkRequest",
            "target_link_uri": "https://tool.school.test/integrations/lti/launch",
            "selection_height": 800,
            "selection_width": 1200,
        }
    ]

    first = client.get("/integrations/lti/jwks")
    assert first.status_code == 200
    assert all("d" not in key for key in first.json()["keys"])
    assert first.headers["etag"] == public_jwks_etag(first.json())
    unchanged = client.get(
        "/integrations/lti/jwks", headers={"If-None-Match": first.headers["etag"]}
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    weak = client.get(
        "/integrations/lti/jwks",
        headers={"If-None-Match": f"W/{first.headers['etag']}"},
    )
    assert weak.status_code == 304


def test_only_organization_administrator_can_manage_registration(
    registration_client,
):
    client, _, organization_id, other_organization_id, _ = registration_client
    path = f"/integrations/lti/organizations/{organization_id}/registrations"

    teacher = client.post(
        path, headers=_headers("teacher@registration.test"), json=_draft()
    )
    cross_org = client.post(
        path, headers=_headers("other-admin@registration.test"), json=_draft()
    )
    own_org = client.get(
        f"/integrations/lti/organizations/{other_organization_id}/registrations",
        headers=_headers("other-admin@registration.test"),
    )

    assert teacher.status_code == 404
    assert cross_org.status_code == 404
    assert own_org.status_code == 200
    readiness = client.get(
        f"/integrations/lti/organizations/{organization_id}/readiness",
        headers=_headers(),
    )
    assert readiness.status_code == 200
    assert readiness.json()["production_ready"] is True


def test_draft_does_not_resolve_dns_and_is_inactive(registration_client, monkeypatch):
    client, _, organization_id, _, _ = registration_client
    monkeypatch.setattr(
        lti_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS used")),
    )

    created = client.post(
        f"/integrations/lti/organizations/{organization_id}/registrations",
        headers=_headers(),
        json=_draft(),
    )

    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is False
    assert created.json()["tool_launch_url"] == (
        "https://tool.school.test/integrations/lti/launch"
    )
    login = client.get(
        "/integrations/lti/login",
        params={
            "iss": _draft()["issuer"],
            "client_id": _draft()["client_id"],
            "lti_deployment_id": _draft()["deployment_id"],
            "login_hint": "opaque",
            "target_link_uri": created.json()["tool_launch_url"],
        },
        follow_redirects=False,
    )
    assert login.status_code == 400


def test_activation_lifecycle_audit_and_active_edit_guard(registration_client):
    client, Session, organization_id, _, admin_user_id = registration_client
    base = f"/integrations/lti/organizations/{organization_id}/registrations"
    created = client.post(base, headers=_headers(), json=_draft())
    registration_id = created.json()["id"]

    activated = client.patch(
        f"{base}/{registration_id}", headers=_headers(), json={"is_active": True}
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True

    edit = client.patch(
        f"{base}/{registration_id}",
        headers=_headers(),
        json={"client_id": "changed-client"},
    )
    assert edit.status_code == 409
    assert edit.json()["detail"]["code"] == "deactivate_before_editing"

    login = client.get(
        "/integrations/lti/login",
        params={
            "iss": _draft()["issuer"],
            "client_id": _draft()["client_id"],
            "lti_deployment_id": _draft()["deployment_id"],
            "login_hint": "opaque",
            "target_link_uri": activated.json()["tool_launch_url"],
        },
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["location"].startswith(_draft()["authorization_endpoint"])

    deactivated = client.patch(
        f"{base}/{registration_id}", headers=_headers(), json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    updated = client.patch(
        f"{base}/{registration_id}",
        headers=_headers(),
        json={"client_id": "10000000000002"},
    )
    assert updated.status_code == 200
    assert updated.json()["client_id"] == "10000000000002"

    with Session() as db:
        events = db.query(LtiRegistrationEvent).order_by(LtiRegistrationEvent.id).all()
        assert [event.event_type for event in events] == [
            "created",
            "activated",
            "deactivated",
            "updated",
        ]
        assert all(event.actor_user_id == admin_user_id for event in events)
        assert events[-1].changed_fields == ["client_id"]
        serialized = json.dumps(
            [event.changed_fields for event in events], sort_keys=True
        )
        assert "canvas.school.test" not in serialized
        assert "10000000000002" not in serialized


def test_activation_failure_preserves_draft_and_duplicate_is_safe(
    registration_client, monkeypatch
):
    client, Session, organization_id, _, _ = registration_client
    base = f"/integrations/lti/organizations/{organization_id}/registrations"
    created = client.post(base, headers=_headers(), json=_draft())
    assert created.status_code == 201

    duplicate = client.post(base, headers=_headers(), json=_draft())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "registration_duplicate"

    monkeypatch.setattr(
        lti_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            lti_service.socket.gaierror("unresolved")
        ),
    )
    failed = client.patch(
        f"{base}/{created.json()['id']}",
        headers=_headers(),
        json={"is_active": True},
    )
    assert failed.status_code == 409
    assert failed.json()["detail"]["code"] == "authorization_endpoint_untrusted"
    with Session() as db:
        row = db.get(LtiRegistration, created.json()["id"])
        assert row.is_active is False
        events = db.query(LtiRegistrationEvent).all()
        assert [event.event_type for event in events] == ["created"]


def test_activation_requires_explicit_platform_host_allowlist(
    registration_client, monkeypatch
):
    client, Session, organization_id, _, _ = registration_client
    base = f"/integrations/lti/organizations/{organization_id}/registrations"
    created = client.post(base, headers=_headers(), json=_draft())
    monkeypatch.delenv("LTI_ALLOWED_HOSTS", raising=False)

    readiness = client.get(
        f"/integrations/lti/organizations/{organization_id}/readiness",
        headers=_headers(),
    )
    assert readiness.status_code == 200
    assert readiness.json()["production_ready"] is False
    assert "platform_host_allowlist_missing" in readiness.json()["blockers"]

    activation = client.patch(
        f"{base}/{created.json()['id']}",
        headers=_headers(),
        json={"is_active": True},
    )

    assert activation.status_code == 409
    assert activation.json()["detail"]["code"] == ("platform_host_allowlist_missing")
    with Session() as db:
        assert db.get(LtiRegistration, created.json()["id"]).is_active is False


@pytest.mark.parametrize(
    "extra",
    [
        {"tool_launch_url": "https://attacker.example/launch"},
        {"is_active": True},
        {"private_jwk": {"d": "secret"}},
    ],
)
def test_registration_draft_rejects_unexpected_fields(registration_client, extra):
    client, Session, organization_id, _, _ = registration_client
    payload = {**_draft(), **extra}

    response = client.post(
        f"/integrations/lti/organizations/{organization_id}/registrations",
        headers=_headers(),
        json=payload,
    )

    assert response.status_code == 422
    with Session() as db:
        assert db.query(LtiRegistration).count() == 0
