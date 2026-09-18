from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Document,
)
from ..schemas.copilot import (
    CopilotRequest,
    CopilotSuggestionOut,
    CopilotSuggestionReviewIn,
    CourseAnswerOut,
    CourseAnswerReviewIn,
    CourseQaFeedbackEventOut,
    CourseQuestionIn,
)
from ..services.authorization import (
    REVIEW_ROLES,
    Principal,
    course_roles,
    get_current_principal,
    require_course_route_access,
)
from ..services.course_copilot import (
    create_copilot_suggestion,
    validate_copilot_suggestion_citations,
)
from ..services.course_qa import answer_course_question
from ..services.learner_agent import revalidate_stored_learner_answer
from ..services.tutor_policy import get_effective_tutor_policy

router = APIRouter(
    tags=["copilot"],
    dependencies=[Depends(require_course_route_access)],
)


def _student_only(db: Session, principal: Principal, course: Course) -> bool:
    if principal.bypass:
        return False
    roles = course_roles(db, principal, course)
    return "student" in roles and not roles.intersection(REVIEW_ROLES)


def _answer_out(
    answer: CourseQuestionAnswer,
    *,
    hide_source_urls: bool,
    hide_reviewer: bool,
    db: Session | None = None,
    course: Course | None = None,
) -> CourseAnswerOut:
    if (
        hide_source_urls
        and db is not None
        and course is not None
        and revalidate_stored_learner_answer(db, course, answer) is None
    ):
        raise HTTPException(404, "resource not found")
    result = CourseAnswerOut.model_validate(answer)
    updates = {}
    if hide_source_urls:
        updates["citations"] = [
            citation.model_copy(update={"source_url": None})
            for citation in result.citations
        ]
    if hide_reviewer:
        updates["reviewed_by"] = None
    if not updates:
        return result
    return result.model_copy(update=updates)


@router.post("/courses/{course_id}/qa", response_model=CourseAnswerOut, status_code=201)
def ask_course(
    course_id: int,
    payload: CourseQuestionIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    tutor_policy = get_effective_tutor_policy(db, course.id)
    if not tutor_policy.enabled:
        raise HTTPException(409, "course tutor is paused")
    ready_documents = (
        db.query(Document)
        .filter(Document.dataset_id == course.dataset_id, Document.status == "ready")
        .count()
    )
    if not ready_documents:
        raise HTTPException(409, "course has no ready documents")
    try:
        generated = answer_course_question(
            db,
            course,
            payload.question,
            top_k=payload.top_k,
            language=payload.language,
            module_id=payload.module_id,
            answer_style=tutor_policy.answer_style,
            tutor_policy_version=tutor_policy.version,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    answer = CourseQuestionAnswer(
        course_id=course.id,
        asked_by_user_id=principal.user_id,
        question=generated.question,
        answer=generated.answer,
        citations=[item.model_dump() for item in generated.citations],
        confidence=generated.confidence,
        retrieval_method=generated.retrieval_method,
        generation_provider=generated.generation_provider,
        generation_model=generated.generation_model,
        insufficient_context=generated.insufficient_context,
        response_mode=generated.response_mode,
        policy_reason=generated.policy_reason,
        tutor_policy_version=generated.tutor_policy_version,
        tutor_answer_style=generated.tutor_answer_style,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return _answer_out(
        answer,
        hide_source_urls=_student_only(db, principal, course),
        hide_reviewer=not principal.bypass,
        db=db,
        course=course,
    )


@router.get("/courses/{course_id}/qa", response_model=list[CourseAnswerOut])
def course_qa_history(
    course_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    query = db.query(CourseQuestionAnswer).filter(
        CourseQuestionAnswer.course_id == course_id
    )
    if not principal.bypass:
        roles = course_roles(db, principal, course)
        if "student" in roles and not roles.intersection(REVIEW_ROLES):
            query = query.filter(
                CourseQuestionAnswer.asked_by_user_id == principal.user_id
            )
        elif not roles.intersection(REVIEW_ROLES):
            raise HTTPException(404, "resource not found")
    rows = query.order_by(CourseQuestionAnswer.id.desc()).limit(50).all()
    hide_source_urls = _student_only(db, principal, course)
    visible = []
    for answer in rows:
        try:
            visible.append(
                _answer_out(
                    answer,
                    hide_source_urls=hide_source_urls,
                    hide_reviewer=not principal.bypass,
                    db=db,
                    course=course,
                )
            )
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return visible


@router.patch("/qa/answers/{answer_id}", response_model=CourseAnswerOut)
def review_course_answer(
    answer_id: int,
    payload: CourseAnswerReviewIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    answer = db.get(CourseQuestionAnswer, answer_id)
    if answer is None:
        raise HTTPException(404, "course answer not found")
    course = db.get(Course, answer.course_id)
    if not principal.bypass:
        roles = course_roles(db, principal, course)
        owns_answer = answer.asked_by_user_id == principal.user_id
        if not owns_answer and not roles.intersection(REVIEW_ROLES):
            raise HTTPException(404, "resource not found")
    reviewed_by = principal.email if not principal.bypass else payload.reviewed_by
    if not reviewed_by:
        raise HTTPException(422, "reviewed_by is required in compatibility mode")
    previous_status = answer.feedback_status
    answer.feedback_status = payload.status
    answer.feedback_comment = payload.comment
    answer.reviewed_by = reviewed_by
    answer.reviewed_at = datetime.now(timezone.utc)
    db.add(
        CourseQaFeedbackEvent(
            answer_id=answer.id,
            course_id=answer.course_id,
            reviewed_by_user_id=(None if principal.bypass else principal.user_id),
            from_status=previous_status,
            to_status=payload.status,
            reviewed_by=reviewed_by,
            comment=payload.comment,
        )
    )
    db.commit()
    db.refresh(answer)
    return _answer_out(
        answer,
        hide_source_urls=_student_only(db, principal, course),
        hide_reviewer=not principal.bypass,
        db=db,
        course=course,
    )


@router.get(
    "/qa/answers/{answer_id}/history", response_model=list[CourseQaFeedbackEventOut]
)
def course_answer_feedback_history(
    answer_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    answer = db.get(CourseQuestionAnswer, answer_id)
    if answer is None:
        raise HTTPException(404, "course answer not found")
    if not principal.bypass:
        course = db.get(Course, answer.course_id)
        roles = course_roles(db, principal, course)
        owns_answer = answer.asked_by_user_id == principal.user_id
        if not owns_answer and not roles.intersection(REVIEW_ROLES):
            raise HTTPException(404, "resource not found")
    rows = (
        db.query(CourseQaFeedbackEvent)
        .filter(CourseQaFeedbackEvent.answer_id == answer_id)
        .order_by(CourseQaFeedbackEvent.id)
        .all()
    )
    if principal.bypass:
        return rows
    return [
        CourseQaFeedbackEventOut.model_validate(row).model_copy(
            update={"reviewed_by": None}
        )
        for row in rows
    ]


@router.post(
    "/findings/{finding_id}/copilot",
    response_model=CopilotSuggestionOut,
    status_code=201,
)
def suggest_remediation(
    finding_id: int,
    payload: CopilotRequest,
    db: Session = Depends(get_db),
):
    finding = db.get(CourseFinding, finding_id)
    if finding is None:
        raise HTTPException(404, "finding not found")
    try:
        suggestion = create_copilot_suggestion(
            db,
            finding,
            top_k=payload.top_k,
            language=payload.language,
        )
    except ValueError as exc:
        status = 409 if "must be" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    db.commit()
    db.refresh(suggestion)
    return CopilotSuggestionOut.model_validate(suggestion)


@router.get("/findings/{finding_id}/copilot", response_model=list[CopilotSuggestionOut])
def list_suggestions(finding_id: int, db: Session = Depends(get_db)):
    if db.get(CourseFinding, finding_id) is None:
        raise HTTPException(404, "finding not found")
    return (
        db.query(CourseCopilotSuggestion)
        .filter(CourseCopilotSuggestion.finding_id == finding_id)
        .order_by(CourseCopilotSuggestion.id.desc())
        .all()
    )


@router.patch(
    "/copilot/suggestions/{suggestion_id}", response_model=CopilotSuggestionOut
)
def review_suggestion(
    suggestion_id: int,
    payload: CopilotSuggestionReviewIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    suggestion = (
        db.query(CourseCopilotSuggestion)
        .filter(CourseCopilotSuggestion.id == suggestion_id)
        .with_for_update()
        .one_or_none()
    )
    if suggestion is None:
        raise HTTPException(404, "Copilot suggestion not found")
    if payload.status == "accepted" and suggestion.insufficient_context:
        raise HTTPException(
            409, "a suggestion without grounded context cannot be accepted"
        )
    course = db.get(Course, suggestion.course_id)
    if payload.status == "accepted" and (
        course is None
        or validate_copilot_suggestion_citations(db, course, suggestion) is None
    ):
        raise HTTPException(409, "suggestion citations are stale")
    reviewed_by = principal.email if not principal.bypass else payload.reviewed_by
    if not reviewed_by:
        raise HTTPException(422, "reviewed_by is required in compatibility mode")
    reviewed_at = datetime.now(timezone.utc)
    if payload.status == "accepted":
        previous = (
            db.query(CourseCopilotSuggestion)
            .filter(
                CourseCopilotSuggestion.finding_id == suggestion.finding_id,
                CourseCopilotSuggestion.id != suggestion.id,
                CourseCopilotSuggestion.status == "accepted",
            )
            .all()
        )
        for item in previous:
            item.status = "rejected"
            item.version += 1
            item.review_reason = "superseded"
            item.reviewed_by = reviewed_by
            item.reviewed_at = reviewed_at
    if payload.status == "accepted" and payload.draft is not None:
        suggestion.draft = payload.draft
    suggestion.status = payload.status
    suggestion.version += 1
    suggestion.review_reason = (
        "teacher_accepted" if payload.status == "accepted" else "teacher_rejected"
    )
    suggestion.reviewed_by = reviewed_by
    suggestion.reviewed_at = reviewed_at
    db.commit()
    db.refresh(suggestion)
    return suggestion
