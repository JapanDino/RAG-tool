from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse

from .lti_registration import (
    LtiRegistrationConfigurationError,
    public_tool_jwks,
    tool_public_origin,
    tool_registration_readiness,
)
from .product_session import csrf_token_for_session, session_cookie_policy

CheckStatus = Literal["passed", "blocked", "external"]


@dataclass(frozen=True)
class PreflightCheck:
    code: str
    status: CheckStatus


EXTERNAL_CHECK_CODES = (
    "canvas_version_confirmed",
    "developer_key_enabled",
    "institutional_tls_chain_verified",
    "iframe_cookie_flow_verified",
    "student_and_instructor_accounts_ready",
    "non_sensitive_pilot_course_ready",
    "signing_key_owner_and_rotation_approved",
    "rollback_owner_and_trigger_approved",
    "student_data_retention_approved",
)

_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_IPV4_NUMBER = re.compile(r"(?:[0-9]+|0x[0-9a-f]+)")


def _exact_hostname(value: str) -> bool:
    if not value or value != value.rstrip("."):
        return False
    try:
        address = ip_address(value)
    except ValueError:
        hostname = value.lower()
        labels = hostname.split(".")
        return bool(
            len(value) <= 253
            and hostname not in {"localhost", "testserver"}
            and not hostname.endswith(".localhost")
            and not all(_IPV4_NUMBER.fullmatch(label) for label in labels)
            and all(_HOST_LABEL.fullmatch(label) is not None for label in labels)
        )
    effective_address = getattr(address, "ipv4_mapped", None) or address
    return not (
        effective_address.is_loopback
        or effective_address.is_unspecified
        or effective_address.is_link_local
        or effective_address.is_multicast
    )


def _exact_https_origin(value: str) -> bool:
    if (
        not value
        or value != value.strip()
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and _exact_hostname(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _check(code: str, passed: bool) -> PreflightCheck:
    return PreflightCheck(code=code, status="passed" if passed else "blocked")


def _cors_origins() -> tuple[str, ...]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values or any(not _exact_https_origin(value) for value in values):
        return ()
    return tuple(value.rstrip("/") for value in values)


def _exact_hosts(variable: str) -> tuple[str, ...] | None:
    raw = os.getenv(variable, "").strip()
    if not raw:
        return ()
    raw_values = raw.split(",")
    values = tuple(
        item.strip().lower().rstrip(".") for item in raw_values if item.strip()
    )
    if not values:
        return None
    for value in values:
        if not _exact_hostname(value):
            return None
    return values


def _public_origin_check() -> PreflightCheck:
    configured = os.getenv("LTI_TOOL_PUBLIC_URL", "").strip()
    if not configured:
        return PreflightCheck(code="tool_public_origin_missing", status="blocked")
    if not _exact_https_origin(configured):
        return PreflightCheck(
            code="tool_public_origin_invalid_exact_host", status="blocked"
        )
    try:
        tool_public_origin()
    except LtiRegistrationConfigurationError as exc:
        return PreflightCheck(code=f"tool_public_origin_{exc.code}", status="blocked")
    return PreflightCheck(code="tool_public_origin", status="passed")


def _public_jwks_check() -> PreflightCheck:
    if not os.getenv("LTI_TOOL_JWKS_JSON", "").strip():
        return PreflightCheck(code="tool_public_jwks_missing", status="blocked")
    try:
        public_tool_jwks()
    except LtiRegistrationConfigurationError as exc:
        return PreflightCheck(code=f"tool_public_jwks_{exc.code}", status="blocked")
    return PreflightCheck(code="tool_public_jwks", status="passed")


def _cookie_check() -> PreflightCheck:
    try:
        policy = session_cookie_policy()
    except RuntimeError:
        return PreflightCheck(code="iframe_cookie_policy", status="blocked")
    return _check(
        "iframe_cookie_policy",
        policy.secure
        and policy.samesite == "none"
        and policy.name.startswith("__Host-"),
    )


def _csrf_check() -> PreflightCheck:
    if len(os.getenv("LTI_SESSION_CSRF_SECRET", "")) < 32:
        return PreflightCheck(code="session_csrf_secret", status="blocked")
    try:
        csrf_token_for_session("preflight-value-not-emitted")
    except RuntimeError:
        return PreflightCheck(code="session_csrf_secret", status="blocked")
    return PreflightCheck(code="session_csrf_secret", status="passed")


def assess_lti_pilot_preflight() -> dict[str, object]:
    """Assess local production configuration without network or database access."""

    cors_origins = _cors_origins()
    platform_hosts = _exact_hosts("LTI_ALLOWED_HOSTS")
    private_platform_hosts = _exact_hosts("LTI_ALLOWED_PRIVATE_HOSTS")
    frontend_origin = os.getenv("FRONTEND_PUBLIC_URL", "").strip().rstrip("/")
    browser_api_origin = os.getenv("NEXT_PUBLIC_API_BASE", "").strip().rstrip("/")
    readiness = tool_registration_readiness()
    automated = [
        _check(
            "production_environment",
            os.getenv("APP_ENV", "").strip().lower() == "production",
        ),
        _check(
            "external_authentication",
            os.getenv("AUTH_MODE", "").strip().lower() == "external",
        ),
        _check("cors_https_origins", bool(cors_origins)),
        _check("frontend_https_origin", _exact_https_origin(frontend_origin)),
        _check("browser_api_https_origin", _exact_https_origin(browser_api_origin)),
        _check(
            "frontend_origin_allowed_by_cors",
            bool(frontend_origin and frontend_origin in cors_origins),
        ),
        _public_origin_check(),
        _public_jwks_check(),
        _check(
            "platform_host_allowlist",
            bool(platform_hosts)
            and "platform_host_allowlist_missing" not in readiness.blockers,
        ),
        _check(
            "private_platform_host_scope",
            private_platform_hosts == ()
            or bool(
                private_platform_hosts
                and platform_hosts
                and set(private_platform_hosts) <= set(platform_hosts)
            ),
        ),
        _cookie_check(),
        _csrf_check(),
    ]
    external = [
        PreflightCheck(code=code, status="external") for code in EXTERNAL_CHECK_CODES
    ]
    ready = all(check.status == "passed" for check in automated)
    return {
        "schema_version": 1,
        "status": "ready_for_external_rehearsal" if ready else "blocked",
        "automated_checks": [asdict(check) for check in automated],
        "external_checks": [asdict(check) for check in external],
    }
