from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.models import (
    LtiContextBinding,
    LtiLaunchAuditEvent,
    LtiRegistration,
    LtiRegistrationEvent,
    LtiSubjectBinding,
    Organization,
)
from .lti import validate_lti_endpoint
from .lti_development import local_jwks

MAX_PUBLIC_JWKS_BYTES = 64 * 1024
MAX_PUBLIC_KEYS = 5
PRIVATE_JWK_FIELDS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})


class LtiRegistrationConfigurationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LtiRegistrationMutationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ToolRegistrationReadiness:
    configuration_ready: bool
    production_ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    public_origin: str | None
    configuration_url: str | None
    login_url: str | None
    launch_url: str | None
    jwks_url: str | None
    key_ids: tuple[str, ...]
    canvas_configuration: dict[str, Any] | None


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def _allowed_platform_hosts() -> frozenset[str]:
    return frozenset(
        item.strip().lower().rstrip(".")
        for item in os.getenv("LTI_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _exact_http_url(
    value: str,
    *,
    origin_only: bool,
    allow_loopback_http: bool,
) -> str:
    if not isinstance(value, str) or not value or len(value) > 2000:
        raise LtiRegistrationConfigurationError("invalid_url")
    if value != value.strip() or "\\" in value or _has_control_characters(value):
        raise LtiRegistrationConfigurationError("invalid_url")
    try:
        parsed = urlparse(value)
        hostname_value = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise LtiRegistrationConfigurationError("invalid_url") from exc
    if (
        not hostname_value
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise LtiRegistrationConfigurationError("invalid_url")
    hostname = hostname_value.lower().rstrip(".")
    loopback = hostname in {"localhost", "127.0.0.1", "testserver"}
    if parsed.scheme != "https" and not (
        allow_loopback_http and parsed.scheme == "http" and loopback
    ):
        raise LtiRegistrationConfigurationError("https_required")
    if origin_only and parsed.path not in {"", "/"}:
        raise LtiRegistrationConfigurationError("origin_required")
    return value.rstrip("/") if origin_only else value


def validate_platform_url(value: str) -> str:
    """Validate draft syntax without DNS resolution or network access."""

    return _exact_http_url(
        value,
        origin_only=False,
        allow_loopback_http=False,
    )


def tool_public_origin() -> str:
    configured = os.getenv("LTI_TOOL_PUBLIC_URL", "").strip()
    if not configured:
        if _is_production():
            raise LtiRegistrationConfigurationError("public_origin_missing")
        configured = "http://localhost:8000"
    return _exact_http_url(
        configured,
        origin_only=True,
        allow_loopback_http=not _is_production(),
    )


def _decode_base64url_uint(
    value: Any, *, minimum_bytes: int, maximum_bytes: int
) -> int:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum_bytes * 2
        or "=" in value
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise LtiRegistrationConfigurationError("invalid_public_key")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise LtiRegistrationConfigurationError("invalid_public_key") from exc
    if not minimum_bytes <= len(raw) <= maximum_bytes:
        raise LtiRegistrationConfigurationError("invalid_public_key")
    return int.from_bytes(raw, "big")


def _public_rsa_key(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or PRIVATE_JWK_FIELDS.intersection(value):
        raise LtiRegistrationConfigurationError("private_key_material_rejected")
    kid = value.get("kid")
    if (
        not isinstance(kid, str)
        or not kid
        or len(kid) > 128
        or kid != kid.strip()
        or _has_control_characters(kid)
    ):
        raise LtiRegistrationConfigurationError("invalid_key_id")
    if value.get("kty") != "RSA" or value.get("alg") != "RS256":
        raise LtiRegistrationConfigurationError("unsupported_public_key")
    if value.get("use", "sig") != "sig":
        raise LtiRegistrationConfigurationError("unsupported_public_key")
    modulus = _decode_base64url_uint(
        value.get("n"), minimum_bytes=256, maximum_bytes=1024
    )
    exponent = _decode_base64url_uint(value.get("e"), minimum_bytes=1, maximum_bytes=8)
    if modulus <= 0 or exponent < 3 or exponent % 2 == 0:
        raise LtiRegistrationConfigurationError("invalid_public_key")
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": value["n"],
        "e": value["e"],
    }


def public_tool_jwks() -> tuple[dict[str, list[dict[str, str]]], bool]:
    configured = os.getenv("LTI_TOOL_JWKS_JSON", "")
    uses_development_fallback = False
    if not configured.strip():
        if _is_production():
            raise LtiRegistrationConfigurationError("public_jwks_missing")
        payload: Any = local_jwks()
        uses_development_fallback = True
    else:
        encoded = configured.encode("utf-8")
        if len(encoded) > MAX_PUBLIC_JWKS_BYTES:
            raise LtiRegistrationConfigurationError("public_jwks_too_large")
        try:
            payload = json.loads(configured)
        except json.JSONDecodeError as exc:
            raise LtiRegistrationConfigurationError("invalid_public_jwks") from exc
    if not isinstance(payload, dict) or set(payload) != {"keys"}:
        raise LtiRegistrationConfigurationError("invalid_public_jwks")
    values = payload.get("keys")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_PUBLIC_KEYS:
        raise LtiRegistrationConfigurationError("invalid_public_jwks")
    keys = [_public_rsa_key(value) for value in values]
    key_ids = [key["kid"] for key in keys]
    if len(set(key_ids)) != len(key_ids):
        raise LtiRegistrationConfigurationError("duplicate_key_id")
    keys.sort(key=lambda key: key["kid"])
    return {"keys": keys}, uses_development_fallback


def canvas_configuration(*, origin: str, jwks: dict[str, Any]) -> dict[str, Any]:
    del jwks  # Key presence is validated before a configuration is emitted.
    login_url = f"{origin}/integrations/lti/login"
    launch_url = f"{origin}/integrations/lti/launch"
    jwks_url = f"{origin}/integrations/lti/jwks"
    hostname = urlparse(origin).hostname or ""
    return {
        "title": "Контур",
        "description": "Помощник курса с проверяемыми подсказками и источниками.",
        "oidc_initiation_url": login_url,
        "target_link_uri": launch_url,
        "scopes": [],
        "extensions": [
            {
                "domain": hostname,
                "tool_id": "kontur-course-assistant",
                "platform": "canvas.instructure.com",
                "privacy_level": "anonymous",
                "settings": {
                    "text": "Контур — помощник курса",
                    "placements": [
                        {
                            "text": "Контур — помощник курса",
                            "placement": "course_navigation",
                            "message_type": "LtiResourceLinkRequest",
                            "target_link_uri": launch_url,
                            "selection_height": 800,
                            "selection_width": 1200,
                        }
                    ],
                },
            }
        ],
        "public_jwk_url": jwks_url,
    }


def public_jwks_etag(jwks: dict[str, Any]) -> str:
    canonical = json.dumps(
        jwks, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f'"{hashlib.sha256(canonical).hexdigest()}"'


def tool_registration_readiness() -> ToolRegistrationReadiness:
    blockers: list[str] = []
    warnings: list[str] = []
    origin: str | None = None
    jwks: dict[str, Any] | None = None
    fallback = False
    try:
        origin = tool_public_origin()
    except LtiRegistrationConfigurationError as exc:
        blockers.append(exc.code)
    try:
        jwks, fallback = public_tool_jwks()
    except LtiRegistrationConfigurationError as exc:
        blockers.append(exc.code)
    configuration = (
        canvas_configuration(origin=origin, jwks=jwks)
        if origin is not None and jwks is not None
        else None
    )
    if fallback:
        warnings.append("development_ephemeral_key")
    if origin and urlparse(origin).scheme != "https":
        warnings.append("development_loopback_origin")
    if not _allowed_platform_hosts():
        blockers.append("platform_host_allowlist_missing")
    production_ready = (
        bool(configuration)
        and not fallback
        and bool(origin and urlparse(origin).scheme == "https")
        and bool(_allowed_platform_hosts())
    )
    return ToolRegistrationReadiness(
        configuration_ready=configuration is not None,
        production_ready=production_ready,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(warnings),
        public_origin=origin,
        configuration_url=(
            f"{origin}/integrations/lti/configuration" if origin else None
        ),
        login_url=f"{origin}/integrations/lti/login" if origin else None,
        launch_url=f"{origin}/integrations/lti/launch" if origin else None,
        jwks_url=f"{origin}/integrations/lti/jwks" if origin else None,
        key_ids=tuple(key["kid"] for key in jwks["keys"]) if jwks else (),
        canvas_configuration=configuration,
    )


REGISTRATION_FIELDS = (
    "issuer",
    "client_id",
    "deployment_id",
    "authorization_endpoint",
    "jwks_url",
)


def _exact_identifier(value: str, *, maximum_length: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum_length
        or value != value.strip()
        or _has_control_characters(value)
    ):
        raise LtiRegistrationMutationError("invalid_identifier")
    return value


def _validated_registration_values(values: dict[str, Any]) -> dict[str, str]:
    try:
        return {
            "issuer": validate_platform_url(values["issuer"]),
            "client_id": _exact_identifier(values["client_id"], maximum_length=255),
            "deployment_id": _exact_identifier(
                values["deployment_id"], maximum_length=255
            ),
            "authorization_endpoint": validate_platform_url(
                values["authorization_endpoint"]
            ),
            "jwks_url": validate_platform_url(values["jwks_url"]),
        }
    except LtiRegistrationConfigurationError as exc:
        raise LtiRegistrationMutationError(exc.code) from exc


def _registration_event(
    *,
    organization_id: int,
    registration_id: int,
    actor_user_id: int | None,
    event_type: str,
    changed_fields: list[str],
) -> LtiRegistrationEvent:
    return LtiRegistrationEvent(
        organization_id=organization_id,
        registration_id=registration_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        changed_fields=sorted(set(changed_fields)),
    )


def registration_out(db: Session, registration: LtiRegistration) -> dict[str, Any]:
    subject_count = (
        db.query(func.count(LtiSubjectBinding.id))
        .filter(LtiSubjectBinding.registration_id == registration.id)
        .scalar()
        or 0
    )
    context_count = (
        db.query(func.count(LtiContextBinding.id))
        .filter(LtiContextBinding.registration_id == registration.id)
        .scalar()
        or 0
    )
    verified_launch_count, last_verified_launch_at = (
        db.query(
            func.count(LtiLaunchAuditEvent.id),
            func.max(LtiLaunchAuditEvent.created_at),
        )
        .filter(
            LtiLaunchAuditEvent.registration_id == registration.id,
            LtiLaunchAuditEvent.outcome == "accepted",
            LtiLaunchAuditEvent.reason_code == "launch_verified",
        )
        .one()
    )
    return {
        "id": registration.id,
        "organization_id": registration.organization_id,
        "issuer": registration.issuer,
        "client_id": registration.client_id,
        "deployment_id": registration.deployment_id,
        "authorization_endpoint": registration.authorization_endpoint,
        "jwks_url": registration.jwks_url,
        "tool_launch_url": registration.tool_launch_url,
        "is_active": registration.is_active,
        "subject_binding_count": int(subject_count),
        "context_binding_count": int(context_count),
        "verified_launch_count": int(verified_launch_count or 0),
        "last_verified_launch_at": last_verified_launch_at,
        "created_at": registration.created_at,
        "updated_at": registration.updated_at,
    }


def readiness_out() -> dict[str, Any]:
    readiness = tool_registration_readiness()
    return {
        "configuration_ready": readiness.configuration_ready,
        "production_ready": readiness.production_ready,
        "blockers": list(readiness.blockers),
        "warnings": list(readiness.warnings),
        "public_origin": readiness.public_origin,
        "configuration_url": readiness.configuration_url,
        "login_url": readiness.login_url,
        "launch_url": readiness.launch_url,
        "jwks_url": readiness.jwks_url,
        "key_ids": list(readiness.key_ids),
        "canvas_configuration": readiness.canvas_configuration,
    }


def list_production_registrations(
    db: Session, *, organization_id: int
) -> list[dict[str, Any]]:
    rows = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
        )
        .order_by(LtiRegistration.created_at.desc(), LtiRegistration.id.desc())
        .limit(100)
        .all()
    )
    return [registration_out(db, row) for row in rows]


def create_registration_draft(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
    values: dict[str, Any],
) -> dict[str, Any]:
    if db.get(Organization, organization_id) is None:
        raise LtiRegistrationMutationError("organization_unavailable")
    validated = _validated_registration_values(values)
    readiness = tool_registration_readiness()
    if not readiness.configuration_ready or readiness.launch_url is None:
        raise LtiRegistrationMutationError("tool_configuration_unavailable")
    registration = LtiRegistration(
        organization_id=organization_id,
        **validated,
        tool_launch_url=readiness.launch_url,
        is_active=False,
        is_development=False,
    )
    db.add(registration)
    db.flush()
    db.add(
        _registration_event(
            organization_id=organization_id,
            registration_id=registration.id,
            actor_user_id=actor_user_id,
            event_type="created",
            changed_fields=[*REGISTRATION_FIELDS, "tool_launch_url"],
        )
    )
    return registration_out(db, registration)


def _registration_for_organization(
    db: Session, *, organization_id: int, registration_id: int
) -> LtiRegistration:
    registration = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.id == registration_id,
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
        )
        .with_for_update()
        .one_or_none()
    )
    if registration is None:
        raise LtiRegistrationMutationError("registration_unavailable")
    return registration


def update_production_registration(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    actor_user_id: int | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    registration = _registration_for_organization(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
    )
    supplied_fields = [field for field in REGISTRATION_FIELDS if field in changes]
    requested_state = changes.get("is_active")
    if registration.is_active and supplied_fields:
        raise LtiRegistrationMutationError("deactivate_before_editing")
    if requested_state is True and supplied_fields:
        raise LtiRegistrationMutationError("activate_separately")

    changed_fields: list[str] = []
    if supplied_fields:
        candidate = {
            field: changes.get(field, getattr(registration, field))
            for field in REGISTRATION_FIELDS
        }
        validated = _validated_registration_values(candidate)
        readiness = tool_registration_readiness()
        if not readiness.configuration_ready or readiness.launch_url is None:
            raise LtiRegistrationMutationError("tool_configuration_unavailable")
        for field, value in validated.items():
            if getattr(registration, field) != value:
                setattr(registration, field, value)
                changed_fields.append(field)
        if registration.tool_launch_url != readiness.launch_url:
            registration.tool_launch_url = readiness.launch_url
            changed_fields.append("tool_launch_url")
        if changed_fields:
            db.flush()
            db.add(
                _registration_event(
                    organization_id=organization_id,
                    registration_id=registration.id,
                    actor_user_id=actor_user_id,
                    event_type="updated",
                    changed_fields=changed_fields,
                )
            )

    if requested_state is True and not registration.is_active:
        readiness = tool_registration_readiness()
        if not _allowed_platform_hosts():
            raise LtiRegistrationMutationError("platform_host_allowlist_missing")
        if not readiness.production_ready or readiness.launch_url is None:
            raise LtiRegistrationMutationError("tool_not_production_ready")
        try:
            validate_lti_endpoint(
                registration.authorization_endpoint,
                allow_development_loopback=False,
            )
        except ValueError as exc:
            raise LtiRegistrationMutationError(
                "authorization_endpoint_untrusted"
            ) from exc
        try:
            validate_lti_endpoint(
                registration.jwks_url,
                allow_development_loopback=False,
            )
        except ValueError as exc:
            raise LtiRegistrationMutationError("jwks_endpoint_untrusted") from exc
        registration.tool_launch_url = readiness.launch_url
        registration.is_active = True
        db.flush()
        db.add(
            _registration_event(
                organization_id=organization_id,
                registration_id=registration.id,
                actor_user_id=actor_user_id,
                event_type="activated",
                changed_fields=["is_active"],
            )
        )
    elif requested_state is False and registration.is_active:
        registration.is_active = False
        db.flush()
        db.add(
            _registration_event(
                organization_id=organization_id,
                registration_id=registration.id,
                actor_user_id=actor_user_id,
                event_type="deactivated",
                changed_fields=["is_active"],
            )
        )
    db.flush()
    return registration_out(db, registration)
