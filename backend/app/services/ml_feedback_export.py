from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.models import (
    AlignmentCandidate,
    AssessmentItem,
    CanvasOutcomeAlignment,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseQuestionAnswer,
    Document,
    LearningObjective,
)
from ..schemas.ml_feedback import MlFeedbackSummaryOut


def build_ml_feedback_rows(
    db: Session,
    course: Course,
    *,
    include_review_metadata: bool = False,
) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    warnings: list[str] = []

    for item in (
        db.query(CourseQuestionAnswer)
        .filter(
            CourseQuestionAnswer.course_id == course.id,
            CourseQuestionAnswer.feedback_status != "unreviewed",
        )
        .order_by(CourseQuestionAnswer.id)
    ):
        rows.append(
            {
                "schema_version": "ml-feedback-v1",
                "example_type": "course_qa",
                "course_id": course.id,
                "example_id": item.id,
                "input": {"question": item.question, "citations": item.citations},
                "prediction": {
                    "answer": item.answer,
                    "confidence": item.confidence,
                    "provider": item.generation_provider,
                    "model": item.generation_model,
                    "retrieval_method": item.retrieval_method,
                    "insufficient_context": item.insufficient_context,
                },
                "label": item.feedback_status,
                "label_source": "teacher_review",
                "review": (
                    {"reviewed_by": item.reviewed_by, "comment": item.feedback_comment}
                    if include_review_metadata
                    else {}
                ),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    for item in (
        db.query(CourseFinding)
        .filter(CourseFinding.course_id == course.id, CourseFinding.status != "new")
        .order_by(CourseFinding.id)
    ):
        rows.append(
            {
                "schema_version": "ml-feedback-v1",
                "example_type": "course_finding",
                "course_id": course.id,
                "audit_run_id": item.audit_run_id,
                "example_id": item.id,
                "input": {
                    "finding_type": item.finding_type,
                    "title": item.title,
                    "description": item.description,
                    "evidence": item.evidence,
                },
                "prediction": {
                    "confidence": item.confidence,
                    "model_info": item.model_info,
                },
                "label": item.status,
                "accepted": item.status in {"confirmed", "resolved"},
                "label_source": "teacher_review",
                "review": (
                    {"reviewed_by": item.reviewed_by} if include_review_metadata else {}
                ),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    for item in (
        db.query(CourseCopilotSuggestion)
        .filter(
            CourseCopilotSuggestion.course_id == course.id,
            (
                (CourseCopilotSuggestion.status == "accepted")
                | (CourseCopilotSuggestion.review_reason == "teacher_rejected")
            ),
        )
        .order_by(CourseCopilotSuggestion.id)
    ):
        rows.append(
            {
                "schema_version": "ml-feedback-v1",
                "example_type": "copilot_remediation",
                "course_id": course.id,
                "audit_run_id": item.audit_run_id,
                "example_id": item.id,
                "input": {
                    "finding_id": item.finding_id,
                    "action_type": item.action_type,
                    "citations": item.citations,
                },
                "prediction": {
                    "title": item.title,
                    "draft": item.draft,
                    "rationale": item.rationale,
                    "target_bloom_level": item.target_bloom_level,
                    "confidence": item.confidence,
                    "provider": item.generation_provider,
                    "model": item.generation_model,
                    "retrieval_method": item.retrieval_method,
                },
                "label": item.status,
                "accepted": item.status == "accepted",
                "label_source": "teacher_review",
                "review_reason": item.review_reason,
                "review": (
                    {"reviewed_by": item.reviewed_by} if include_review_metadata else {}
                ),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    explicit_pairs = {
        (item.outcome_external_id, item.assignment_external_id)
        for item in db.query(CanvasOutcomeAlignment).filter(
            CanvasOutcomeAlignment.course_id == course.id
        )
    }
    if explicit_pairs:
        candidates = (
            db.query(AlignmentCandidate)
            .filter(
                AlignmentCandidate.course_id == course.id,
                AlignmentCandidate.relation_type == "assesses",
            )
            .order_by(AlignmentCandidate.id)
            .all()
        )
        objective_ids = {item.source_id for item in candidates}
        assessment_ids = {item.target_id for item in candidates}
        objectives = (
            db.query(LearningObjective)
            .filter(LearningObjective.id.in_(objective_ids))
            .all()
            if objective_ids
            else []
        )
        assessments = (
            db.query(AssessmentItem).filter(AssessmentItem.id.in_(assessment_ids)).all()
            if assessment_ids
            else []
        )
        document_ids = {
            item.document_id
            for item in [*objectives, *assessments]
            if item.document_id is not None
        }
        documents = (
            db.query(Document).filter(Document.id.in_(document_ids)).all()
            if document_ids
            else []
        )
        metadata_by_document = {
            item.id: item.source_metadata or {} for item in documents
        }
        objective_by_id = {
            item.id: item for item in objectives if item.course_id == course.id
        }
        assessment_by_id = {
            item.id: item for item in assessments if item.course_id == course.id
        }
        objective_external = {
            item.id: str(
                metadata_by_document.get(item.document_id, {}).get("canvas_outcome_id")
            )
            for item in objectives
            if metadata_by_document.get(item.document_id, {}).get("canvas_outcome_id")
            is not None
        }
        assessment_external = {
            item.id: str(
                metadata_by_document.get(item.document_id, {}).get(
                    "canvas_assignment_id"
                )
            )
            for item in assessments
            if metadata_by_document.get(item.document_id, {}).get(
                "canvas_assignment_id"
            )
            is not None
        }
        mapped = 0
        for item in candidates:
            outcome_id = objective_external.get(item.source_id)
            assignment_id = assessment_external.get(item.target_id)
            objective = objective_by_id.get(item.source_id)
            assessment = assessment_by_id.get(item.target_id)
            if (
                outcome_id is None
                or assignment_id is None
                or objective is None
                or assessment is None
            ):
                continue
            mapped += 1
            aligned = (outcome_id, assignment_id) in explicit_pairs
            rows.append(
                {
                    "schema_version": "ml-feedback-v1",
                    "example_type": "canvas_alignment",
                    "course_id": course.id,
                    "audit_run_id": item.audit_run_id,
                    "example_id": item.id,
                    "input": {
                        "objective": objective.text,
                        "assessment": assessment.text,
                        "canvas_outcome_id": outcome_id,
                        "canvas_assignment_id": assignment_id,
                    },
                    "prediction": {
                        "score": item.score,
                        "selected": item.selected,
                        "method": item.method,
                        "model_info": item.model_info,
                    },
                    "label": "aligned" if aligned else "not_aligned",
                    "accepted": aligned,
                    "label_source": "canvas_outcome_alignments",
                    "weak_negative": not aligned,
                    "created_at": (
                        item.created_at.isoformat() if item.created_at else None
                    ),
                }
            )
        if candidates and not mapped:
            warnings.append(
                "Canvas alignment candidates exist but could not be mapped to Canvas document IDs"
            )
        if any(
            row.get("example_type") == "canvas_alignment" and row.get("weak_negative")
            for row in rows
        ):
            warnings.append(
                "Canvas non-alignments are weak negatives because teacher-authored alignments may be incomplete"
            )

    return rows, warnings


def ml_feedback_summary(
    course: Course, rows: list[dict], warnings: list[str]
) -> MlFeedbackSummaryOut:
    by_type = Counter(str(item["example_type"]) for item in rows)

    def positive(item: dict) -> bool:
        if item["example_type"] == "course_qa":
            return item["label"] == "helpful"
        return bool(item.get("accepted"))

    positives = sum(positive(item) for item in rows)
    return MlFeedbackSummaryOut(
        course_id=course.id,
        generated_at=datetime.now(timezone.utc),
        total_examples=len(rows),
        positive_examples=positives,
        negative_examples=len(rows) - positives,
        by_type=dict(sorted(by_type.items())),
        warnings=warnings,
    )
