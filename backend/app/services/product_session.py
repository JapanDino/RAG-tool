from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy.orm import Session

from ..models.models import (
    Course,
    CourseMembership,
    LtiProductSession,
    LtiRegistration,
    Organization,
    User,
)

DEFAULT_SESSION_TTL_MINUTES = 60
_DEVELOPMENT_CSRF_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True)
class SessionCookiePolicy:
    name: str
    secure: bool
    samesite: str
    max_age: int


@dataclass(frozen=True)
class IssuedProductSession:
    row: LtiProductSession
    raw_token: str


@dataclass(frozen=True)
class ResolvedProductSession:
    row: LtiProductSession
    registration: LtiRegistration
    user: User
    course: Course


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def session_ttl_minutes() -> int:
    raw = os.getenv("LTI_SESSION_TTL_MINUTES", str(DEFAULT_SESSION_TTL_MINUTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("LTI_SESSION_TTL_MINUTES must be an integer") from exc
    if value != DEFAULT_SESSION_TTL_MINUTES:
        raise RuntimeError("LTI_SESSION_TTL_MINUTES must be 60")
    return value


def session_cookie_policy() -> SessionCookiePolicy:
    production = _is_production()
    secure = production or os.getenv("LTI_SESSION_COOKIE_SECURE", "0").strip() in {
        "1",
        "true",
        "True",
    }
    default_samesite = "none" if production else "lax"
    samesite = os.getenv("LTI_SESSION_COOKIE_SAMESITE", default_samesite).lower()
    if samesite not in {"strict", "lax", "none"}:
        raise RuntimeError("LTI_SESSION_COOKIE_SAMESITE is invalid")
    if samesite == "none" and not secure:
        raise RuntimeError("SameSite=None requires a Secure session cookie")
    return SessionCookiePolicy(
        name="__Host-rag_lti_session" if production else "rag_lti_session",
        secure=secure,
        samesite=samesite,
        max_age=session_ttl_minutes() * 60,
    )


def _csrf_secret() -> bytes:
    configured = os.getenv("LTI_SESSION_CSRF_SECRET", "")
    if _is_production():
        if len(configured) < 32:
            raise RuntimeError(
                "LTI_SESSION_CSRF_SECRET must contain at least 32 characters"
            )
        return configured.encode("utf-8")
    return configured.encode("utf-8") if configured else _DEVELOPMENT_CSRF_SECRET


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def csrf_token_for_session(raw_token: str) -> str:
    return hmac.new(
        _csrf_secret(), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def valid_csrf_token(raw_token: str, supplied: str | None) -> bool:
    if supplied is None or len(supplied) != 64:
        return False
    return secrets.compare_digest(csrf_token_for_session(raw_token), supplied)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def issue_product_session(
    db: Session,
    *,
    registration_id: int,
    user_id: int,
    course_id: int,
    role: str,
) -> IssuedProductSession:
    if role not in {"student", "instructor"}:
        raise ValueError("unsupported product-session role")
    now = datetime.now(UTC)
    registration = (
        db.query(LtiRegistration)
        .filter(LtiRegistration.id == registration_id)
        .with_for_update()
        .one_or_none()
    )
    if registration is None:
        raise ValueError("product-session registration is unavailable")
    active_rows = (
        db.query(LtiProductSession)
        .filter(
            LtiProductSession.registration_id == registration_id,
            LtiProductSession.user_id == user_id,
            LtiProductSession.course_id == course_id,
            LtiProductSession.revoked_at.is_(None),
        )
        .with_for_update()
        .all()
    )
    for row in active_rows:
        row.revoked_at = now
    raw_token = secrets.token_urlsafe(48)
    row = LtiProductSession(
        registration_id=registration_id,
        user_id=user_id,
        course_id=course_id,
        role=role,
        token_digest=token_digest(raw_token),
        expires_at=now + timedelta(minutes=session_ttl_minutes()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return IssuedProductSession(row=row, raw_token=raw_token)


def resolve_product_session(
    db: Session, raw_token: str | None
) -> ResolvedProductSession | None:
    if not raw_token or len(raw_token) > 200:
        return None
    row = (
        db.query(LtiProductSession)
        .filter(LtiProductSession.token_digest == token_digest(raw_token))
        .first()
    )
    if (
        row is None
        or row.revoked_at is not None
        or _aware(row.expires_at) <= datetime.now(UTC)
    ):
        return None
    registration = db.get(LtiRegistration, row.registration_id)
    user = db.get(User, row.user_id)
    course = db.get(Course, row.course_id)
    organization = (
        db.get(Organization, registration.organization_id) if registration else None
    )
    membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.organization_id == registration.organization_id,
            CourseMembership.course_id == row.course_id,
            CourseMembership.user_id == row.user_id,
            CourseMembership.role == row.role,
            CourseMembership.is_active.is_(True),
        )
        .first()
        if registration is not None
        else None
    )
    if (
        registration is None
        or not registration.is_active
        or user is None
        or not user.is_active
        or course is None
        or course.organization_id != registration.organization_id
        or organization is None
        or not organization.is_active
        or membership is None
    ):
        return None
    return ResolvedProductSession(
        row=row,
        registration=registration,
        user=user,
        course=course,
    )


def revoke_product_session(db: Session, session_id: int) -> None:
    row = db.get(LtiProductSession, session_id)
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = datetime.now(UTC)
    db.commit()


def set_product_session_cookie(response: Response, raw_token: str) -> None:
    policy = session_cookie_policy()
    response.set_cookie(
        key=policy.name,
        value=raw_token,
        max_age=policy.max_age,
        httponly=True,
        secure=policy.secure,
        samesite=policy.samesite,
        path="/",
    )


def clear_product_session_cookie(response: Response) -> None:
    policy = session_cookie_policy()
    response.delete_cookie(
        key=policy.name,
        httponly=True,
        secure=policy.secure,
        samesite=policy.samesite,
        path="/",
    )
