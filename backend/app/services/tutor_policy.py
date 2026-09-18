from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.models import CourseTutorPolicy, CourseTutorPolicyEvent
from ..schemas.tutor_policy import TutorAnswerStyle, TutorPolicyOut


class TutorPolicyVersionConflict(Exception):
    pass


def _state(policy: CourseTutorPolicy) -> dict:
    return {
        "enabled": bool(policy.enabled),
        "answer_style": policy.answer_style,
        "version": int(policy.version),
    }


def tutor_policy_out(
    policy: CourseTutorPolicy | None, course_id: int
) -> TutorPolicyOut:
    if policy is None:
        return TutorPolicyOut(course_id=course_id)
    return TutorPolicyOut(
        course_id=course_id,
        enabled=bool(policy.enabled),
        answer_style=policy.answer_style,
        version=int(policy.version),
        updated_at=policy.updated_at,
    )


def get_effective_tutor_policy(db: Session, course_id: int) -> TutorPolicyOut:
    policy = (
        db.query(CourseTutorPolicy)
        .filter(CourseTutorPolicy.course_id == course_id)
        .first()
    )
    return tutor_policy_out(policy, course_id)


def update_tutor_policy(
    db: Session,
    *,
    course_id: int,
    enabled: bool,
    answer_style: TutorAnswerStyle,
    expected_version: int,
    actor_user_id: int | None,
) -> TutorPolicyOut:
    policy = (
        db.query(CourseTutorPolicy)
        .filter(CourseTutorPolicy.course_id == course_id)
        .with_for_update()
        .first()
    )
    if policy is None:
        if expected_version != 0:
            raise TutorPolicyVersionConflict
        policy = CourseTutorPolicy(
            course_id=course_id,
            enabled=enabled,
            answer_style=answer_style,
            version=1,
            updated_by_user_id=actor_user_id,
        )
        db.add(policy)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise TutorPolicyVersionConflict from exc
        previous_state = {
            "enabled": True,
            "answer_style": "balanced",
            "version": 0,
        }
    else:
        if policy.version != expected_version:
            raise TutorPolicyVersionConflict
        previous_state = _state(policy)
        policy.enabled = enabled
        policy.answer_style = answer_style
        policy.version += 1
        policy.updated_by_user_id = actor_user_id
        db.flush()
    db.add(
        CourseTutorPolicyEvent(
            policy_id=policy.id,
            course_id=course_id,
            actor_user_id=actor_user_id,
            previous_state=previous_state,
            new_state=_state(policy),
            version=policy.version,
        )
    )
    db.flush()
    return tutor_policy_out(policy, course_id)
