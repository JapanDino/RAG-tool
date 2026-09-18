from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.models import (
    AlignmentEdge,
    AssessmentItem,
    AuditRun,
    CanvasOutcomeAlignment,
    Document,
    LearningObjective,
)


def evaluate_canvas_alignment(db: Session, audit_run_id: int) -> dict:
    run = db.get(AuditRun, audit_run_id)
    if run is None:
        raise LookupError("audit run not found")

    explicit_rows = (
        db.query(CanvasOutcomeAlignment)
        .filter(CanvasOutcomeAlignment.course_id == run.course_id)
        .all()
    )
    if not explicit_rows:
        return {"available": False}

    objectives = (
        db.query(LearningObjective)
        .filter(LearningObjective.audit_run_id == audit_run_id)
        .all()
    )
    assessments = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.audit_run_id == audit_run_id)
        .all()
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
    metadata_by_document = {item.id: item.source_metadata or {} for item in documents}

    objective_external_by_id: dict[int, str] = {}
    objective_text_by_external: dict[str, str] = {}
    for objective in objectives:
        external_id = metadata_by_document.get(objective.document_id, {}).get(
            "canvas_outcome_id"
        )
        if external_id is not None:
            external_id = str(external_id)
            objective_external_by_id[objective.id] = external_id
            objective_text_by_external.setdefault(external_id, objective.text)

    assessment_external_by_id: dict[int, str] = {}
    assessment_title_by_external: dict[str, str] = {}
    for assessment in assessments:
        external_id = metadata_by_document.get(assessment.document_id, {}).get(
            "canvas_assignment_id"
        )
        if external_id is not None:
            external_id = str(external_id)
            assessment_external_by_id[assessment.id] = external_id
            assessment_title_by_external.setdefault(
                external_id, assessment.title or assessment.text
            )

    explicit_pairs = {
        (item.outcome_external_id, item.assignment_external_id)
        for item in explicit_rows
    }
    mappable_explicit = {
        pair
        for pair in explicit_pairs
        if pair[0] in objective_text_by_external
        and pair[1] in assessment_title_by_external
    }
    unmapped_explicit = explicit_pairs - mappable_explicit

    inferred_pairs: set[tuple[str, str]] = set()
    edges = (
        db.query(AlignmentEdge)
        .filter(
            AlignmentEdge.audit_run_id == audit_run_id,
            AlignmentEdge.relation_type == "assesses",
            AlignmentEdge.source_type == "learning_objective",
            AlignmentEdge.target_type == "assessment_item",
        )
        .all()
    )
    for edge in edges:
        outcome_external_id = objective_external_by_id.get(edge.source_id)
        assignment_external_id = assessment_external_by_id.get(edge.target_id)
        if outcome_external_id is not None and assignment_external_id is not None:
            inferred_pairs.add((outcome_external_id, assignment_external_id))

    matched = inferred_pairs & mappable_explicit
    inferred_only = inferred_pairs - mappable_explicit
    missing = mappable_explicit - inferred_pairs
    tp = len(matched)
    fp = len(inferred_only)
    fn = len(missing)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    def serialize(pairs: set[tuple[str, str]]) -> list[dict]:
        return [
            {
                "outcome_external_id": outcome_id,
                "assignment_external_id": assignment_id,
                "outcome_text": objective_text_by_external.get(outcome_id),
                "assignment_title": assessment_title_by_external.get(assignment_id),
            }
            for outcome_id, assignment_id in sorted(pairs)
        ]

    return {
        "available": True,
        "explicit_pairs": len(explicit_pairs),
        "inferred_pairs": len(inferred_pairs),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mapping_coverage": round(len(mappable_explicit) / len(explicit_pairs), 4),
        "matched": serialize(matched),
        "missing_in_inference": serialize(missing),
        "inferred_only": serialize(inferred_only),
        "unmapped_explicit": serialize(unmapped_explicit),
    }
