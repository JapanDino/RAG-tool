from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    Course,
    CourseMembership,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Organization,
    OrganizationTutorDataPolicy,
    OrganizationTutorDataPolicyEvent,
    TutorDataDeletionEvent,
)
from ..schemas.tutor_data import (
    TutorDataDeletionOut,
    TutorDataPolicyOut,
    TutorRetentionDays,
)

DEFAULT_TUTOR_RETENTION_DAYS: TutorRetentionDays = 90
AGENT_RUN_RETENTION_DAYS = 30
ALLOWED_TUTOR_RETENTION_DAYS = frozenset({30, 90, 180, 365})


class TutorDataPolicyVersionConflict(Exception):
    pass


class TutorDataScopeDenied(Exception):
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
        raise TutorDataScopeDenied
    return organization


def _policy_state(policy: OrganizationTutorDataPolicy) -> dict:
    return {
        "retention_days": int(policy.retention_days),
        "version": int(policy.version),
    }


def tutor_data_policy_out(
    policy: OrganizationTutorDataPolicy | None,
    organization_id: int,
    *,
    course_id: int | None = None,
) -> TutorDataPolicyOut:
    if policy is None:
        return TutorDataPolicyOut(
            organization_id=organization_id,
            course_id=course_id,
        )
    return TutorDataPolicyOut(
        organization_id=organization_id,
        course_id=course_id,
        retention_days=policy.retention_days,
        version=int(policy.version),
        updated_at=policy.updated_at,
    )


def get_effective_tutor_data_policy(
    db: Session,
    organization_id: int,
    *,
    course_id: int | None = None,
) -> TutorDataPolicyOut:
    policy = (
        db.query(OrganizationTutorDataPolicy)
        .filter(OrganizationTutorDataPolicy.organization_id == organization_id)
        .first()
    )
    return tutor_data_policy_out(policy, organization_id, course_id=course_id)


def update_tutor_data_policy(
    db: Session,
    *,
    organization_id: int,
    retention_days: TutorRetentionDays,
    expected_version: int,
    actor_user_id: int | None,
) -> TutorDataPolicyOut:
    if retention_days not in ALLOWED_TUTOR_RETENTION_DAYS:
        raise ValueError("unsupported tutor retention period")
    _lock_organization(db, organization_id)
    policy = (
        db.query(OrganizationTutorDataPolicy)
        .filter(OrganizationTutorDataPolicy.organization_id == organization_id)
        .with_for_update()
        .first()
    )
    if policy is None:
        if expected_version != 0:
            raise TutorDataPolicyVersionConflict
        policy = OrganizationTutorDataPolicy(
            organization_id=organization_id,
            retention_days=retention_days,
            version=1,
            updated_by_user_id=actor_user_id,
        )
        db.add(policy)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise TutorDataPolicyVersionConflict from exc
        previous_state = {
            "retention_days": DEFAULT_TUTOR_RETENTION_DAYS,
            "version": 0,
        }
    else:
        if policy.version != expected_version:
            raise TutorDataPolicyVersionConflict
        previous_state = _policy_state(policy)
        policy.retention_days = retention_days
        policy.version += 1
        policy.updated_by_user_id = actor_user_id
        db.flush()
    db.add(
        OrganizationTutorDataPolicyEvent(
            policy_id=policy.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            previous_state=previous_state,
            new_state=_policy_state(policy),
            version=policy.version,
        )
    )
    db.flush()
    return tutor_data_policy_out(policy, organization_id)


def _delete_answers(
    db: Session,
    answer_ids: list[int],
) -> tuple[int, int]:
    if not answer_ids:
        return 0, 0
    feedback_events_deleted = (
        db.query(CourseQaFeedbackEvent)
        .filter(CourseQaFeedbackEvent.answer_id.in_(answer_ids))
        .delete(synchronize_session=False)
    )
    answers_deleted = (
        db.query(CourseQuestionAnswer)
        .filter(CourseQuestionAnswer.id.in_(answer_ids))
        .delete(synchronize_session=False)
    )
    return int(answers_deleted), int(feedback_events_deleted)


def purge_expired_agent_runs(
    db: Session,
    *,
    now: datetime,
    organization_id: int | None = None,
) -> int:
    cutoff = now - timedelta(days=AGENT_RUN_RETENTION_DAYS)
    query = db.query(AgentRun).filter(AgentRun.created_at < cutoff)
    if organization_id is not None:
        query = query.filter(AgentRun.organization_id == organization_id)
    return int(query.delete(synchronize_session=False))


def _deletion_result(
    *,
    reason: str,
    policy_version: int,
    answers_deleted: int,
    feedback_events_deleted: int,
    agent_runs_deleted: int,
    cutoff: datetime | None,
    agent_run_cutoff: datetime | None,
    deleted_at: datetime,
) -> TutorDataDeletionOut:
    return TutorDataDeletionOut(
        reason=reason,
        policy_version=policy_version,
        answers_deleted=answers_deleted,
        feedback_events_deleted=feedback_events_deleted,
        agent_runs_deleted=agent_runs_deleted,
        cutoff=cutoff,
        agent_run_cutoff=agent_run_cutoff,
        deleted_at=deleted_at,
    )


def delete_owned_tutor_history(
    db: Session,
    *,
    organization_id: int,
    course_id: int,
    user_id: int,
    now: datetime | None = None,
) -> TutorDataDeletionOut:
    deleted_at = now or datetime.now(timezone.utc)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.organization_id == organization_id,
        )
        .first()
    )
    membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.organization_id == organization_id,
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == user_id,
            CourseMembership.role == "student",
            CourseMembership.is_active.is_(True),
        )
        .first()
    )
    if course is None or membership is None:
        raise TutorDataScopeDenied
    policy = get_effective_tutor_data_policy(
        db,
        organization_id,
        course_id=course_id,
    )
    answer_ids = [
        answer_id
        for (answer_id,) in db.query(CourseQuestionAnswer.id)
        .filter(
            CourseQuestionAnswer.course_id == course_id,
            CourseQuestionAnswer.asked_by_user_id == user_id,
        )
        .all()
    ]
    answers_deleted, feedback_events_deleted = _delete_answers(db, answer_ids)
    agent_runs_deleted = int(
        db.query(AgentRun)
        .filter(
            AgentRun.organization_id == organization_id,
            AgentRun.course_id == course_id,
            AgentRun.user_id == user_id,
            AgentRun.role == "student",
        )
        .delete(synchronize_session=False)
    )
    if answers_deleted or feedback_events_deleted or agent_runs_deleted:
        db.add(
            TutorDataDeletionEvent(
                organization_id=organization_id,
                course_id=course_id,
                actor_user_id=user_id,
                subject_user_id=user_id,
                reason="student_request",
                policy_version=policy.version,
                answers_deleted=answers_deleted,
                feedback_events_deleted=feedback_events_deleted,
                agent_runs_deleted=agent_runs_deleted,
            )
        )
        db.flush()
    return _deletion_result(
        reason="student_request",
        policy_version=policy.version,
        answers_deleted=answers_deleted,
        feedback_events_deleted=feedback_events_deleted,
        agent_runs_deleted=agent_runs_deleted,
        cutoff=None,
        agent_run_cutoff=None,
        deleted_at=deleted_at,
    )


def purge_expired_tutor_history(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None = None,
    reason: str = "automatic_retention",
    expected_version: int | None = None,
    now: datetime | None = None,
) -> TutorDataDeletionOut:
    deleted_at = now or datetime.now(timezone.utc)
    _lock_organization(db, organization_id)
    policy_row = (
        db.query(OrganizationTutorDataPolicy)
        .filter(OrganizationTutorDataPolicy.organization_id == organization_id)
        .with_for_update()
        .first()
    )
    policy = tutor_data_policy_out(policy_row, organization_id)
    if expected_version is not None and policy.version != expected_version:
        raise TutorDataPolicyVersionConflict
    cutoff = deleted_at - timedelta(days=policy.retention_days)
    agent_run_cutoff = deleted_at - timedelta(days=AGENT_RUN_RETENTION_DAYS)
    course_ids = [
        course_id
        for (course_id,) in db.query(Course.id)
        .filter(Course.organization_id == organization_id)
        .all()
    ]
    answer_ids = []
    if course_ids:
        answer_ids = [
            answer_id
            for (answer_id,) in db.query(CourseQuestionAnswer.id)
            .filter(
                CourseQuestionAnswer.course_id.in_(course_ids),
                CourseQuestionAnswer.created_at < cutoff,
            )
            .all()
        ]
    answers_deleted, feedback_events_deleted = _delete_answers(db, answer_ids)
    agent_runs_deleted = purge_expired_agent_runs(
        db,
        now=deleted_at,
        organization_id=organization_id,
    )
    if answers_deleted or feedback_events_deleted or agent_runs_deleted:
        db.add(
            TutorDataDeletionEvent(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                reason=reason,
                policy_version=policy.version,
                cutoff=cutoff,
                answers_deleted=answers_deleted,
                feedback_events_deleted=feedback_events_deleted,
                agent_runs_deleted=agent_runs_deleted,
                agent_run_cutoff=agent_run_cutoff,
            )
        )
        db.flush()
    return _deletion_result(
        reason=reason,
        policy_version=policy.version,
        answers_deleted=answers_deleted,
        feedback_events_deleted=feedback_events_deleted,
        agent_runs_deleted=agent_runs_deleted,
        cutoff=cutoff,
        agent_run_cutoff=agent_run_cutoff,
        deleted_at=deleted_at,
    )


def purge_all_expired_tutor_history(
    db: Session,
    *,
    now: datetime | None = None,
) -> list[TutorDataDeletionOut]:
    deleted_at = now or datetime.now(timezone.utc)
    organization_ids = [
        organization_id
        for (organization_id,) in db.query(Organization.id)
        .filter(Organization.is_active.is_(True))
        .order_by(Organization.id)
        .all()
    ]
    results = [
        purge_expired_tutor_history(
            db,
            organization_id=organization_id,
            now=deleted_at,
        )
        for organization_id in organization_ids
    ]
    # Agent metadata has a stricter global cap and must also be removed for a
    # deactivated organization that no longer participates in tutor purges.
    purge_expired_agent_runs(db, now=deleted_at)
    return results
