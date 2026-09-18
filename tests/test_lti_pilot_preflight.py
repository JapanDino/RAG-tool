import json

import pytest

pytest.importorskip("sqlalchemy")

from backend.app.services.lti_development import local_jwks
from backend.app.services.lti_preflight import (
    EXTERNAL_CHECK_CODES,
    assess_lti_pilot_preflight,
)
from scripts.check_lti_pilot_preflight import main


def _production_environment(monkeypatch):
    key = dict(local_jwks()["keys"][0])
    key["kid"] = "preflight-secret-key-id"
    values = {
        "APP_ENV": "production",
        "AUTH_MODE": "external",
        "CORS_ALLOW_ORIGINS": "https://frontend.secret-school.test",
        "FRONTEND_PUBLIC_URL": "https://frontend.secret-school.test",
        "NEXT_PUBLIC_API_BASE": "https://api.secret-school.test",
        "LTI_TOOL_PUBLIC_URL": "https://tool.secret-school.test",
        "LTI_TOOL_JWKS_JSON": json.dumps({"keys": [key]}),
        "LTI_ALLOWED_HOSTS": "canvas.secret-school.test",
        "LTI_SESSION_CSRF_SECRET": "preflight-super-secret-value-1234567890",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LTI_SESSION_COOKIE_SAMESITE", raising=False)
    return values


def _by_code(report, group):
    return {item["code"]: item["status"] for item in report[group]}


def test_complete_configuration_is_ready_for_external_rehearsal(monkeypatch):
    _production_environment(monkeypatch)

    report = assess_lti_pilot_preflight()

    assert report["schema_version"] == 1
    assert report["status"] == "ready_for_external_rehearsal"
    assert set(_by_code(report, "automated_checks").values()) == {"passed"}
    assert _by_code(report, "external_checks") == {
        code: "external" for code in EXTERNAL_CHECK_CODES
    }


def test_unsafe_configuration_returns_stable_blockers(monkeypatch):
    _production_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "http://localhost:3000")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE", "http://localhost:8000")
    monkeypatch.delenv("LTI_TOOL_PUBLIC_URL")
    monkeypatch.delenv("LTI_TOOL_JWKS_JSON")
    monkeypatch.delenv("LTI_ALLOWED_HOSTS")
    monkeypatch.setenv("LTI_SESSION_CSRF_SECRET", "short")

    report = assess_lti_pilot_preflight()
    checks = _by_code(report, "automated_checks")

    assert report["status"] == "blocked"
    assert checks["production_environment"] == "blocked"
    assert checks["external_authentication"] == "blocked"
    assert checks["cors_https_origins"] == "blocked"
    assert checks["frontend_https_origin"] == "blocked"
    assert checks["browser_api_https_origin"] == "blocked"
    assert checks["platform_host_allowlist"] == "blocked"
    assert checks["tool_public_origin_missing"] == "blocked"
    assert checks["tool_public_jwks_missing"] == "blocked"
    assert checks["iframe_cookie_policy"] == "blocked"
    assert checks["session_csrf_secret"] == "blocked"


def test_report_never_echoes_configuration_values(monkeypatch):
    values = _production_environment(monkeypatch)

    encoded = json.dumps(assess_lti_pilot_preflight(), sort_keys=True)

    forbidden = (
        values["FRONTEND_PUBLIC_URL"],
        values["NEXT_PUBLIC_API_BASE"],
        values["LTI_TOOL_PUBLIC_URL"],
        values["LTI_ALLOWED_HOSTS"],
        "preflight-secret-key-id",
        values["LTI_SESSION_CSRF_SECRET"],
    )
    assert all(value not in encoded for value in forbidden)


@pytest.mark.parametrize(
    "allowed_hosts",
    (
        "https://canvas.school.test",
        "*.school.test",
        "canvas.school.test:443",
        "canvas..school.test",
    ),
)
def test_platform_allowlist_requires_exact_hostnames(monkeypatch, allowed_hosts):
    _production_environment(monkeypatch)
    monkeypatch.setenv("LTI_ALLOWED_HOSTS", allowed_hosts)

    checks = _by_code(assess_lti_pilot_preflight(), "automated_checks")

    assert checks["platform_host_allowlist"] == "blocked"


@pytest.mark.parametrize(
    ("variable", "check_code"),
    (
        ("CORS_ALLOW_ORIGINS", "cors_https_origins"),
        ("FRONTEND_PUBLIC_URL", "frontend_https_origin"),
        ("NEXT_PUBLIC_API_BASE", "browser_api_https_origin"),
        ("LTI_TOOL_PUBLIC_URL", "tool_public_origin_invalid_exact_host"),
    ),
)
@pytest.mark.parametrize(
    "invalid_origin",
    (
        "https://*",
        "https://*.school.test",
        "https://bad_host.school.test",
        "https://canvas..school.test",
        "https://localhost",
        "https://tool.localhost",
        "https://testserver",
        "https://127.0.0.1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://0x7f000001",
        "https://0x7f.0.0.1",
        "https://0177.0.0.1",
        "https://2130706433",
    ),
)
def test_public_origins_reject_wildcard_or_malformed_hosts(
    monkeypatch, variable, check_code, invalid_origin
):
    _production_environment(monkeypatch)
    monkeypatch.setenv(variable, invalid_origin)

    report = assess_lti_pilot_preflight()
    checks = _by_code(report, "automated_checks")

    assert report["status"] == "blocked"
    assert checks[check_code] == "blocked"


def test_private_platform_hosts_must_also_be_in_primary_allowlist(monkeypatch):
    _production_environment(monkeypatch)
    monkeypatch.setenv("LTI_ALLOWED_PRIVATE_HOSTS", "internal.secret-school.test")

    checks = _by_code(assess_lti_pilot_preflight(), "automated_checks")

    assert checks["private_platform_host_scope"] == "blocked"

    monkeypatch.setenv(
        "LTI_ALLOWED_HOSTS",
        "canvas.secret-school.test,internal.secret-school.test",
    )
    checks = _by_code(assess_lti_pilot_preflight(), "automated_checks")
    assert checks["private_platform_host_scope"] == "passed"


def test_assessment_performs_no_dns_lookup(monkeypatch):
    _production_environment(monkeypatch)

    def reject_network(*args, **kwargs):
        raise AssertionError("preflight attempted network access")

    monkeypatch.setattr("socket.getaddrinfo", reject_network)
    monkeypatch.setattr("requests.get", reject_network)
    monkeypatch.setattr("sqlalchemy.create_engine", reject_network)

    assert assess_lti_pilot_preflight()["status"] == "ready_for_external_rehearsal"


def test_cli_returns_zero_only_for_ready_local_configuration(monkeypatch, capsys):
    _production_environment(monkeypatch)
    assert main() == 0
    ready_output = capsys.readouterr().out
    assert json.loads(ready_output)["status"] == "ready_for_external_rehearsal"

    monkeypatch.setenv("AUTH_MODE", "development")
    assert main() == 2
    blocked_output = capsys.readouterr().out
    assert json.loads(blocked_output)["status"] == "blocked"
