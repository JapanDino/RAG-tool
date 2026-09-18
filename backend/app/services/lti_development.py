from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session

from ..models.models import (
    Course,
    CourseMembership,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    OrganizationMembership,
    User,
)
from .lti import (
    CONTEXT,
    DEPLOYMENT_ID,
    MESSAGE_TYPE,
    RESOURCE_LINK,
    ROLES,
    TARGET_LINK_URI,
    VERSION,
)

LOCAL_CLIENT_ID = "rag-tool-local"
LOCAL_DEPLOYMENT_ID = "rag-tool-local-school"
LOCAL_KEY_ID = "rag-tool-local-ephemeral"

ROLE_URIS = {
    "student": "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner",
    "instructor": "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor",
    "program_designer": "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper",
    "administrator": "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
}


def _b64uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@lru_cache(maxsize=1)
def local_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def local_jwks() -> dict:
    numbers = local_private_key().public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": LOCAL_KEY_ID,
                "n": _b64uint(numbers.n),
                "e": _b64uint(numbers.e),
            }
        ]
    }


def encode_login_hint(registration_id: int, subject: str, context_id: str) -> str:
    payload = json.dumps(
        {"r": registration_id, "s": subject, "c": context_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_login_hint(value: str) -> tuple[int, str, str]:
    if not value or len(value) > 2000:
        raise ValueError("invalid login hint")
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        registration_id = int(payload["r"])
        subject = payload["s"]
        context_id = payload["c"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid login hint") from exc
    if (
        not isinstance(subject, str)
        or not isinstance(context_id, str)
        or not subject
        or not context_id
        or len(subject) > 255
        or len(context_id) > 255
    ):
        raise ValueError("invalid login hint")
    return registration_id, subject, context_id


def development_role(
    db: Session, registration: LtiRegistration, user_id: int, course_id: int
) -> str | None:
    membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.organization_id == registration.organization_id,
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == user_id,
            CourseMembership.is_active.is_(True),
        )
        .first()
    )
    if (
        membership is not None
        and membership.role != "administrator"
        and membership.role in ROLE_URIS
    ):
        return membership.role
    admin = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == registration.organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.role == "administrator",
            OrganizationMembership.is_active.is_(True),
        )
        .first()
    )
    return "administrator" if admin is not None else None


def issue_local_token(
    db: Session,
    *,
    registration: LtiRegistration,
    subject: str,
    context_id: str,
    nonce: str,
) -> str:
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
        raise ValueError("binding unavailable")
    user = db.get(User, subject_binding.user_id)
    course = db.get(Course, context_binding.course_id)
    if user is None or course is None or not user.is_active:
        raise ValueError("binding unavailable")
    role = development_role(db, registration, user.id, course.id)
    if role is None:
        raise ValueError("role unavailable")
    now = datetime.now(UTC)
    claims = {
        "iss": registration.issuer,
        "aud": registration.client_id,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        MESSAGE_TYPE: "LtiResourceLinkRequest",
        VERSION: "1.3.0",
        DEPLOYMENT_ID: registration.deployment_id,
        TARGET_LINK_URI: registration.tool_launch_url,
        RESOURCE_LINK: {"id": f"local-resource-{course.id}"},
        ROLES: [ROLE_URIS[role]],
        CONTEXT: {
            "id": context_id,
            "title": course.title,
            "type": ["http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering"],
        },
    }
    return jwt.encode(
        claims,
        local_private_key(),
        algorithm="RS256",
        headers={"kid": LOCAL_KEY_ID},
    )


def local_subject(user_id: int) -> str:
    return f"local-subject-{user_id}-{secrets.token_hex(4)}"
