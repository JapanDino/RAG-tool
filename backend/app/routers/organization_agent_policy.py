from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Organization
from ..schemas.organization_agent_policy import (
    AgentPolicySettings,
    OrganizationAgentPolicyDraftIn,
    OrganizationAgentPolicyOut,
    OrganizationAgentPolicyPreviewOut,
    OrganizationAgentPolicyUpdateIn,
)
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_organization_role,
)
from ..services.organization_agent_policy import (
    AgentPolicyScopeDenied,
    AgentPolicyVersionConflict,
    get_effective_agent_policy,
    preview_agent_policy,
    update_agent_policy,
)

router = APIRouter(tags=["organization-agent-policy"])


def _authorize(db: Session, principal: Principal, organization_id: int) -> None:
    if principal.bypass or principal.user_id is None:
        raise HTTPException(404, "resource not found")
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(404, "resource not found")
    require_organization_role(
        db,
        principal,
        organization_id,
        frozenset({"administrator"}),
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/organizations/{organization_id}/agent-policy",
    response_model=OrganizationAgentPolicyOut,
)
def get_organization_agent_policy(
    organization_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize(db, principal, organization_id)
    _no_store(response)
    return get_effective_agent_policy(db, organization_id)


@router.post(
    "/organizations/{organization_id}/agent-policy/preview",
    response_model=OrganizationAgentPolicyPreviewOut,
)
def preview_organization_agent_policy(
    organization_id: int,
    payload: OrganizationAgentPolicyDraftIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize(db, principal, organization_id)
    current = get_effective_agent_policy(db, organization_id)
    if current.version != payload.expected_version:
        raise HTTPException(
            409,
            {
                "code": "agent_policy_version_conflict",
                "message": "Agent policy changed. Reload and try again.",
            },
        )
    _no_store(response)
    proposed = AgentPolicySettings(**payload.model_dump(exclude={"expected_version"}))
    return preview_agent_policy(
        db,
        organization_id=organization_id,
        proposed=proposed,
    )


@router.patch(
    "/organizations/{organization_id}/agent-policy",
    response_model=OrganizationAgentPolicyOut,
)
def update_organization_agent_policy(
    organization_id: int,
    payload: OrganizationAgentPolicyUpdateIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize(db, principal, organization_id)
    proposed = AgentPolicySettings(
        **payload.model_dump(exclude={"expected_version", "confirmation"})
    )
    try:
        policy = update_agent_policy(
            db,
            organization_id=organization_id,
            proposed=proposed,
            expected_version=payload.expected_version,
            actor_user_id=principal.user_id,
        )
    except AgentPolicyVersionConflict as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "agent_policy_version_conflict",
                "message": "Agent policy changed. Reload and try again.",
            },
        ) from exc
    except AgentPolicyScopeDenied as exc:
        db.rollback()
        raise HTTPException(404, "resource not found") from exc
    db.commit()
    _no_store(response)
    return policy
