from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

import jwt
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.models import (
    Course,
    CourseMembership,
    LtiContextBinding,
    LtiLaunchAttempt,
    LtiLaunchAuditEvent,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from .lti_binding import capture_unbound_candidates

LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim"
MESSAGE_TYPE = f"{LTI_CLAIM}/message_type"
VERSION = f"{LTI_CLAIM}/version"
DEPLOYMENT_ID = f"{LTI_CLAIM}/deployment_id"
TARGET_LINK_URI = f"{LTI_CLAIM}/target_link_uri"
RESOURCE_LINK = f"{LTI_CLAIM}/resource_link"
ROLES = f"{LTI_CLAIM}/roles"
CONTEXT = f"{LTI_CLAIM}/context"

ROLE_MAP = {
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner": "student",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor": "instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper": "program_designer",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator": "administrator",
    "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator": "administrator",
    "http://purl.imsglobal.org/vocab/lis/v2/system/person#SysAdmin": "administrator",
}

MAX_IDENTIFIER_LENGTH = 255
LAUNCH_TTL = timedelta(minutes=5)
CLOCK_SKEW_SECONDS = 30
MAX_JWKS_BYTES = 64 * 1024


class LtiLaunchError(Exception):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LtiLaunchResult:
    registration_id: int
    organization_id: int
    course_id: int
    user_id: int
    course_title: str
    display_name: str
    role: str


def digest_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_string(value: Any, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise LtiLaunchError("required_claim_missing")
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH:
        raise LtiLaunchError("invalid_claim")
    return value


def _is_development() -> bool:
    return (
        os.getenv("APP_ENV", "development").strip().lower() != "production"
        and os.getenv("AUTH_MODE", "development").strip().lower() == "development"
    )


def validate_lti_endpoint(url: str, *, allow_development_loopback: bool) -> str:
    parsed = urlparse(url.strip())
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("LTI endpoint contains unsupported URL components")
    if not parsed.hostname:
        raise ValueError("LTI endpoint has no hostname")
    hostname = parsed.hostname.lower().rstrip(".")
    if (
        allow_development_loopback
        and _is_development()
        and parsed.scheme == "http"
        and hostname in {"localhost", "127.0.0.1", "testserver"}
    ):
        return url
    if parsed.scheme != "https":
        raise ValueError("LTI endpoints must use HTTPS")

    exact_hosts = {
        item.strip().lower().rstrip(".")
        for item in os.getenv("LTI_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    if exact_hosts and hostname not in exact_hosts:
        raise ValueError("LTI endpoint host is not allow-listed")
    private_hosts = {
        item.strip().lower().rstrip(".")
        for item in os.getenv("LTI_ALLOWED_PRIVATE_HOSTS", "").split(",")
        if item.strip()
    }
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError("LTI endpoint hostname cannot be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_multicast or ip.is_unspecified:
            raise ValueError("unsafe LTI endpoint address")
        unsafe = not ip.is_global
        if unsafe and hostname not in private_hosts:
            raise ValueError("private LTI endpoint is not explicitly allow-listed")
    return url


def _registration_for_login(
    db: Session,
    *,
    issuer: str,
    client_id: str | None,
    deployment_id: str | None,
) -> LtiRegistration:
    query = db.query(LtiRegistration).filter(
        LtiRegistration.issuer == issuer,
        LtiRegistration.is_active.is_(True),
    )
    if client_id:
        query = query.filter(LtiRegistration.client_id == client_id)
    if deployment_id:
        query = query.filter(LtiRegistration.deployment_id == deployment_id)
    rows = query.limit(2).all()
    if len(rows) != 1:
        raise LtiLaunchError("registration_unavailable")
    registration = rows[0]
    if registration.is_development and not _is_development():
        raise LtiLaunchError("registration_unavailable")
    return registration


def create_login_redirect(
    db: Session,
    *,
    issuer: str,
    login_hint: str,
    target_link_uri: str,
    client_id: str | None,
    deployment_id: str | None,
    lti_message_hint: str | None,
) -> str:
    if not issuer or len(issuer) > 1000:
        raise LtiLaunchError("invalid_login_request")
    if not login_hint or len(login_hint) > 2000:
        raise LtiLaunchError("invalid_login_request")
    if client_id is not None and (not client_id or len(client_id) > 255):
        raise LtiLaunchError("invalid_login_request")
    if deployment_id is not None and (not deployment_id or len(deployment_id) > 255):
        raise LtiLaunchError("invalid_login_request")
    if lti_message_hint and len(lti_message_hint) > 2000:
        raise LtiLaunchError("invalid_login_request")
    registration = _registration_for_login(
        db,
        issuer=issuer,
        client_id=client_id,
        deployment_id=deployment_id,
    )
    if target_link_uri != registration.tool_launch_url:
        raise LtiLaunchError("target_mismatch")
    try:
        validate_lti_endpoint(
            registration.authorization_endpoint,
            allow_development_loopback=registration.is_development,
        )
    except ValueError as exc:
        raise LtiLaunchError("authorization_endpoint_unavailable") from exc

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        LtiLaunchAttempt(
            registration_id=registration.id,
            state_digest=digest_secret(state),
            nonce_digest=digest_secret(nonce),
            target_link_uri=target_link_uri,
            expires_at=now + LAUNCH_TTL,
        )
    )
    db.commit()
    params = {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "client_id": registration.client_id,
        "redirect_uri": registration.tool_launch_url,
        "login_hint": login_hint,
        "state": state,
        "nonce": nonce,
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint
    separator = "&" if urlparse(registration.authorization_endpoint).query else "?"
    return f"{registration.authorization_endpoint}{separator}{urlencode(params)}"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _consume_attempt(
    db: Session, state: str
) -> tuple[LtiLaunchAttempt, LtiRegistration]:
    if not state or len(state) > 200:
        raise LtiLaunchError("state_invalid")
    attempt = (
        db.query(LtiLaunchAttempt)
        .filter(LtiLaunchAttempt.state_digest == digest_secret(state))
        .with_for_update()
        .first()
    )
    now = datetime.now(UTC)
    if (
        attempt is None
        or attempt.consumed_at is not None
        or _aware(attempt.expires_at) <= now
    ):
        raise LtiLaunchError("state_invalid")
    registration = db.get(LtiRegistration, attempt.registration_id)
    if registration is None or not registration.is_active:
        raise LtiLaunchError("registration_unavailable")
    attempt.consumed_at = now
    db.commit()
    return attempt, registration


def _fetch_jwks(
    registration: LtiRegistration,
    http_get: Callable[..., requests.Response],
) -> dict[str, Any]:
    try:
        validate_lti_endpoint(
            registration.jwks_url,
            allow_development_loopback=registration.is_development,
        )
        response = http_get(
            registration.jwks_url,
            timeout=float(os.getenv("LTI_JWKS_TIMEOUT_SECONDS", "5")),
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        if len(response.content) > MAX_JWKS_BYTES:
            raise LtiLaunchError("jwks_unavailable")
        payload = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise LtiLaunchError("jwks_unavailable") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise LtiLaunchError("jwks_unavailable")
    return payload


def _decode_id_token(
    registration: LtiRegistration,
    id_token: str,
    http_get: Callable[..., requests.Response],
) -> dict[str, Any]:
    if not id_token or len(id_token) > 32_000:
        raise LtiLaunchError("token_invalid")
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise LtiLaunchError("token_invalid") from exc
    kid = header.get("kid")
    if (
        header.get("alg") != "RS256"
        or not isinstance(kid, str)
        or not kid
        or len(kid) > MAX_IDENTIFIER_LENGTH
    ):
        raise LtiLaunchError("token_invalid")
    jwks = _fetch_jwks(registration, http_get)
    matches = []
    for key in jwks["keys"]:
        if not isinstance(key, dict):
            continue
        key_ops = key.get("key_ops")
        if (
            key.get("kid") == kid
            and key.get("kty") == "RSA"
            and key.get("alg") in {None, "RS256"}
            and key.get("use") in {None, "sig"}
            and (key_ops is None or (isinstance(key_ops, list) and "verify" in key_ops))
        ):
            matches.append(key)
    if len(matches) != 1:
        raise LtiLaunchError("token_invalid")
    try:
        public_key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256").key
        claims = jwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            audience=registration.client_id,
            issuer=registration.issuer,
            leeway=CLOCK_SKEW_SECONDS,
            options={
                "require": ["iss", "aud", "exp", "iat", "nonce", "sub"],
            },
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise LtiLaunchError("token_invalid") from exc
    audience = claims.get("aud")
    authorized_party = claims.get("azp")
    if isinstance(audience, list) and len(audience) > 1:
        if authorized_party != registration.client_id:
            raise LtiLaunchError("token_invalid")
    elif authorized_party is not None and authorized_party != registration.client_id:
        raise LtiLaunchError("token_invalid")
    return claims


def _require_launch_claims(
    registration: LtiRegistration,
    attempt: LtiLaunchAttempt,
    claims: dict[str, Any],
) -> tuple[str, str, set[str]]:
    if claims.get(MESSAGE_TYPE) != "LtiResourceLinkRequest":
        raise LtiLaunchError("message_type_invalid")
    if claims.get(VERSION) != "1.3.0":
        raise LtiLaunchError("version_invalid")
    if claims.get(DEPLOYMENT_ID) != registration.deployment_id:
        raise LtiLaunchError("deployment_mismatch")
    if (
        claims.get(TARGET_LINK_URI) != attempt.target_link_uri
        or attempt.target_link_uri != registration.tool_launch_url
    ):
        raise LtiLaunchError("target_mismatch")
    nonce = _bounded_string(claims.get("nonce"))
    if not secrets.compare_digest(digest_secret(nonce), attempt.nonce_digest):
        raise LtiLaunchError("nonce_mismatch")
    subject = _bounded_string(claims.get("sub"))
    resource_link = claims.get(RESOURCE_LINK)
    if not isinstance(resource_link, dict):
        raise LtiLaunchError("resource_link_invalid")
    _bounded_string(resource_link.get("id"))
    context = claims.get(CONTEXT)
    if not isinstance(context, dict):
        raise LtiLaunchError("context_invalid")
    context_id = _bounded_string(context.get("id"))
    roles = claims.get(ROLES)
    if not isinstance(roles, list) or not all(isinstance(item, str) for item in roles):
        raise LtiLaunchError("roles_invalid")
    mapped_roles = {ROLE_MAP[item] for item in roles if item in ROLE_MAP}
    if not mapped_roles:
        raise LtiLaunchError("role_unavailable")
    return subject, context_id, mapped_roles


def _resolve_bound_access(
    db: Session,
    registration: LtiRegistration,
    subject: str,
    context_id: str,
    mapped_roles: set[str],
) -> LtiLaunchResult:
    subject_binding = (
        db.query(LtiSubjectBinding)
        .filter(
            LtiSubjectBinding.registration_id == registration.id,
            LtiSubjectBinding.platform_subject == subject,
        )
        .first()
    )
    context_binding = (
        db.query(LtiContextBinding)
        .filter(
            LtiContextBinding.registration_id == registration.id,
            LtiContextBinding.platform_context_id == context_id,
        )
        .first()
    )
    if subject_binding is None or context_binding is None:
        raise LtiLaunchError("binding_unavailable")
    user = db.get(User, subject_binding.user_id)
    course = db.get(Course, context_binding.course_id)
    organization = db.get(Organization, registration.organization_id)
    if (
        user is None
        or not user.is_active
        or course is None
        or course.organization_id != registration.organization_id
        or organization is None
        or not organization.is_active
    ):
        raise LtiLaunchError("binding_unavailable")

    course_membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == user.id,
            CourseMembership.organization_id == registration.organization_id,
            CourseMembership.is_active.is_(True),
        )
        .first()
    )
    resolved_role = None
    if (
        course_membership is not None
        and course_membership.role != "administrator"
        and course_membership.role in mapped_roles
    ):
        resolved_role = course_membership.role
    if resolved_role is None and "administrator" in mapped_roles:
        org_admin = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == registration.organization_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.role == "administrator",
                OrganizationMembership.is_active.is_(True),
            )
            .first()
        )
        if org_admin is not None:
            resolved_role = "administrator"
    if resolved_role is None:
        raise LtiLaunchError("role_mismatch")
    return LtiLaunchResult(
        registration_id=registration.id,
        organization_id=registration.organization_id,
        course_id=course.id,
        user_id=user.id,
        course_title=course.title,
        display_name=user.display_name,
        role=resolved_role,
    )


def _audit(
    db: Session,
    *,
    outcome: str,
    reason_code: str,
    registration: LtiRegistration | None = None,
    result: LtiLaunchResult | None = None,
) -> None:
    db.add(
        LtiLaunchAuditEvent(
            registration_id=(
                result.registration_id if result else getattr(registration, "id", None)
            ),
            organization_id=(
                result.organization_id
                if result
                else getattr(registration, "organization_id", None)
            ),
            course_id=result.course_id if result else None,
            user_id=result.user_id if result else None,
            outcome=outcome,
            reason_code=reason_code,
        )
    )
    db.commit()


def validate_launch(
    db: Session,
    *,
    state: str,
    id_token: str,
    http_get: Callable[..., requests.Response] | None = None,
) -> LtiLaunchResult:
    registration: LtiRegistration | None = None
    try:
        attempt, registration = _consume_attempt(db, state)
        if registration.is_development and not _is_development():
            raise LtiLaunchError("registration_unavailable")
        claims = _decode_id_token(registration, id_token, http_get or requests.get)
        subject, context_id, mapped_roles = _require_launch_claims(
            registration, attempt, claims
        )
        capture_unbound_candidates(
            db,
            registration=registration,
            subject=subject,
            context_id=context_id,
        )
        result = _resolve_bound_access(
            db, registration, subject, context_id, mapped_roles
        )
        _audit(db, outcome="accepted", reason_code="launch_verified", result=result)
        return result
    except LtiLaunchError as exc:
        if registration is not None:
            _audit(
                db,
                outcome="rejected",
                reason_code=exc.reason_code,
                registration=registration,
            )
        raise


def login_http_error(exc: LtiLaunchError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "lti_login_unavailable",
            "message": "LTI login could not be started for this registration.",
        },
    )
