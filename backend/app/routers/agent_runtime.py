from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..schemas.model_gateway import AgentModelReadinessOut
from ..schemas.model_preflight import ModelCompatibilityProfileId, ModelHostPreflightOut
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_organization_role,
)
from ..services.model_gateway import model_runtime_readiness
from ..services.model_preflight import (
    build_model_host_preflight,
    serialize_model_host_preflight,
)
from ..services.organization_agent_policy import get_effective_agent_policy

router = APIRouter(prefix="/organizations", tags=["agent-runtime"])
_PREFLIGHT_PROFILES = frozenset({"deepseek_openai_v1", "gemma_openai_v1"})


def _authorize_admin(db: Session, principal: Principal, organization_id: int) -> None:
    if principal.bypass or principal.user_id is None:
        raise HTTPException(status_code=404, detail="resource not found")
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )


def _no_store(response: Response) -> None:
    response.headers.update(
        {
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
    )


def _validate_preflight_profile(profile: str) -> ModelCompatibilityProfileId:
    if profile not in _PREFLIGHT_PROFILES:
        raise HTTPException(status_code=422, detail="unsupported profile")
    return cast(ModelCompatibilityProfileId, profile)


def _preflight(
    db: Session,
    *,
    organization_id: int,
    profile: ModelCompatibilityProfileId,
) -> ModelHostPreflightOut:
    policy = get_effective_agent_policy(db, organization_id)
    return build_model_host_preflight(
        profile_id=profile,
        organization_model_route=(
            "deterministic_only"
            if policy.model_mode == "deterministic_only"
            else "allowed"
        ),
    )


@router.get(
    "/{organization_id}/agent-model/readiness",
    response_model=AgentModelReadinessOut,
)
def organization_agent_model_readiness(
    organization_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize_admin(db, principal, organization_id)
    _no_store(response)
    return model_runtime_readiness(db, organization_id=organization_id)


@router.get(
    "/{organization_id}/agent-model/preflight",
    response_model=ModelHostPreflightOut,
)
def organization_agent_model_preflight(
    organization_id: int,
    response: Response,
    profile: str = "deepseek_openai_v1",
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize_admin(db, principal, organization_id)
    profile_id = _validate_preflight_profile(profile)
    _no_store(response)
    return _preflight(
        db,
        organization_id=organization_id,
        profile=profile_id,
    )


@router.get("/{organization_id}/agent-model/preflight/export")
def export_organization_agent_model_preflight(
    organization_id: int,
    profile: str = "deepseek_openai_v1",
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _authorize_admin(db, principal, organization_id)
    profile_id = _validate_preflight_profile(profile)
    report = _preflight(
        db,
        organization_id=organization_id,
        profile=profile_id,
    )
    family = "deepseek" if profile_id == "deepseek_openai_v1" else "gemma"
    return Response(
        content=serialize_model_host_preflight(report),
        media_type="application/json",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                f'attachment; filename="agent-model-preflight-{family}.json"'
            ),
        },
    )
