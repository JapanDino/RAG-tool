from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.models import (
    Organization,
    OrganizationAgentPolicy,
    OrganizationAgentPolicyEvent,
)
from ..schemas.organization_agent_policy import (
    AgentPolicyChangeOut,
    AgentPolicySettings,
    OrganizationAgentPolicyOut,
    OrganizationAgentPolicyPreviewOut,
)

DEFAULT_MODEL_MODE = "approved_host_with_safe_fallback"
ADMIN_GOVERNANCE_WORKFLOWS = frozenset(
    {
        "admin.integration_readiness.v1",
        "admin.analytics_health.v1",
        "admin.policy_status.v1",
    }
)


class AgentPolicyVersionConflict(Exception):
    pass


class AgentPolicyScopeDenied(Exception):
    pass


def _lock_organization(db: Session, organization_id: int) -> Organization:
    organization = (
        db.query(Organization)
        .filter(
            Organization.id == organization_id,
            Organization.is_active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if organization is None:
        raise AgentPolicyScopeDenied
    return organization


def _settings(policy: OrganizationAgentPolicy | None) -> AgentPolicySettings:
    if policy is None:
        return AgentPolicySettings()
    return AgentPolicySettings(
        learner_enabled=bool(policy.learner_enabled),
        instructor_enabled=bool(policy.instructor_enabled),
        program_enabled=bool(policy.program_enabled),
        model_mode=policy.model_mode,
    )


def _event_state(policy: OrganizationAgentPolicy) -> dict:
    return {
        **_settings(policy).model_dump(),
        "version": int(policy.version),
    }


def organization_agent_policy_out(
    policy: OrganizationAgentPolicy | None,
    organization_id: int,
) -> OrganizationAgentPolicyOut:
    settings = _settings(policy)
    return OrganizationAgentPolicyOut(
        organization_id=organization_id,
        **settings.model_dump(),
        version=int(policy.version) if policy is not None else 0,
        updated_at=policy.updated_at if policy is not None else None,
    )


def get_effective_agent_policy(
    db: Session, organization_id: int
) -> OrganizationAgentPolicyOut:
    policy = (
        db.query(OrganizationAgentPolicy)
        .filter(OrganizationAgentPolicy.organization_id == organization_id)
        .first()
    )
    return organization_agent_policy_out(policy, organization_id)


def _display(field: str, value: bool | str) -> str:
    if isinstance(value, bool):
        return "Доступен" if value else "На паузе"
    return (
        "Школьный AI-сервис с безопасным резервом"
        if value == DEFAULT_MODEL_MODE
        else "Только детерминированный режим"
    )


def preview_agent_policy(
    db: Session,
    *,
    organization_id: int,
    proposed: AgentPolicySettings,
) -> OrganizationAgentPolicyPreviewOut:
    current = get_effective_agent_policy(db, organization_id)
    labels = {
        "learner_enabled": "Помощник ученика",
        "instructor_enabled": "Помощник преподавателя",
        "program_enabled": "Команда образовательных программ",
        "model_mode": "Маршрут школьного AI-сервиса",
    }
    impacts = {
        "learner_enabled": "Новые и незавершённые задания ученика будут следовать этой настройке.",
        "instructor_enabled": "Новые и незавершённые задания преподавателя будут следовать этой настройке.",
        "program_enabled": "Новые и незавершённые проверки карты программы будут следовать этой настройке.",
        "model_mode": "Определяет, может ли агент обращаться к настроенному школьному AI-сервису.",
    }
    changes: list[AgentPolicyChangeOut] = []
    for field in labels:
        before = getattr(current, field)
        after = getattr(proposed, field)
        if before != after:
            changes.append(
                AgentPolicyChangeOut(
                    field=field,
                    label=labels[field],
                    before=_display(field, before),
                    after=_display(field, after),
                    impact=impacts[field],
                )
            )
    return OrganizationAgentPolicyPreviewOut(
        current=current,
        proposed=proposed,
        changes=changes,
    )


def update_agent_policy(
    db: Session,
    *,
    organization_id: int,
    proposed: AgentPolicySettings,
    expected_version: int,
    actor_user_id: int | None,
) -> OrganizationAgentPolicyOut:
    _lock_organization(db, organization_id)
    policy = (
        db.query(OrganizationAgentPolicy)
        .filter(OrganizationAgentPolicy.organization_id == organization_id)
        .with_for_update()
        .first()
    )
    current = organization_agent_policy_out(policy, organization_id)
    if current.version != expected_version:
        raise AgentPolicyVersionConflict
    if all(
        getattr(current, field) == getattr(proposed, field)
        for field in (
            "learner_enabled",
            "instructor_enabled",
            "program_enabled",
            "model_mode",
        )
    ):
        return current
    if policy is None:
        policy = OrganizationAgentPolicy(
            organization_id=organization_id,
            **proposed.model_dump(),
            version=1,
            updated_by_user_id=actor_user_id,
        )
        db.add(policy)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise AgentPolicyVersionConflict from exc
        previous_state = {**AgentPolicySettings().model_dump(), "version": 0}
    else:
        previous_state = _event_state(policy)
        for field, value in proposed.model_dump().items():
            setattr(policy, field, value)
        policy.version += 1
        policy.updated_by_user_id = actor_user_id
        db.flush()
    db.add(
        OrganizationAgentPolicyEvent(
            policy_id=policy.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            previous_state=previous_state,
            new_state=_event_state(policy),
            version=policy.version,
        )
    )
    db.flush()
    return organization_agent_policy_out(policy, organization_id)


def assert_agent_workflow_enabled(
    db: Session,
    *,
    organization_id: int,
    role: str,
    workflow: str | None,
) -> None:
    if workflow is None or workflow in ADMIN_GOVERNANCE_WORKFLOWS:
        return
    policy = get_effective_agent_policy(db, organization_id)
    enabled = True
    if role == "student" and workflow.startswith("learner."):
        enabled = policy.learner_enabled
    elif role == "instructor" and workflow.startswith("instructor."):
        enabled = policy.instructor_enabled
    elif workflow.startswith("program."):
        enabled = policy.program_enabled
    if not enabled:
        raise AgentPolicyScopeDenied


def lock_and_assert_agent_workflow_enabled(
    db: Session,
    *,
    organization_id: int,
    role: str,
    workflow: str | None,
) -> None:
    """Serialize admission/execution with policy changes for one organization."""
    _lock_organization(db, organization_id)
    assert_agent_workflow_enabled(
        db,
        organization_id=organization_id,
        role=role,
        workflow=workflow,
    )


def organization_uses_deterministic_model_mode(
    db: Session, organization_id: int
) -> bool:
    return (
        get_effective_agent_policy(db, organization_id).model_mode
        == "deterministic_only"
    )
