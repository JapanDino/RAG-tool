from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Literal

from sqlalchemy.orm import Session

from ..models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseInterventionDraft,
    CourseMembership,
    CourseModule,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Document,
)
from .course_retrieval import RetrievalDeadlineExceeded, _bm25_scores

WINDOW_DAYS = 30
MIN_DISTINCT_STUDENTS = 3
MIN_EVENTS = 3
MAX_SIGNALS = 3
MAX_QUALIFYING_ANSWERS = 2000
MAX_CANDIDATE_CHUNKS = 500
MIN_LEXICAL_ANCHOR_SCORE = 0.18

SignalKind = Literal["repeated_unsupported", "low_helpfulness", "mixed"]


@dataclass(frozen=True)
class LearningGapCandidate:
    aggregate_digest: str
    signal_kind: SignalKind
    topic_label: str
    module_title: str | None
    evidence_excerpt: str
    document_id: int
    chunk_id: int
    cohort_size: int
    event_count: int
    cohort_band: str
    event_band: str
    confidence: float
    window_started_at: datetime
    window_ended_at: datetime


@dataclass(frozen=True)
class _EvidenceAnchor:
    document_id: int
    chunk_id: int
    document_title: str
    module_title: str | None
    quote: str
    score: float


@dataclass(frozen=True)
class _GapEvent:
    answer_id: int
    student_id: int
    reasons: frozenset[str]
    anchor: _EvidenceAnchor


def _check_deadline(deadline_monotonic: float | None) -> None:
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        raise RetrievalDeadlineExceeded("learning-gap aggregation deadline exceeded")


def _normalized(value: object, *, limit: int = 900) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _band(value: int) -> str:
    if value <= 5:
        return "3–5"
    if value <= 10:
        return "6–10"
    return "11+"


def _window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current - timedelta(days=WINDOW_DAYS), current


def _latest_owner_feedback(
    db: Session,
    answers: list[CourseQuestionAnswer],
) -> dict[int, str]:
    answer_ids = [item.id for item in answers]
    if not answer_ids:
        return {}
    owners = {item.id: item.asked_by_user_id for item in answers}
    events = (
        db.query(CourseQaFeedbackEvent)
        .filter(CourseQaFeedbackEvent.answer_id.in_(answer_ids))
        .order_by(CourseQaFeedbackEvent.id)
        .all()
    )
    latest: dict[int, str] = {}
    for event in events:
        if (
            event.reviewed_by_user_id is not None
            and event.reviewed_by_user_id == owners.get(event.answer_id)
            and event.to_status in {"helpful", "unhelpful"}
        ):
            latest[event.answer_id] = event.to_status
    return latest


def _course_evidence(
    db: Session,
    course: Course,
) -> list[_EvidenceAnchor]:
    if course.dataset_id is None:
        return []
    rows = (
        db.query(Chunk, Document, CourseModule)
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(CourseModule, CourseModule.id == Document.course_module_id)
        .filter(
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .order_by(Document.id, Chunk.idx, Chunk.id)
        .limit(MAX_CANDIDATE_CHUNKS)
        .all()
    )
    return [
        _EvidenceAnchor(
            document_id=document.id,
            chunk_id=chunk.id,
            document_title=_normalized(document.title, limit=300) or "Материал курса",
            module_title=(
                _normalized(module.title, limit=300) if module is not None else None
            ),
            quote=_normalized(chunk.text),
            score=0.0,
        )
        for chunk, document, module in rows
        if _normalized(chunk.text)
    ]


def _citation_anchor(
    answer: CourseQuestionAnswer,
    evidence_by_chunk: dict[int, _EvidenceAnchor],
) -> _EvidenceAnchor | None:
    for citation in answer.citations or []:
        if not isinstance(citation, dict):
            continue
        chunk_id = citation.get("chunk_id")
        document_id = citation.get("document_id")
        if type(chunk_id) is not int or type(document_id) is not int:
            continue
        anchor = evidence_by_chunk.get(chunk_id)
        if (
            anchor is not None
            and anchor.document_id == document_id
            and _normalized(citation.get("quote")) == anchor.quote
        ):
            return _EvidenceAnchor(**{**anchor.__dict__, "score": 1.0})
    return None


def _lexical_anchor(
    question: str,
    evidence: list[_EvidenceAnchor],
    *,
    deadline_monotonic: float | None,
) -> _EvidenceAnchor | None:
    _check_deadline(deadline_monotonic)
    scores = _bm25_scores(
        question,
        [item.quote for item in evidence],
        deadline_monotonic=deadline_monotonic,
    )
    if not scores:
        return None
    index = max(range(len(scores)), key=lambda position: (scores[position], -position))
    if scores[index] < MIN_LEXICAL_ANCHOR_SCORE:
        return None
    anchor = evidence[index]
    return _EvidenceAnchor(**{**anchor.__dict__, "score": float(scores[index])})


def aggregate_learning_gaps(
    db: Session,
    course: Course,
    *,
    now: datetime | None = None,
    deadline_monotonic: float | None = None,
) -> list[LearningGapCandidate]:
    """Return privacy-thresholded current-course signals without transcript data."""

    _check_deadline(deadline_monotonic)
    window_started_at, window_ended_at = _window(now)
    answers = (
        db.query(CourseQuestionAnswer)
        .join(
            CourseMembership,
            (CourseMembership.course_id == CourseQuestionAnswer.course_id)
            & (CourseMembership.user_id == CourseQuestionAnswer.asked_by_user_id),
        )
        .filter(
            CourseQuestionAnswer.course_id == course.id,
            CourseQuestionAnswer.created_at >= window_started_at,
            CourseQuestionAnswer.created_at < window_ended_at,
            CourseQuestionAnswer.asked_by_user_id.is_not(None),
            CourseMembership.role == "student",
            CourseMembership.is_active.is_(True),
        )
        .order_by(CourseQuestionAnswer.id.desc())
        .limit(MAX_QUALIFYING_ANSWERS)
        .all()
    )
    feedback = _latest_owner_feedback(db, answers)
    evidence = _course_evidence(db, course)
    evidence_by_chunk = {item.chunk_id: item for item in evidence}
    events: list[_GapEvent] = []
    for answer in answers:
        _check_deadline(deadline_monotonic)
        reasons = set()
        if answer.response_mode == "abstained" or answer.insufficient_context:
            reasons.add("unsupported")
        if feedback.get(answer.id) == "unhelpful":
            reasons.add("unhelpful")
        if not reasons or answer.asked_by_user_id is None:
            continue
        anchor = _citation_anchor(answer, evidence_by_chunk) or _lexical_anchor(
            answer.question,
            evidence,
            deadline_monotonic=deadline_monotonic,
        )
        if anchor is None:
            continue
        events.append(
            _GapEvent(
                answer_id=answer.id,
                student_id=answer.asked_by_user_id,
                reasons=frozenset(reasons),
                anchor=anchor,
            )
        )

    grouped: dict[tuple[int, int], list[_GapEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.anchor.document_id, event.anchor.chunk_id)].append(event)
    candidates: list[LearningGapCandidate] = []
    for (document_id, chunk_id), group in grouped.items():
        _check_deadline(deadline_monotonic)
        students = {item.student_id for item in group}
        if len(students) < MIN_DISTINCT_STUDENTS or len(group) < MIN_EVENTS:
            continue
        unsupported = sum("unsupported" in item.reasons for item in group)
        unhelpful = sum("unhelpful" in item.reasons for item in group)
        signal_kind: SignalKind = (
            "mixed"
            if unsupported and unhelpful
            else "repeated_unsupported" if unsupported else "low_helpfulness"
        )
        anchor = sorted(
            (item.anchor for item in group),
            key=lambda item: (-item.score, item.chunk_id),
        )[0]
        digest_input = ":".join(
            [
                str(course.id),
                str(document_id),
                str(chunk_id),
                *[
                    f"{item.answer_id}:{','.join(sorted(item.reasons))}"
                    for item in sorted(group, key=lambda value: value.answer_id)
                ],
            ]
        )
        aggregate_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        candidates.append(
            LearningGapCandidate(
                aggregate_digest=aggregate_digest,
                signal_kind=signal_kind,
                topic_label=anchor.document_title,
                module_title=anchor.module_title,
                evidence_excerpt=anchor.quote,
                document_id=anchor.document_id,
                chunk_id=anchor.chunk_id,
                cohort_size=len(students),
                event_count=len(group),
                cohort_band=_band(len(students)),
                event_band=_band(len(group)),
                # A fixed, cautious value cannot encode exact private counts.
                confidence=0.68,
                window_started_at=window_started_at,
                window_ended_at=window_ended_at,
            )
        )
    return sorted(
        candidates,
        key=lambda item: (-item.cohort_size, -item.event_count, item.topic_label),
    )[:MAX_SIGNALS]


def create_intervention_draft(
    db: Session,
    course: Course,
    candidate: LearningGapCandidate,
) -> CourseInterventionDraft:
    if course.dataset_id is None:
        raise ValueError("course has no current dataset")
    latest_audit = (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course.id, AuditRun.status == "done")
        .order_by(AuditRun.id.desc())
        .first()
    )
    content = (
        f"## Дополнительный разбор: {candidate.topic_label}\n\n"
        f"Ключевая опора из материалов курса:\n\n> {candidate.evidence_excerpt}\n\n"
        "### Как работать с материалом\n"
        "1. Сформулируйте главную мысль фрагмента своими словами.\n"
        "2. Свяжите её с уже изученным примером из этого раздела.\n"
        "3. Запишите один вопрос, который поможет проверить понимание без подсказки ответа.\n\n"
        "### Самопроверка\n"
        "Объясните, когда и почему применяется идея из фрагмента, и укажите, "
        "какую часть объяснения ещё нужно уточнить."
    )
    rationale = (
        "Кандидат появился только после повторяющегося обезличенного сигнала от "
        f"группы {candidate.cohort_band} за текущий 30-дневный период. "
        "Черновик добавляет короткий разбор и самопроверку рядом с текущей опорой курса."
    )
    citation = {
        "document_id": candidate.document_id,
        "chunk_id": candidate.chunk_id,
        "document_title": candidate.topic_label,
        "module_title": candidate.module_title,
        "quote": candidate.evidence_excerpt,
    }
    row = CourseInterventionDraft(
        course_id=course.id,
        source_dataset_id=course.dataset_id,
        source_document_id=candidate.document_id,
        source_chunk_id=candidate.chunk_id,
        source_audit_run_id=latest_audit.id if latest_audit is not None else None,
        aggregate_digest=candidate.aggregate_digest,
        signal_kind=candidate.signal_kind,
        cohort_band=candidate.cohort_band,
        event_band=candidate.event_band,
        window_started_at=candidate.window_started_at,
        window_ended_at=candidate.window_ended_at,
        title=f"Дополнительный разбор: {candidate.topic_label}",
        initial_content=content,
        content=content,
        rationale=rationale,
        citations=[citation],
        confidence=candidate.confidence,
        status="draft",
        version=1,
    )
    db.add(row)
    db.flush()
    return row


def validate_intervention_evidence(
    db: Session,
    course: Course,
    draft: CourseInterventionDraft,
) -> dict | None:
    if course.dataset_id is None or draft.source_dataset_id != course.dataset_id:
        return None
    row = (
        db.query(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .filter(
            Chunk.id == draft.source_chunk_id,
            Document.id == draft.source_document_id,
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .one_or_none()
    )
    if row is None or len(draft.citations or []) != 1:
        return None
    chunk, document = row
    citation = draft.citations[0]
    if not isinstance(citation, dict):
        return None
    if (
        citation.get("chunk_id") != chunk.id
        or citation.get("document_id") != document.id
        or _normalized(citation.get("quote")) != _normalized(chunk.text)
    ):
        return None
    return {
        "document_title": _normalized(document.title, limit=300) or "Материал курса",
        "module_title": citation.get("module_title"),
        "quote": _normalized(chunk.text),
    }


def review_intervention_draft(
    db: Session,
    draft: CourseInterventionDraft,
    *,
    reviewer_user_id: int,
    status: Literal["accepted", "rejected"],
    content: str | None,
    now: datetime | None = None,
) -> CourseInterventionDraft:
    reviewed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    final_content = (
        content if status == "accepted" and content is not None else draft.content
    )
    draft.content = final_content
    draft.status = status
    draft.version += 1
    draft.reviewed_by_user_id = reviewer_user_id
    draft.reviewed_at = reviewed_at
    draft.review_reason = (
        "teacher_accepted" if status == "accepted" else "teacher_rejected"
    )
    draft.edit_distance_ratio = round(
        1.0 - SequenceMatcher(None, draft.initial_content, final_content).ratio(),
        4,
    )
    created_at = draft.created_at
    if created_at is not None:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        draft.decision_latency_seconds = max(
            0,
            int((reviewed_at - created_at.astimezone(timezone.utc)).total_seconds()),
        )
    return draft


__all__ = [
    "LearningGapCandidate",
    "aggregate_learning_gaps",
    "create_intervention_draft",
    "review_intervention_draft",
    "validate_intervention_evidence",
]
