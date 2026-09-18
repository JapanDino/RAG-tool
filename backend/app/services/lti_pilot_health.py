from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.models import LtiBindingCandidate, LtiLaunchAuditEvent, LtiRegistration

WINDOW_DAYS = 7
REPEATED_REJECTION_THRESHOLD = 3
NO_SUCCESS_THRESHOLD = 5

FAILURE_FAMILIES = {
    "binding_required": frozenset(
        {
            "binding_unavailable",
            "context_invalid",
            "role_mismatch",
            "role_unavailable",
        }
    ),
    "platform_configuration": frozenset(
        {
            "authorization_endpoint_unavailable",
            "deployment_mismatch",
            "invalid_login_request",
            "message_type_invalid",
            "registration_unavailable",
            "resource_link_invalid",
            "target_mismatch",
            "version_invalid",
        }
    ),
    "signature_or_replay": frozenset(
        {
            "invalid_claim",
            "jwks_unavailable",
            "nonce_mismatch",
            "required_claim_missing",
            "roles_invalid",
            "state_invalid",
            "token_invalid",
        }
    ),
}
FAILURE_FAMILY_BY_REASON = {
    reason: family for family, reasons in FAILURE_FAMILIES.items() for reason in reasons
}
PAUSE_TRIGGER_ORDER = ("no_verified_launch", "repeated_rejections")


def _count_by_value(rows: list[tuple[str, int]]) -> dict[str, int]:
    return {str(value): int(count) for value, count in rows}


def pilot_launch_health(
    db: Session,
    *,
    organization_id: int,
    now: datetime | None = None,
) -> dict:
    generated_at = now or datetime.now(UTC)
    cutoff = generated_at - timedelta(days=WINDOW_DAYS)

    outcome_counts = _count_by_value(
        db.query(LtiLaunchAuditEvent.outcome, func.count(LtiLaunchAuditEvent.id))
        .join(
            LtiRegistration,
            LtiRegistration.id == LtiLaunchAuditEvent.registration_id,
        )
        .filter(
            LtiLaunchAuditEvent.organization_id == organization_id,
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
            LtiLaunchAuditEvent.created_at >= cutoff,
            LtiLaunchAuditEvent.outcome.in_(("accepted", "rejected")),
        )
        .group_by(LtiLaunchAuditEvent.outcome)
        .all()
    )
    accepted = outcome_counts.get("accepted", 0)
    rejected = outcome_counts.get("rejected", 0)
    known_launches = accepted + rejected

    reason_counts = _count_by_value(
        db.query(
            LtiLaunchAuditEvent.reason_code,
            func.count(LtiLaunchAuditEvent.id),
        )
        .join(
            LtiRegistration,
            LtiRegistration.id == LtiLaunchAuditEvent.registration_id,
        )
        .filter(
            LtiLaunchAuditEvent.organization_id == organization_id,
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
            LtiLaunchAuditEvent.created_at >= cutoff,
            LtiLaunchAuditEvent.outcome == "rejected",
        )
        .group_by(LtiLaunchAuditEvent.reason_code)
        .all()
    )
    family_counts: dict[str, int] = {}
    for reason, count in reason_counts.items():
        family = FAILURE_FAMILY_BY_REASON.get(reason, "other")
        family_counts[family] = family_counts.get(family, 0) + count
    failure_families = [
        {"code": code, "count": count}
        for code, count in sorted(
            family_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    pending_counts = _count_by_value(
        db.query(
            LtiBindingCandidate.candidate_type,
            func.count(LtiBindingCandidate.id),
        )
        .join(
            LtiRegistration,
            LtiRegistration.id == LtiBindingCandidate.registration_id,
        )
        .filter(
            LtiBindingCandidate.organization_id == organization_id,
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
            LtiBindingCandidate.status == "pending",
            LtiBindingCandidate.expires_at > generated_at,
        )
        .group_by(LtiBindingCandidate.candidate_type)
        .all()
    )
    pending_subjects = pending_counts.get("subject", 0)
    pending_contexts = pending_counts.get("context", 0)
    pending_total = pending_subjects + pending_contexts

    latest_outcomes = [
        str(outcome)
        for (outcome,) in (
            db.query(LtiLaunchAuditEvent.outcome)
            .join(
                LtiRegistration,
                LtiRegistration.id == LtiLaunchAuditEvent.registration_id,
            )
            .filter(
                LtiLaunchAuditEvent.organization_id == organization_id,
                LtiRegistration.organization_id == organization_id,
                LtiRegistration.is_development.is_(False),
                LtiLaunchAuditEvent.created_at >= cutoff,
                LtiLaunchAuditEvent.outcome.in_(("accepted", "rejected")),
            )
            .order_by(
                LtiLaunchAuditEvent.created_at.desc(),
                LtiLaunchAuditEvent.id.desc(),
            )
            .limit(REPEATED_REJECTION_THRESHOLD)
            .all()
        )
    ]
    triggers = set()
    if known_launches >= NO_SUCCESS_THRESHOLD and accepted == 0:
        triggers.add("no_verified_launch")
    if len(latest_outcomes) == REPEATED_REJECTION_THRESHOLD and set(
        latest_outcomes
    ) == {"rejected"}:
        triggers.add("repeated_rejections")
    pause_triggers = [code for code in PAUSE_TRIGGER_ORDER if code in triggers]

    if pending_total:
        state = "review_bindings"
    elif rejected or pause_triggers:
        state = "review_failures"
    elif known_launches:
        state = "stable"
    else:
        state = "not_started"

    active_registrations = (
        db.query(func.count(LtiRegistration.id))
        .filter(
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
            LtiRegistration.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    last_known_launch_at = (
        db.query(func.max(LtiLaunchAuditEvent.created_at))
        .join(
            LtiRegistration,
            LtiRegistration.id == LtiLaunchAuditEvent.registration_id,
        )
        .filter(
            LtiLaunchAuditEvent.organization_id == organization_id,
            LtiRegistration.organization_id == organization_id,
            LtiRegistration.is_development.is_(False),
            LtiLaunchAuditEvent.created_at >= cutoff,
            LtiLaunchAuditEvent.outcome.in_(("accepted", "rejected")),
        )
        .scalar()
    )
    return {
        "schema_version": 1,
        "window_days": WINDOW_DAYS,
        "state": state,
        "known_launches": known_launches,
        "accepted_launches": accepted,
        "rejected_launches": rejected,
        "active_registrations": int(active_registrations),
        "pending_bindings": {
            "total": pending_total,
            "subjects": pending_subjects,
            "contexts": pending_contexts,
        },
        "failure_families": failure_families,
        "pause_triggers": pause_triggers,
        "last_known_launch_at": last_known_launch_at,
        "generated_at": generated_at,
    }
