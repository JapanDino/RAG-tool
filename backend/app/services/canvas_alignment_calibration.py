from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..models.models import (
    AlignmentCandidate,
    AssessmentItem,
    AuditRun,
    CanvasOutcomeAlignment,
    Document,
    LearningObjective,
)


def calibrate_canvas_alignment(db: Session, audit_run_id: int) -> dict:
    run = db.get(AuditRun, audit_run_id)
    if run is None:
        raise LookupError("audit run not found")

    explicit_rows = (
        db.query(CanvasOutcomeAlignment)
        .filter(CanvasOutcomeAlignment.course_id == run.course_id)
        .all()
    )
    if not explicit_rows:
        return {
            "available": False,
            "reason": "Canvas outcome alignments are not imported",
        }

    candidates = (
        db.query(AlignmentCandidate)
        .filter(
            AlignmentCandidate.audit_run_id == audit_run_id,
            AlignmentCandidate.relation_type == "assesses",
        )
        .all()
    )
    if not candidates:
        return {
            "available": False,
            "reason": "This audit has no candidate scores; run a new audit after enabling calibration",
        }

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

    objective_external_by_id = {
        item.id: str(metadata_by_document[item.document_id]["canvas_outcome_id"])
        for item in objectives
        if item.document_id in metadata_by_document
        and metadata_by_document[item.document_id].get("canvas_outcome_id") is not None
    }
    assessment_external_by_id = {
        item.id: str(metadata_by_document[item.document_id]["canvas_assignment_id"])
        for item in assessments
        if item.document_id in metadata_by_document
        and metadata_by_document[item.document_id].get("canvas_assignment_id")
        is not None
    }

    explicit_pairs = {
        (item.outcome_external_id, item.assignment_external_id)
        for item in explicit_rows
    }
    mapped_outcomes = set(objective_external_by_id.values())
    mapped_assignments = set(assessment_external_by_id.values())
    comparable_explicit = {
        pair
        for pair in explicit_pairs
        if pair[0] in mapped_outcomes and pair[1] in mapped_assignments
    }
    if not comparable_explicit:
        return {
            "available": False,
            "reason": "Canvas references could not be mapped to extracted objectives and assessments",
        }

    comparable_candidates = [
        item
        for item in candidates
        if item.source_id in objective_external_by_id
        and item.target_id in assessment_external_by_id
    ]
    if not comparable_candidates:
        return {
            "available": False,
            "reason": "No candidate scores can be mapped to Canvas IDs",
        }

    top_k = max(1, int((run.config or {}).get("top_k", 5)))
    current_threshold = float((run.config or {}).get("min_relation_score", 0.22))

    by_objective: dict[int, list[AlignmentCandidate]] = defaultdict(list)
    for item in comparable_candidates:
        by_objective[item.source_id].append(item)
    for rows in by_objective.values():
        rows.sort(key=lambda item: item.score, reverse=True)

    def metrics(threshold: float) -> dict:
        inferred: set[tuple[str, str]] = set()
        for source_id, rows in by_objective.items():
            for item in [row for row in rows if row.score >= threshold][:top_k]:
                inferred.add(
                    (
                        objective_external_by_id[source_id],
                        assessment_external_by_id[item.target_id],
                    )
                )
        matched = inferred & comparable_explicit
        false_positive = inferred - comparable_explicit
        missing = comparable_explicit - inferred
        tp, fp, fn = len(matched), len(false_positive), len(missing)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        return {
            "threshold": round(threshold, 4),
            "inferred_pairs": len(inferred),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    exact_thresholds = sorted(
        {0.0, current_threshold, *(float(item.score) for item in comparable_candidates)}
    )
    exact_metrics = [metrics(value) for value in exact_thresholds]
    best = max(
        exact_metrics,
        key=lambda item: (item["f1"], item["precision"], item["threshold"]),
    )
    if best["f1"] == 0:
        best = None

    curve_thresholds = {round(index / 20, 2) for index in range(21)} | {
        round(current_threshold, 4)
    }
    if best:
        curve_thresholds.add(best["threshold"])
    curve_thresholds = sorted(curve_thresholds)
    mapping_coverage = len(comparable_explicit) / len(explicit_pairs)
    reliable = len(comparable_explicit) >= 10 and mapping_coverage >= 0.8
    caveat = (
        "Порог рассчитан на текущем курсе. Подтвердите его на независимой выборке перед использованием по умолчанию."
        if reliable
        else "Недостаточно независимой разметки для надёжной калибровки: рекомендация диагностическая и может переобучиться на этом курсе."
    )
    return {
        "available": True,
        "current_threshold": round(current_threshold, 4),
        "current": metrics(current_threshold),
        "recommended_threshold": best["threshold"] if best else None,
        "recommended": best,
        "top_k": top_k,
        "labeled_positive_pairs": len(comparable_explicit),
        "comparable_candidates": len(comparable_candidates),
        "mapping_coverage": round(mapping_coverage, 4),
        "reliable": reliable,
        "caveat": caveat,
        "curve": [metrics(value) for value in curve_thresholds],
    }
