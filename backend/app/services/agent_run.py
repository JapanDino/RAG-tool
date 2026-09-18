from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    Course,
    CourseMembership,
    LtiProductSession,
    LtiRegistration,
    Organization,
    Program,
    User,
)
from ..schemas.agent_api import AgentMessageIn
from .agent_policy import WORKFLOW_REGISTRY, AgentRole, route_message
from .authorization import Principal, organization_roles
from .organization_agent_policy import (
    AgentPolicyScopeDenied,
    lock_and_assert_agent_workflow_enabled,
)

CONTRACT_VERSION = "agent.v1"
POLICY_VERSION = "role-policy.v1"
EVENT_REPLAY_HOURS = 24
_DEVELOPMENT_IDEMPOTENCY_SECRET = b"agent-v1-development-idempotency-secret"


@dataclass(frozen=True)
class AgentTrustedContext:
    organization_id: int
    course_id: int | None
    user_id: int
    role: AgentRole
    product_session_id: int | None


def _deny() -> None:
    raise HTTPException(status_code=404, detail="resource not found")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def resolve_agent_context(
    db: Session,
    principal: Principal,
    *,
    organization_id: int | None = None,
) -> AgentTrustedContext:
    if principal.bypass or principal.user_id is None:
        _deny()

    if principal.auth_mode == "lti_session":
        if principal.session_id is None or principal.course_scope_id is None:
            _deny()
        product_session = db.get(LtiProductSession, principal.session_id)
        course = db.get(Course, principal.course_scope_id)
        registration = (
            db.get(LtiRegistration, product_session.registration_id)
            if product_session is not None
            else None
        )
        organization = (
            db.get(Organization, registration.organization_id)
            if registration is not None
            else None
        )
        user = db.get(User, principal.user_id)
        membership = (
            db.query(CourseMembership.id)
            .filter(
                CourseMembership.organization_id == registration.organization_id,
                CourseMembership.course_id == product_session.course_id,
                CourseMembership.user_id == product_session.user_id,
                CourseMembership.role == product_session.role,
                CourseMembership.is_active.is_(True),
            )
            .first()
            if registration is not None and product_session is not None
            else None
        )
        if (
            product_session is None
            or product_session.revoked_at is not None
            or _aware(product_session.expires_at) <= datetime.now(UTC)
            or product_session.user_id != principal.user_id
            or product_session.course_id != principal.course_scope_id
            or product_session.role not in {"student", "instructor"}
            or principal.registration_id != product_session.registration_id
            or registration is None
            or not registration.is_active
            or course is None
            or course.organization_id is None
            or course.organization_id != registration.organization_id
            or organization is None
            or not organization.is_active
            or (organization_id is not None and organization.id != organization_id)
            or user is None
            or not user.is_active
            or membership is None
        ):
            _deny()
        return AgentTrustedContext(
            organization_id=int(course.organization_id),
            course_id=course.id,
            user_id=principal.user_id,
            role=product_session.role,
            product_session_id=product_session.id,
        )

    roles = organization_roles(db, principal)
    if organization_id is None:
        if len(roles) != 1:
            _deny()
        selected_organization_id, role = next(iter(roles.items()))
    else:
        selected_organization_id = organization_id
        role = roles.get(selected_organization_id)
        if role is None:
            _deny()
    organization = db.get(Organization, selected_organization_id)
    user = db.get(User, principal.user_id)
    if (
        role
        not in {
            "student",
            "instructor",
            "methodologist",
            "program_designer",
            "administrator",
        }
        or organization is None
        or not organization.is_active
        or user is None
        or not user.is_active
    ):
        _deny()
    return AgentTrustedContext(
        organization_id=selected_organization_id,
        course_id=None,
        user_id=principal.user_id,
        role=role,
        product_session_id=None,
    )


def _idempotency_secret() -> bytes:
    configured = os.getenv("AGENT_IDEMPOTENCY_SECRET", "")
    production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    if production and len(configured) < 32:
        raise RuntimeError(
            "AGENT_IDEMPOTENCY_SECRET must contain at least 32 characters"
        )
    return configured.encode("utf-8") if configured else _DEVELOPMENT_IDEMPOTENCY_SECRET


def validate_idempotency_key(value: str | None) -> str:
    normalized = (value or "").strip()
    if not 8 <= len(normalized) <= 128:
        raise HTTPException(status_code=400, detail="invalid idempotency key")
    if not all(
        char.isascii() and (char.isalnum() or char in "_-.") for char in normalized
    ):
        raise HTTPException(status_code=400, detail="invalid idempotency key")
    return normalized


def _idempotency_digest(context: AgentTrustedContext, raw_key: str) -> str:
    scope = ":".join(
        (
            str(context.organization_id),
            str(context.course_id or 0),
            str(context.user_id),
            context.role,
            str(context.product_session_id or 0),
            raw_key,
        )
    )
    return hmac.new(
        _idempotency_secret(), scope.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _input_digest(context: AgentTrustedContext, payload: AgentMessageIn) -> str:
    selection = payload.selection
    canonical = json.dumps(
        {
            "organization_id": context.organization_id,
            "course_id": context.course_id,
            "user_id": context.user_id,
            "role": context.role,
            "product_session_id": context.product_session_id,
            "message": payload.message,
            "module_ref": selection.module_ref if selection else None,
            "evidence_ref": selection.evidence_ref if selection else None,
            "program_ref": selection.program_ref if selection else None,
            "organization_ref": selection.organization_ref if selection else None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hmac.new(
        _idempotency_secret(), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _new_opaque(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def agent_reference_secret() -> bytes:
    """Return the configured server secret for signed opaque resource refs."""
    return _idempotency_secret()


def _owned_conversation_exists(
    db: Session, context: AgentTrustedContext, conversation_id: str
) -> bool:
    return (
        db.query(AgentRun.id)
        .filter(
            AgentRun.conversation_id == conversation_id,
            AgentRun.organization_id == context.organization_id,
            AgentRun.course_id == context.course_id,
            AgentRun.user_id == context.user_id,
            AgentRun.role == context.role,
        )
        .first()
        is not None
    )


def create_or_replay_agent_run(
    db: Session,
    *,
    principal: Principal,
    payload: AgentMessageIn,
    idempotency_key: str | None,
) -> AgentRun:
    program_selection = payload.selection.program_ref if payload.selection else None
    organization_selection = (
        payload.selection.organization_ref if payload.selection else None
    )
    selected_organization_id = None
    if program_selection is not None:
        parts = program_selection.split("_")
        if len(parts) != 4 or parts[0] != "program":
            _deny()
        try:
            selected_program_id = int(parts[1])
        except ValueError:
            _deny()
        selected_program = db.get(Program, selected_program_id)
        if selected_program is None or not selected_program.is_active:
            _deny()
        selected_organization_id = selected_program.organization_id
    if organization_selection is not None:
        parts = organization_selection.split("_")
        if len(parts) != 3 or parts[0] != "organization":
            _deny()
        try:
            selected_organization_id = int(parts[1])
        except ValueError:
            _deny()
        selected_organization = db.get(Organization, selected_organization_id)
        if selected_organization is None or not selected_organization.is_active:
            _deny()
    context = resolve_agent_context(
        db, principal, organization_id=selected_organization_id
    )
    raw_key = validate_idempotency_key(idempotency_key)
    digest = _idempotency_digest(context, raw_key)
    existing = db.query(AgentRun).filter(AgentRun.idempotency_digest == digest).first()
    if existing is not None:
        if not hmac.compare_digest(
            existing.input_digest, _input_digest(context, payload)
        ):
            raise HTTPException(status_code=409, detail="idempotency payload conflict")
        try:
            lock_and_assert_agent_workflow_enabled(
                db,
                organization_id=context.organization_id,
                role=context.role,
                workflow=existing.workflow,
            )
        except AgentPolicyScopeDenied:
            _deny()
        return existing

    if payload.conversation_id is not None and not _owned_conversation_exists(
        db, context, payload.conversation_id
    ):
        _deny()

    decision = route_message(
        role=context.role,
        message=payload.message,
        has_course_scope=context.course_id is not None,
        has_material_scope=(
            payload.selection is not None and payload.selection.module_ref is not None
        ),
    )
    try:
        lock_and_assert_agent_workflow_enabled(
            db,
            organization_id=context.organization_id,
            role=context.role,
            workflow=decision.workflow,
        )
    except AgentPolicyScopeDenied:
        _deny()
    if (
        payload.selection is not None
        and payload.selection.evidence_ref is not None
        and decision.workflow
        not in {
            "learner.locate_source.v1",
            "instructor.inspect_audit.v1",
            "instructor.draft_improvement.v1",
            "instructor.preview_canvas_change.v1",
        }
    ):
        _deny()
    program_ref = payload.selection.program_ref if payload.selection else None
    organization_ref = payload.selection.organization_ref if payload.selection else None
    program_workflow = bool(
        decision.workflow and decision.workflow.startswith("program.")
    )
    admin_organization_workflow = decision.workflow in {
        "admin.integration_readiness.v1",
        "admin.analytics_health.v1",
        "admin.policy_status.v1",
    }
    if (program_ref is not None) != program_workflow:
        _deny()
    if organization_ref is not None and not admin_organization_workflow:
        _deny()
    row = AgentRun(
        public_id=_new_opaque("run"),
        conversation_id=payload.conversation_id or _new_opaque("conv"),
        organization_id=context.organization_id,
        course_id=context.course_id,
        user_id=context.user_id,
        role=context.role,
        product_session_id=context.product_session_id,
        module_ref=payload.selection.module_ref if payload.selection else None,
        selection_ref=(
            payload.selection.evidence_ref
            or payload.selection.program_ref
            or payload.selection.organization_ref
            if payload.selection
            else None
        ),
        input_digest=_input_digest(context, payload),
        contract_version=CONTRACT_VERSION,
        policy_version=POLICY_VERSION,
        workflow=decision.workflow,
        route_state=decision.state,
        status=(
            "queued"
            if decision.workflow
            in {
                "learner.explain_material.v1",
                "learner.assessment_safe_hint.v1",
                "learner.self_check.v1",
                "learner.locate_source.v1",
                "instructor.course_summary.v1",
                "instructor.inspect_audit.v1",
                "instructor.inspect_question_gaps.v1",
                "instructor.draft_improvement.v1",
                "instructor.preview_canvas_change.v1",
                "program.inspect_map.v1",
                "program.inspect_gap.v1",
                "program.inspect_prerequisite.v1",
                "program.draft_review_note.v1",
                "admin.integration_readiness.v1",
                "admin.analytics_health.v1",
                "admin.policy_status.v1",
            }
            and (
                (
                    context.role in {"student", "instructor"}
                    and context.course_id is not None
                )
                or (
                    context.role
                    in {"methodologist", "program_designer", "administrator"}
                    and context.course_id is None
                    and decision.workflow
                    in {
                        "program.inspect_map.v1",
                        "program.inspect_gap.v1",
                        "program.inspect_prerequisite.v1",
                        "program.draft_review_note.v1",
                    }
                )
                or (
                    context.role == "administrator"
                    and context.course_id is None
                    and decision.workflow
                    in {
                        "admin.integration_readiness.v1",
                        "admin.analytics_health.v1",
                        "admin.policy_status.v1",
                    }
                    and organization_ref is not None
                )
            )
            else "completed" if decision.state == "routed" else "abstained"
        ),
        idempotency_digest=digest,
        label=decision.label,
        recovery_action=decision.recovery_action,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = (
            db.query(AgentRun).filter(AgentRun.idempotency_digest == digest).first()
        )
        if replay is None:
            raise
        if not hmac.compare_digest(
            replay.input_digest, _input_digest(context, payload)
        ):
            raise HTTPException(status_code=409, detail="idempotency payload conflict")
        return replay
    db.refresh(row)
    return row


def validate_agent_run_input(
    row: AgentRun,
    *,
    context: AgentTrustedContext,
    payload: AgentMessageIn,
) -> None:
    if not hmac.compare_digest(row.input_digest, _input_digest(context, payload)):
        raise HTTPException(status_code=409, detail="agent input conflict")


def owned_agent_run(db: Session, *, principal: Principal, public_id: str) -> AgentRun:
    if principal.user_id is None:
        _deny()
    row = (
        db.query(AgentRun)
        .filter(
            AgentRun.public_id == public_id,
            AgentRun.user_id == principal.user_id,
        )
        .first()
    )
    if row is None:
        _deny()
    context = resolve_agent_context(db, principal, organization_id=row.organization_id)
    if (
        row.organization_id != context.organization_id
        or row.course_id != context.course_id
        or row.role != context.role
    ):
        _deny()
    return row


def planned_step_count(row: AgentRun) -> int:
    if row.workflow is None:
        return 0
    return len(WORKFLOW_REGISTRY[row.workflow].tools)


def event_replay_available(row: AgentRun, *, now: datetime | None = None) -> bool:
    checked_at = now or datetime.now(UTC)
    return checked_at < _aware(row.updated_at) + timedelta(hours=EVENT_REPLAY_HOURS)


__all__ = [
    "CONTRACT_VERSION",
    "agent_reference_secret",
    "create_or_replay_agent_run",
    "event_replay_available",
    "owned_agent_run",
    "planned_step_count",
    "resolve_agent_context",
    "validate_agent_run_input",
]
