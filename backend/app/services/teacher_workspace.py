import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseFinding,
    CourseMembership,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Document,
)
from ..schemas.teacher_workspace import (
    AttentionFindingOut,
    EvidenceExcerptOut,
    TeacherAuditOut,
    TeacherCourseOut,
    TeacherHealthOut,
    TeacherWorkspaceOut,
    TutorQualityOut,
)
from .tutor_policy import get_effective_tutor_policy

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
STATUS_ORDER = {"new": 0, "confirmed": 1, "rejected": 2, "ignored": 3, "resolved": 4}
TUTOR_QUALITY_PERIOD_DAYS = 30
MINIMUM_FEEDBACK_SAMPLE = 3


def _confidence_meta(confidence: float) -> tuple[str, str]:
    if confidence >= 0.75:
        return "strong", "Доказательства достаточно устойчивы"
    if confidence >= 0.5:
        return "review", "Есть основания, нужна проверка"
    return "weak", "Недостаточно уверенности"


def _attention_label(finding: CourseFinding) -> str:
    if finding.status != "new":
        return "Решение записано"
    if finding.severity == "high":
        return "Сначала"
    if finding.severity == "medium":
        return "Проверить"
    return "Наблюдать"


def _thread_focus(finding_type: str) -> str:
    if finding_type == "objective_without_material":
        return "objective_material"
    if finding_type in {"objective_without_assessment", "bloom_mismatch"}:
        return "objective_assessment"
    return "whole_course"


def _evidence_excerpt(item: object) -> EvidenceExcerptOut | None:
    if not isinstance(item, dict):
        return None
    quote = str(item.get("quote") or "").strip()
    if not quote:
        return None
    return EvidenceExcerptOut(
        object_type=str(item.get("object_type") or "course_source")[:100],
        object_id=(
            item.get("object_id") if isinstance(item.get("object_id"), int) else None
        ),
        document_id=(
            item.get("document_id")
            if isinstance(item.get("document_id"), int)
            else None
        ),
        quote=quote[:800],
        source_start=(
            item.get("start") if isinstance(item.get("start"), int) else None
        ),
        source_end=item.get("end") if isinstance(item.get("end"), int) else None,
    )


def _finding_out(finding: CourseFinding) -> AttentionFindingOut:
    confidence_band, confidence_label = _confidence_meta(float(finding.confidence))
    evidence = [
        excerpt
        for excerpt in (
            _evidence_excerpt(item) for item in (finding.evidence or [])[:5]
        )
        if excerpt is not None
    ]
    return AttentionFindingOut(
        id=finding.id,
        finding_type=finding.finding_type,
        severity=finding.severity,
        status=finding.status,
        title=finding.title,
        description=finding.description,
        recommendation=finding.recommendation,
        confidence=float(finding.confidence),
        confidence_band=confidence_band,
        confidence_label=confidence_label,
        attention_label=_attention_label(finding),
        thread_focus=_thread_focus(finding.finding_type),
        evidence=evidence,
        uncertainty_reasons=[
            str(item)[:500] for item in finding.uncertainty_reasons or []
        ],
        reviewed_by=finding.reviewed_by,
        reviewed_at=finding.reviewed_at,
    )


def tutor_quality_signal(
    *,
    questions_total: int,
    answer_responses: int,
    abstained_answers: int,
    answers_needing_review: int,
) -> str:
    if questions_total == 0:
        return "empty"
    if questions_total < 5:
        return "early"
    abstained_rate = abstained_answers / questions_total
    review_rate = answers_needing_review / answer_responses if answer_responses else 0.0
    if abstained_rate >= 0.35 and (
        answers_needing_review == 0 or abstained_rate >= review_rate
    ):
        return "coverage"
    if answers_needing_review > 0:
        return "review"
    if answer_responses < 3:
        return "limited"
    return "steady"


def _normalized_excerpt(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _answers_with_valid_citations(
    db: Session,
    course: Course,
    answers: list[CourseQuestionAnswer],
) -> set[int]:
    chunk_ids = {
        item.get("chunk_id")
        for answer in answers
        for item in (answer.citations or [])
        if isinstance(item, dict) and type(item.get("chunk_id")) is int
    }
    if not chunk_ids:
        return set()
    rows = (
        db.query(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .filter(
            Chunk.id.in_(chunk_ids),
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .all()
    )
    expected_quotes = {
        (chunk.id, document.id): _normalized_excerpt(chunk.text)[:900]
        for chunk, document in rows
    }
    valid_answer_ids = set()
    for answer in answers:
        for citation in answer.citations or []:
            if not isinstance(citation, dict):
                continue
            chunk_id = citation.get("chunk_id")
            document_id = citation.get("document_id")
            source_id = citation.get("source_id")
            quote = _normalized_excerpt(citation.get("quote"))
            if (
                type(chunk_id) is int
                and type(document_id) is int
                and isinstance(source_id, str)
                and source_id.strip()
                and quote
                and expected_quotes.get((chunk_id, document_id)) == quote
            ):
                valid_answer_ids.add(answer.id)
                break
    return valid_answer_ids


def _student_feedback(
    db: Session,
    questions: list[CourseQuestionAnswer],
) -> list[tuple[CourseQuestionAnswer, CourseQaFeedbackEvent]]:
    answer_ids = [item.id for item in questions]
    if not answer_ids:
        return []
    events = (
        db.query(CourseQaFeedbackEvent)
        .filter(CourseQaFeedbackEvent.answer_id.in_(answer_ids))
        .order_by(CourseQaFeedbackEvent.id)
        .all()
    )
    owner_by_answer = {item.id: item.asked_by_user_id for item in questions}
    latest_by_answer = {
        event.answer_id: event
        for event in events
        if event.reviewed_by_user_id == owner_by_answer.get(event.answer_id)
    }
    return [
        (item, event)
        for item in questions
        if (event := latest_by_answer.get(item.id)) is not None
        and event.to_status in {"helpful", "unhelpful"}
    ]


def _tutor_quality(db: Session, course: Course) -> TutorQualityOut:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TUTOR_QUALITY_PERIOD_DAYS)
    questions = (
        db.query(CourseQuestionAnswer)
        .join(
            CourseMembership,
            (CourseMembership.course_id == CourseQuestionAnswer.course_id)
            & (CourseMembership.user_id == CourseQuestionAnswer.asked_by_user_id),
        )
        .filter(
            CourseQuestionAnswer.course_id == course.id,
            CourseQuestionAnswer.created_at >= cutoff,
            CourseMembership.role == "student",
            CourseMembership.is_active.is_(True),
        )
        .all()
    )
    abstained = [
        item
        for item in questions
        if item.response_mode == "abstained" or item.insufficient_context
    ]
    guidance = [
        item
        for item in questions
        if item.response_mode == "guidance" and item not in abstained
    ]
    answers = [
        item for item in questions if item not in abstained and item not in guidance
    ]
    supported_answer_ids = _answers_with_valid_citations(db, course, answers)
    supported = [item for item in answers if item.id in supported_answer_ids]
    needs_review = [
        item
        for item in answers
        if item.id not in supported_answer_ids or float(item.confidence) < 0.5
    ]
    rated = _student_feedback(db, questions)
    helpful = [item for item, event in rated if event.to_status == "helpful"]
    helpful_rate = None
    helpful_answers = None
    if len(rated) >= MINIMUM_FEEDBACK_SAMPLE:
        helpful_rate = round(len(helpful) / len(rated), 4)
        helpful_answers = len(helpful)
    return TutorQualityOut(
        signal=tutor_quality_signal(
            questions_total=len(questions),
            answer_responses=len(answers),
            abstained_answers=len(abstained),
            answers_needing_review=len(needs_review),
        ),
        questions_total=len(questions),
        answer_responses=len(answers),
        supported_answers=len(supported),
        guidance_answers=len(guidance),
        abstained_answers=len(abstained),
        answers_needing_review=len(needs_review),
        rated_answers=len(rated),
        helpful_answers=helpful_answers,
        helpful_rate=helpful_rate,
    )


def build_teacher_workspace(db: Session, course: Course) -> TeacherWorkspaceOut:
    latest = (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course.id)
        .order_by(AuditRun.id.desc())
        .first()
    )
    summary = (latest.metrics or {}).get("summary", {}) if latest else {}
    findings = []
    if latest is not None:
        findings = (
            db.query(CourseFinding)
            .filter(CourseFinding.audit_run_id == latest.id)
            .all()
        )
        findings.sort(
            key=lambda item: (
                STATUS_ORDER.get(item.status, 99),
                SEVERITY_ORDER.get(item.severity, 99),
                -float(item.confidence),
                item.id,
            )
        )
    audit = None
    if latest is not None:
        audit = TeacherAuditOut(
            id=latest.id,
            status=latest.status,
            progress=int((latest.metrics or {}).get("progress", 0)),
            created_at=latest.created_at,
            finished_at=latest.finished_at,
            failure_message=(
                "Аудит не завершён. Исходные данные курса сохранены."
                if latest.status == "failed"
                else None
            ),
        )
    return TeacherWorkspaceOut(
        course=TeacherCourseOut(
            id=course.id,
            title=course.title,
            description=course.description,
            source_type=course.source_type,
        ),
        latest_audit=audit,
        health=TeacherHealthOut(
            objectives_total=int(summary.get("objectives_total", 0)),
            materials_total=int(summary.get("materials_total", 0)),
            assessments_total=int(summary.get("assessments_total", 0)),
            objective_material_coverage=float(
                summary.get("objective_material_coverage", 0.0)
            ),
            objective_assessment_coverage=float(
                summary.get("objective_assessment_coverage", 0.0)
            ),
            findings_total=len(findings),
            high_severity_findings=sum(
                item.severity == "high" and item.status in {"new", "confirmed"}
                for item in findings
            ),
            findings_reviewed=sum(item.status != "new" for item in findings),
        ),
        tutor_quality=_tutor_quality(db, course),
        tutor_policy=get_effective_tutor_policy(db, course.id),
        findings=[_finding_out(item) for item in findings],
    )
