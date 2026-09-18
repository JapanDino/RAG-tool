from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.models import (
    Course,
    LtiBindingCandidate,
    LtiBindingEvent,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    OrganizationMembership,
    User,
)

CANDIDATE_TTL_DAYS = 30
MAX_PENDING_CANDIDATES = 200


class LtiBindingError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(registration_id: int, candidate_type: str, identifier: str) -> str:
    material = f"{registration_id}:{candidate_type}:{identifier}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _registration(
    db: Session, *, organization_id: int, registration_id: int
) -> LtiRegistration:
    registration = db.get(LtiRegistration, registration_id)
    if registration is None or registration.organization_id != organization_id:
        raise LtiBindingError("registration_not_found")
    return registration


def capture_unbound_candidates(
    db: Session,
    *,
    registration: LtiRegistration,
    subject: str,
    context_id: str,
) -> int:
    """Quarantine only identifiers missing an explicit binding.

    This must be called only after signature and mandatory launch claims have
    been validated. The caller owns the transaction and audit commit.
    """

    missing: list[tuple[str, str]] = []
    subject_bound = (
        db.query(LtiSubjectBinding.id)
        .filter(
            LtiSubjectBinding.registration_id == registration.id,
            LtiSubjectBinding.platform_subject == subject,
        )
        .first()
    )
    if subject_bound is None:
        missing.append(("subject", subject))
    context_bound = (
        db.query(LtiContextBinding.id)
        .filter(
            LtiContextBinding.registration_id == registration.id,
            LtiContextBinding.platform_context_id == context_id,
        )
        .first()
    )
    if context_bound is None:
        missing.append(("context", context_id))

    now = _now()
    expires_at = now + timedelta(days=CANDIDATE_TTL_DAYS)
    captured = 0
    stale_candidates = (
        db.query(LtiBindingCandidate)
        .filter(
            LtiBindingCandidate.registration_id == registration.id,
            LtiBindingCandidate.status == "pending",
            LtiBindingCandidate.expires_at <= now,
        )
        .all()
    )
    _expire_pending(stale_candidates, now)
    pending_count = (
        db.query(LtiBindingCandidate.id)
        .filter(
            LtiBindingCandidate.registration_id == registration.id,
            LtiBindingCandidate.status == "pending",
        )
        .count()
    )
    for candidate_type, identifier in missing:
        identifier_digest = _digest(registration.id, candidate_type, identifier)
        candidate = (
            db.query(LtiBindingCandidate)
            .filter(
                LtiBindingCandidate.registration_id == registration.id,
                LtiBindingCandidate.candidate_type == candidate_type,
                LtiBindingCandidate.identifier_digest == identifier_digest,
            )
            .first()
        )
        if candidate is None:
            if pending_count >= MAX_PENDING_CANDIDATES:
                continue
            candidate = LtiBindingCandidate(
                registration_id=registration.id,
                organization_id=registration.organization_id,
                candidate_type=candidate_type,
                identifier_digest=identifier_digest,
                platform_identifier=identifier,
                status="pending",
                seen_count=1,
                first_seen_at=now,
                last_seen_at=now,
                expires_at=expires_at,
            )
            try:
                with db.begin_nested():
                    db.add(candidate)
                    db.flush([candidate])
            except IntegrityError:
                # Another verified launch may insert the same opaque identifier
                # between our lookup and flush. Recover inside the outer launch
                # transaction and count this as another sighting.
                candidate = (
                    db.query(LtiBindingCandidate)
                    .filter(
                        LtiBindingCandidate.registration_id == registration.id,
                        LtiBindingCandidate.candidate_type == candidate_type,
                        LtiBindingCandidate.identifier_digest == identifier_digest,
                    )
                    .with_for_update()
                    .one()
                )
            else:
                pending_count += 1
                captured += 1
                continue
        if candidate.status != "pending" and pending_count >= MAX_PENDING_CANDIDATES:
            continue
        if candidate.status != "pending":
            pending_count += 1
        candidate.platform_identifier = identifier
        candidate.status = "pending"
        candidate.seen_count += 1
        candidate.last_seen_at = now
        candidate.expires_at = expires_at
        candidate.resolved_at = None
        candidate.resolved_by_user_id = None
        candidate.target_user_id = None
        candidate.target_course_id = None
        captured += 1
    db.flush()
    return captured


def _expire_pending(candidates: list[LtiBindingCandidate], now: datetime) -> bool:
    changed = False
    for candidate in candidates:
        if candidate.status == "pending" and _as_utc(candidate.expires_at) <= now:
            candidate.status = "expired"
            candidate.platform_identifier = None
            candidate.resolved_at = now
            changed = True
    return changed


def expire_overdue_binding_candidates(
    db: Session, *, limit: int = 1000, now: datetime | None = None
) -> int:
    """Clear overdue plaintext independently of launches and administrator traffic."""

    if limit < 1:
        raise ValueError("limit must be positive")
    cutoff = now or _now()
    candidates = (
        db.query(LtiBindingCandidate)
        .filter(
            LtiBindingCandidate.status == "pending",
            LtiBindingCandidate.expires_at <= cutoff,
        )
        .order_by(LtiBindingCandidate.expires_at.asc(), LtiBindingCandidate.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    _expire_pending(candidates, cutoff)
    db.flush()
    return len(candidates)


def _candidate_out(candidate: LtiBindingCandidate) -> dict:
    return {
        "id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "identifier_hint": candidate.identifier_digest[:12],
        "seen_count": candidate.seen_count,
        "first_seen_at": candidate.first_seen_at,
        "last_seen_at": candidate.last_seen_at,
        "expires_at": candidate.expires_at,
    }


def binding_readiness(
    db: Session, *, organization_id: int, registration_id: int
) -> dict:
    registration = _registration(
        db, organization_id=organization_id, registration_id=registration_id
    )
    candidates = (
        db.query(LtiBindingCandidate)
        .filter(
            LtiBindingCandidate.registration_id == registration.id,
            LtiBindingCandidate.organization_id == organization_id,
        )
        .order_by(
            LtiBindingCandidate.last_seen_at.desc(), LtiBindingCandidate.id.desc()
        )
        .all()
    )
    if _expire_pending(candidates, _now()):
        db.flush()

    memberships = (
        db.query(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.display_name.asc(), User.id.asc())
        .all()
    )
    courses = (
        db.query(Course)
        .filter(Course.organization_id == organization_id)
        .order_by(Course.title.asc(), Course.id.asc())
        .all()
    )
    return {
        "registration_id": registration.id,
        "registration_active": registration.is_active,
        "candidates": [
            _candidate_out(candidate)
            for candidate in candidates
            if candidate.status == "pending"
        ],
        "users": [
            {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "organization_role": membership.role,
            }
            for membership, user in memberships
        ],
        "courses": [{"id": course.id, "title": course.title} for course in courses],
    }


def _pending_candidate(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    candidate_id: int,
) -> tuple[LtiRegistration, LtiBindingCandidate, datetime]:
    registration = _registration(
        db, organization_id=organization_id, registration_id=registration_id
    )
    candidate = (
        db.query(LtiBindingCandidate)
        .filter(
            LtiBindingCandidate.id == candidate_id,
            LtiBindingCandidate.registration_id == registration.id,
            LtiBindingCandidate.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    now = _now()
    if candidate is None:
        raise LtiBindingError("candidate_not_found")
    if (
        candidate.status != "pending"
        or candidate.platform_identifier is None
        or _as_utc(candidate.expires_at) <= now
    ):
        raise LtiBindingError("candidate_unavailable")
    return registration, candidate, now


def bind_candidate(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    candidate_id: int,
    target_id: int,
    actor_user_id: int | None,
) -> dict:
    registration, candidate, now = _pending_candidate(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        candidate_id=candidate_id,
    )
    if candidate.candidate_type == "subject":
        user = db.get(User, target_id)
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == target_id,
                OrganizationMembership.is_active.is_(True),
            )
            .first()
        )
        if user is None or not user.is_active or membership is None:
            raise LtiBindingError("target_not_found")
        db.add(
            LtiSubjectBinding(
                registration_id=registration.id,
                user_id=user.id,
                platform_subject=candidate.platform_identifier,
            )
        )
        candidate.target_user_id = user.id
    else:
        course = db.get(Course, target_id)
        if course is None or course.organization_id != organization_id:
            raise LtiBindingError("target_not_found")
        db.add(
            LtiContextBinding(
                registration_id=registration.id,
                course_id=course.id,
                platform_context_id=candidate.platform_identifier,
            )
        )
        candidate.target_course_id = course.id

    candidate.status = "bound"
    candidate.platform_identifier = None
    candidate.resolved_at = now
    candidate.resolved_by_user_id = actor_user_id
    db.add(
        LtiBindingEvent(
            organization_id=organization_id,
            registration_id=registration.id,
            candidate_id=candidate.id,
            actor_user_id=actor_user_id,
            event_type="bound",
            target_user_id=candidate.target_user_id,
            target_course_id=candidate.target_course_id,
        )
    )
    db.flush()
    return {
        "candidate_id": candidate.id,
        "status": candidate.status,
        "candidate_type": candidate.candidate_type,
        "target_id": target_id,
    }


def dismiss_candidate(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    candidate_id: int,
    actor_user_id: int | None,
) -> dict:
    registration, candidate, now = _pending_candidate(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        candidate_id=candidate_id,
    )
    candidate.status = "dismissed"
    candidate.platform_identifier = None
    candidate.resolved_at = now
    candidate.resolved_by_user_id = actor_user_id
    db.add(
        LtiBindingEvent(
            organization_id=organization_id,
            registration_id=registration.id,
            candidate_id=candidate.id,
            actor_user_id=actor_user_id,
            event_type="dismissed",
        )
    )
    db.flush()
    return {
        "candidate_id": candidate.id,
        "status": candidate.status,
        "candidate_type": candidate.candidate_type,
        "target_id": None,
    }
