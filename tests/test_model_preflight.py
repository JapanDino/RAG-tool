from __future__ import annotations

import json

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
from backend.app.models.models import Organization, OrganizationMembership, User
from backend.app.services.model_preflight import (
    build_model_host_preflight,
    serialize_model_host_preflight,
)
from scripts.check_agent_model_preflight import main as preflight_main

SECRET = "credential-sentinel-never-export"
HOST = "models.private-school.example"
MODEL = "private-model-id-never-export"


def _configured_env(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "development",
        "AGENT_MODEL_ENABLED": "1",
        "AGENT_MODEL_BASE_URL": f"https://{HOST}/v1",
        "AGENT_MODEL_ALLOWED_HOSTS": HOST,
        "AGENT_MODEL_ID": MODEL,
        "AGENT_MODEL_API_KEY": SECRET,
        "AGENT_MODEL_CONNECT_TIMEOUT": "3",
        "AGENT_MODEL_READ_TIMEOUT": "30",
        "AGENT_MODEL_RETRIES": "1",
    }
    values.update(overrides)
    return values


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


@pytest.mark.parametrize(
    "profile_id",
    ("deepseek_openai_v1", "gemma_openai_v1"),
)
def test_profiles_use_one_offline_contract_without_network(monkeypatch, profile_id):
    def unexpected_network(*args, **kwargs):
        raise AssertionError("offline preflight attempted network access")

    monkeypatch.setattr("requests.post", unexpected_network)
    report = build_model_host_preflight(profile_id=profile_id, env={})

    checks = {item.code: item for item in report.checks}
    assert checks["profile_contract_supported"].status == "passed"
    assert checks["structured_probe_succeeds"].status == "external"
    assert report.status == "configuration_required"
    assert report.network_probe_performed is False
    assert report.credentials_included is False
    assert report.course_data_used is False
    assert report.bundle_fingerprint.startswith("sha256:")


def test_configured_and_invalid_states_are_bounded_and_secret_free():
    configured = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        organization_model_route="allowed",
        env=_configured_env(),
    )
    invalid = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        organization_model_route="deterministic_only",
        env=_configured_env(AGENT_MODEL_BASE_URL=f"http://{HOST}/v1"),
    )

    assert configured.status == "ready_for_credentialed_probe"
    assert configured.configuration_state == "configured"
    assert invalid.status == "configuration_blocked"
    assert invalid.configuration_state == "misconfigured"
    assert invalid.organization_model_route == "deterministic_only"
    encoded = serialize_model_host_preflight(configured)
    assert encoded == serialize_model_host_preflight(configured)
    assert json.loads(encoded)["bundle_fingerprint"] == configured.bundle_fingerprint
    lowered = encoded.decode("ascii").casefold()
    for forbidden in (SECRET.casefold(), HOST.casefold(), MODEL.casefold(), "/v1"):
        assert forbidden not in lowered
    for forbidden_field in (
        "api_key_value",
        "base_url_value",
        "model_id_value",
        "prompt",
        "response_body",
        "course_content",
    ):
        assert forbidden_field not in lowered


def test_origin_and_runtime_failures_are_reported_independently():
    invalid_runtime = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        env=_configured_env(AGENT_MODEL_READ_TIMEOUT="unbounded"),
    )
    invalid_origin = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        env=_configured_env(AGENT_MODEL_BASE_URL=f"http://{HOST}/v1"),
    )

    runtime_checks = {item.code: item.status for item in invalid_runtime.checks}
    origin_checks = {item.code: item.status for item in invalid_origin.checks}
    assert runtime_checks["exact_origin_policy_valid"] == "passed"
    assert runtime_checks["bounded_runtime_policy_valid"] == "blocked"
    assert origin_checks["exact_origin_policy_valid"] == "blocked"
    assert origin_checks["bounded_runtime_policy_valid"] == "passed"

    dormant_malformed = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        env={
            "AGENT_MODEL_ENABLED": "0",
            "AGENT_MODEL_BASE_URL": "http://[bad",
            "AGENT_MODEL_ALLOWED_HOSTS": "https://[also-bad",
        },
    )
    dormant_checks = {item.code: item.status for item in dormant_malformed.checks}
    assert dormant_malformed.status == "configuration_required"
    assert dormant_checks["exact_origin_policy_valid"] == "blocked"


def test_preflight_api_is_admin_only_and_export_matches_report(monkeypatch):
    for name, value in _configured_env().items():
        monkeypatch.setenv(name, value)
    client, Session, engine = _client(monkeypatch)
    try:
        bootstrap = client.post("/identity/development/bootstrap", json={})
        assert bootstrap.status_code == 201
        organization_id = bootstrap.json()["organization"]["id"]
        path = f"/organizations/{organization_id}/agent-model/preflight"
        with Session() as db:
            other = Organization(slug="preflight-other", name="Other School")
            foreign_admin = User(
                email="preflight-foreign-admin@test",
                display_name="Foreign admin",
                is_active=True,
            )
            db.add_all([other, foreign_admin])
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=other.id,
                    user_id=foreign_admin.id,
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()

        report = client.get(
            path,
            params={"profile": "gemma_openai_v1"},
            headers={"X-Dev-User": "admin@local.test"},
        )
        assert report.status_code == 200, report.text
        assert report.headers["cache-control"].startswith("no-store")
        assert report.json()["profile"]["id"] == "gemma_openai_v1"
        assert report.json()["status"] == "ready_for_credentialed_probe"

        denied_identities = (
            "student@local.test",
            "instructor@local.test",
            "methodologist@local.test",
            "designer@local.test",
            "preflight-foreign-admin@test",
        )
        for identity in denied_identities:
            denied = client.get(path, headers={"X-Dev-User": identity})
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"

        for endpoint in (path, f"{path}/export"):
            for identity in denied_identities:
                denied = client.get(
                    endpoint,
                    params={"profile": "user-selected-provider"},
                    headers={"X-Dev-User": identity},
                )
                assert denied.status_code == 404
                assert denied.json()["detail"] == "resource not found"

        monkeypatch.setenv("AUTH_MODE", "disabled")
        for endpoint in (path, f"{path}/export"):
            denied = client.get(
                endpoint,
                params={"profile": "user-selected-provider"},
            )
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"
        monkeypatch.setenv("AUTH_MODE", "development")
        invalid = client.get(
            path,
            params={"profile": "user-selected-provider"},
            headers={"X-Dev-User": "admin@local.test"},
        )
        assert invalid.status_code == 422

        exported = client.get(
            f"{path}/export",
            params={"profile": "gemma_openai_v1"},
            headers={"X-Dev-User": "admin@local.test"},
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith("application/json")
        assert exported.headers["x-content-type-options"] == "nosniff"
        assert exported.headers["content-disposition"] == (
            'attachment; filename="agent-model-preflight-gemma.json"'
        )
        assert json.loads(exported.content) == report.json()
        for forbidden in (SECRET, HOST, MODEL):
            assert forbidden not in exported.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_cli_matches_service_and_never_prints_values(monkeypatch, capfd):
    for name, value in _configured_env().items():
        monkeypatch.setenv(name, value)
    expected = build_model_host_preflight(
        profile_id="deepseek_openai_v1",
        organization_model_route="not_assessed",
    )
    assert preflight_main(["--profile", "deepseek"]) == 0
    output = capfd.readouterr().out.encode("utf-8")
    assert output == serialize_model_host_preflight(expected)
    for forbidden in (SECRET, HOST, MODEL):
        assert forbidden not in output.decode("utf-8")

    monkeypatch.setenv("AGENT_MODEL_ENABLED", "0")
    assert preflight_main(["--profile", "gemma"]) == 2
    blocked = json.loads(capfd.readouterr().out)
    assert blocked["status"] == "configuration_required"
