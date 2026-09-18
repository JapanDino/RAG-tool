from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course, Organization
from ..schemas.tutor_data import (
    TutorDataDeletionOut,
    TutorDataPolicyOut,
    TutorDataPolicyUpdateIn,
    TutorExpiredDataPurgeIn,
    TutorHistoryDeleteIn,
)
from ..services.authorization import (
    REVIEW_ROLES,
    Principal,
    course_roles,
    get_current_principal,
    require_course_route_access,
    require_organization_role,
)
from ..services.tutor_data import (
    TutorDataPolicyVersionConflict,
    TutorDataScopeDenied,
    delete_owned_tutor_history,
    get_effective_tutor_data_policy,
    purge_expired_tutor_history,
    update_tutor_data_policy,
)

course_router = APIRouter(
    tags=["tutor-data"],
    dependencies=[Depends(require_course_route_access)],
)
organization_router = APIRouter(tags=["tutor-data"])


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "resource not found")
    return course


@course_router.get(
    "/courses/{course_id}/tutor-data-policy",
    response_model=TutorDataPolicyOut,
)
def get_course_tutor_data_policy(
    course_id: int,
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    if course.organization_id is None:
        raise HTTPException(409, "course organization is unavailable")
    return get_effective_tutor_data_policy(
        db,
        course.organization_id,
        course_id=course.id,
    )


@course_router.delete(
    "/courses/{course_id}/qa/history",
    response_model=TutorDataDeletionOut,
)
def delete_own_tutor_history(
    course_id: int,
    payload: TutorHistoryDeleteIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    course = _course_or_404(db, course_id)
    roles = course_roles(db, principal, course)
    is_student_owner_context = (
        principal.user_id is not None
        and "student" in roles
        and not roles.intersection(REVIEW_ROLES)
    )
    if not is_student_owner_context or course.organization_id is None:
        raise HTTPException(404, "resource not found")
    try:
        result = delete_owned_tutor_history(
            db,
            organization_id=course.organization_id,
            course_id=course.id,
            user_id=principal.user_id,
        )
    except TutorDataScopeDenied as exc:
        db.rollback()
        raise HTTPException(404, "resource not found") from exc
    db.commit()
    return result


def _organization_or_404(db: Session, organization_id: int) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(404, "resource not found")
    return organization


@organization_router.get(
    "/organizations/{organization_id}/tutor-data-policy",
    response_model=TutorDataPolicyOut,
)
def get_organization_tutor_data_policy(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _organization_or_404(db, organization_id)
    require_organization_role(
        db,
        principal,
        organization_id,
        frozenset({"administrator"}),
    )
    return get_effective_tutor_data_policy(db, organization_id)


@organization_router.patch(
    "/organizations/{organization_id}/tutor-data-policy",
    response_model=TutorDataPolicyOut,
)
def update_organization_tutor_data_policy(
    organization_id: int,
    payload: TutorDataPolicyUpdateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _organization_or_404(db, organization_id)
    require_organization_role(
        db,
        principal,
        organization_id,
        frozenset({"administrator"}),
    )
    try:
        policy = update_tutor_data_policy(
            db,
            organization_id=organization_id,
            retention_days=payload.retention_days,
            expected_version=payload.expected_version,
            actor_user_id=principal.user_id,
        )
    except TutorDataPolicyVersionConflict as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "tutor_data_policy_version_conflict",
                "message": "Tutor data policy changed. Reload and try again.",
            },
        ) from exc
    db.commit()
    return policy


@organization_router.post(
    "/organizations/{organization_id}/tutor-data-policy/purge",
    response_model=TutorDataDeletionOut,
)
def purge_organization_tutor_data(
    organization_id: int,
    payload: TutorExpiredDataPurgeIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _organization_or_404(db, organization_id)
    require_organization_role(
        db,
        principal,
        organization_id,
        frozenset({"administrator"}),
    )
    try:
        result = purge_expired_tutor_history(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
            reason="admin_purge",
            expected_version=payload.expected_version,
        )
    except TutorDataPolicyVersionConflict as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "tutor_data_policy_version_conflict",
                "message": "Tutor data policy changed. Reload and try again.",
            },
        ) from exc
    db.commit()
    return result
