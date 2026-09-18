from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course
from ..schemas.tutor_policy import TutorPolicyOut, TutorPolicyUpdateIn
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_course_route_access,
)
from ..services.tutor_policy import (
    TutorPolicyVersionConflict,
    get_effective_tutor_policy,
    update_tutor_policy,
)

router = APIRouter(
    tags=["tutor-policy"],
    dependencies=[Depends(require_course_route_access)],
)


@router.get("/courses/{course_id}/tutor-policy", response_model=TutorPolicyOut)
def get_tutor_policy(course_id: int, db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "resource not found")
    return get_effective_tutor_policy(db, course_id)


@router.patch("/courses/{course_id}/tutor-policy", response_model=TutorPolicyOut)
def update_tutor_policy_route(
    course_id: int,
    payload: TutorPolicyUpdateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "resource not found")
    try:
        policy = update_tutor_policy(
            db,
            course_id=course_id,
            enabled=payload.enabled,
            answer_style=payload.answer_style,
            expected_version=payload.expected_version,
            actor_user_id=principal.user_id,
        )
    except TutorPolicyVersionConflict as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "tutor_policy_version_conflict",
                "message": "Tutor policy changed. Reload and try again.",
            },
        ) from exc
    db.commit()
    return policy
