import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import lti_security as sec


@pytest.fixture
def platform(monkeypatch):
    cfg = {
        "PUBLIC_BASE_URL": "https://assistant.test",
        "CANVAS_URL": "https://canvas.test",
        "LTI_ISSUER": "https://canvas.test",
        "LTI_CLIENT_ID": "client-1",
        "LTI_DEPLOYMENT_ID": "deployment-1",
        "LTI_AUTH_URL": "https://canvas.test/authorize",
        "LTI_JWKS_URL": "https://canvas.test/jwks",
        "LTI_ALLOWED_COURSE_IDS": "123",
    }
    for name, value in cfg.items():
        monkeypatch.setenv(name, value)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        sec,
        "jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
        ),
    )
    claims = {
        "iss": cfg["LTI_ISSUER"],
        "aud": cfg["LTI_CLIENT_ID"],
        "sub": "user-1",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "nonce-1",
        sec.CLAIM + "deployment_id": cfg["LTI_DEPLOYMENT_ID"],
        sec.CLAIM + "version": "1.3.0",
        sec.CLAIM + "message_type": "LtiResourceLinkRequest",
        sec.CLAIM + "target_link_uri": cfg["PUBLIC_BASE_URL"] + "/lti/launch",
        sec.CLAIM + "context": {"id": "context-1", "title": "Test course"},
        sec.CLAIM + "custom": {"canvas_course_id": "123"},
        sec.CLAIM + "resource_link": {"id": "link-1"},
        sec.CLAIM + "roles": [sec.LEARNER_ROLE],
    }
    return cfg, private, claims


def signed(platform, claims=None):
    return jwt.encode(
        claims or platform[2], platform[1], algorithm="RS256", headers={"kid": "test"}
    )


def test_valid_student_launch(platform):
    user = sec.validate_launch(signed(platform), {"nonce": "nonce-1"}, platform[0])
    assert user["role"] == "student" and user["course_id"] == 123


def test_valid_teacher_launch(platform):
    platform[2][sec.CLAIM + "roles"] = [next(iter(sec.TEACHER_ROLES))]
    assert (
        sec.validate_launch(signed(platform), {"nonce": "nonce-1"}, platform[0])["role"]
        == "teacher"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("iss", "https://attacker.test"),
        ("aud", "other-client"),
        ("exp", 1),
        ("iat", 4102444800),
        ("nonce", "wrong"),
        ("azp", "wrong-client"),
        (sec.CLAIM + "deployment_id", "another"),
        (sec.CLAIM + "version", "1.0"),
        (sec.CLAIM + "message_type", "LtiDeepLinkingRequest"),
        (sec.CLAIM + "target_link_uri", "https://attacker.test"),
        (sec.CLAIM + "roles", ["Instructor"]),
        (
            sec.CLAIM + "roles",
            ["http://purl.imsglobal.org/vocab/lis/v2/membership#Observer"],
        ),
        (sec.CLAIM + "context", {}),
        (sec.CLAIM + "resource_link", {}),
        (sec.CLAIM + "custom", {"canvas_course_id": "456"}),
    ],
)
def test_invalid_claims_fail_closed(platform, field, value):
    platform[2][field] = value
    with pytest.raises(HTTPException) as exc:
        sec.validate_launch(signed(platform), {"nonce": "nonce-1"}, platform[0])
    assert exc.value.status_code == 401


def test_wrong_signature(platform):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(platform[2], other, algorithm="RS256")
    with pytest.raises(HTTPException):
        sec.validate_launch(token, {"nonce": "nonce-1"}, platform[0])


def test_multi_audience_requires_authorized_party(platform):
    platform[2]["aud"] = ["client-1", "another"]
    with pytest.raises(HTTPException):
        sec.validate_launch(signed(platform), {"nonce": "nonce-1"}, platform[0])
    platform[2]["azp"] = "client-1"
    assert (
        sec.validate_launch(signed(platform), {"nonce": "nonce-1"}, platform[0])["role"]
        == "student"
    )


def test_state_is_single_use(monkeypatch):
    store = {sec.key("state", "test"): '{"nonce":"nonce-1"}'}
    monkeypatch.setattr(
        sec,
        "redis_client",
        lambda: SimpleNamespace(getdel=lambda k: store.pop(k, None)),
    )
    assert sec.consume_state("test")["nonce"] == "nonce-1"
    with pytest.raises(HTTPException):
        sec.consume_state("test")


def test_lti_mode_blocks_all_legacy_endpoints(monkeypatch):
    monkeypatch.setenv("APP_MODE", "lti")
    client = TestClient(app)
    for path in (
        "/datasets",
        "/canvas/courses",
        "/search",
        "/chat/stream",
        "/docs",
        "/openapi.json",
        "/jobs/1",
    ):
        assert client.get(path).status_code == 404
    assert client.get("/portal/session").status_code == 401


def test_registration_available_before_client_id(platform, monkeypatch):
    monkeypatch.delenv("LTI_CLIENT_ID")
    monkeypatch.delenv("LTI_DEPLOYMENT_ID")
    response = TestClient(app).get("/lti/config")
    assert response.status_code == 200
    assert response.json()["scopes"] == []
    assert response.json()["custom_fields"]["canvas_course_id"] == "$Canvas.course.id"


def test_login_rejects_untrusted_platform_and_redirect(platform):
    client = TestClient(app)
    params = {
        "iss": "https://attacker.test",
        "login_hint": "1",
        "target_link_uri": "https://assistant.test/lti/launch",
    }
    assert client.get("/lti/login", params=params).status_code == 400
    params.update(
        iss=platform[0]["LTI_ISSUER"], target_link_uri="https://attacker.test"
    )
    assert client.get("/lti/login", params=params).status_code == 400


def test_launch_requires_browser_binding(platform):
    response = TestClient(app).post(
        "/lti/launch", data={"id_token": signed(platform), "state": "stolen"}
    )
    assert response.status_code == 401


def test_non_https_configuration_rejected(platform, monkeypatch):
    monkeypatch.setenv("LTI_JWKS_URL", "http://canvas.test/jwks")
    with pytest.raises(HTTPException):
        sec.settings()
