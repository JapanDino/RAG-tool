from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models.models import (
    AlignmentCandidate,
    AlignmentEdge,
    AssessmentItem,
    AuditRun,
    Course,
    CourseFinding,
    LearningMaterial,
    LearningObjective,
)
from .embedding import embed_texts

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
STOPWORDS = {
    "после",
    "модуля",
    "курса",
    "студент",
    "ученик",
    "должен",
    "должна",
    "сможет",
    "будет",
    "этот",
    "эта",
    "эти",
    "того",
    "чтобы",
    "который",
    "для",
    "или",
    "при",
    "как",
    "что",
    "это",
    "все",
    "его",
    "она",
    "они",
    "the",
    "and",
    "for",
    "with",
}


def semantic_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) >= 4 and token.lower() not in STOPWORDS
    }


def coverage_score(
    source_text: str, target_text: str, same_module: bool
) -> tuple[float, list[str]]:
    source = semantic_tokens(source_text)
    target = semantic_tokens(target_text)
    if not source or not target:
        return (0.12 if same_module else 0.0), []
    matches = sorted(source & target)
    lexical = len(matches) / len(source)
    score = min(1.0, lexical * 0.82 + (0.18 if same_module else 0.0))
    return round(score, 4), matches


def expected_bloom_level(vector: list) -> float:
    if not vector or len(vector) != 6:
        return 0.0
    total = sum(float(value) for value in vector)
    if total <= 0:
        return 0.0
    return sum(index * float(value) for index, value in enumerate(vector)) / total


def bloom_mismatch_magnitude(source: list, target: list) -> tuple[float, float, int]:
    expected_difference = expected_bloom_level(target) - expected_bloom_level(source)
    source_dominant = (
        max(range(6), key=lambda index: float(source[index]))
        if len(source or []) == 6
        else 0
    )
    target_dominant = (
        max(range(6), key=lambda index: float(target[index]))
        if len(target or []) == 6
        else 0
    )
    dominant_difference = target_dominant - source_dominant
    magnitude = max(abs(expected_difference), abs(dominant_difference))
    direction_value = (
        dominant_difference
        if abs(dominant_difference) >= abs(expected_difference)
        else expected_difference
    )
    return (
        magnitude,
        expected_difference,
        int(direction_value > 0) - int(direction_value < 0),
    )


def build_alignment_edges(
    db: Session,
    course: Course,
    run: AuditRun,
    min_score: float = 0.22,
    top_k: int = 5,
) -> dict[str, int]:
    objectives = (
        db.query(LearningObjective)
        .filter(LearningObjective.audit_run_id == run.id)
        .all()
    )
    materials = (
        db.query(LearningMaterial).filter(LearningMaterial.audit_run_id == run.id).all()
    )
    assessments = (
        db.query(AssessmentItem).filter(AssessmentItem.audit_run_id == run.id).all()
    )
    counters = {"teaches": 0, "assesses": 0}
    embedding_lookup = _alignment_embeddings(objectives, materials, assessments)
    relation_method = (
        "hybrid_embedding_lexical_module-v1"
        if embedding_lookup
        else "lexical_module_baseline-v1"
    )

    for objective in objectives:
        material_candidates = []
        for material in materials:
            same_module = (
                objective.module_id is not None
                and objective.module_id == material.module_id
            )
            score, matches = coverage_score(
                objective.text, material.source_text, same_module
            )
            embedding_similarity = _embedding_similarity(
                embedding_lookup, ("objective", objective.id), ("material", material.id)
            )
            if embedding_similarity is not None:
                score = round(
                    min(1.0, score * 0.7 + max(0.0, embedding_similarity) * 0.3), 4
                )
            if score >= min_score:
                material_candidates.append(
                    (score, material, matches, same_module, embedding_similarity)
                )
        for score, material, matches, same_module, embedding_similarity in sorted(
            material_candidates, reverse=True, key=lambda row: row[0]
        )[:top_k]:
            db.add(
                AlignmentEdge(
                    course_id=course.id,
                    audit_run_id=run.id,
                    source_type="learning_objective",
                    source_id=objective.id,
                    target_type="learning_material",
                    target_id=material.id,
                    relation_type="teaches",
                    score=score,
                    evidence=[
                        {
                            "object_type": "learning_objective",
                            "object_id": objective.id,
                            "quote": objective.text,
                            "document_id": objective.document_id,
                            "start": objective.source_start,
                            "end": objective.source_end,
                        },
                        {
                            "object_type": "learning_material",
                            "object_id": material.id,
                            "quote": material.source_text[:500],
                            "document_id": material.document_id,
                            "matched_terms": matches,
                        },
                    ],
                    method=relation_method,
                    model_info={
                        "matched_terms": matches,
                        "same_module": same_module,
                        "embedding_similarity": embedding_similarity,
                    },
                )
            )
            counters["teaches"] += 1

        assessment_candidates = []
        for assessment in assessments:
            same_module = (
                objective.module_id is not None
                and objective.module_id == assessment.module_id
            )
            score, matches = coverage_score(
                objective.text, assessment.text, same_module
            )
            embedding_similarity = _embedding_similarity(
                embedding_lookup,
                ("objective", objective.id),
                ("assessment", assessment.id),
            )
            if embedding_similarity is not None:
                score = round(
                    min(1.0, score * 0.7 + max(0.0, embedding_similarity) * 0.3), 4
                )
            assessment_candidates.append(
                (score, assessment, matches, same_module, embedding_similarity)
            )
        selected_assessments = sorted(
            [row for row in assessment_candidates if row[0] >= min_score],
            reverse=True,
            key=lambda row: row[0],
        )[:top_k]
        selected_ids = {row[1].id for row in selected_assessments}
        for (
            score,
            assessment,
            matches,
            same_module,
            embedding_similarity,
        ) in assessment_candidates:
            db.add(
                AlignmentCandidate(
                    course_id=course.id,
                    audit_run_id=run.id,
                    source_type="learning_objective",
                    source_id=objective.id,
                    target_type="assessment_item",
                    target_id=assessment.id,
                    relation_type="assesses",
                    score=score,
                    selected=assessment.id in selected_ids,
                    method=relation_method,
                    model_info={
                        "matched_terms": matches,
                        "same_module": same_module,
                        "embedding_similarity": embedding_similarity,
                    },
                )
            )
        for (
            score,
            assessment,
            matches,
            same_module,
            embedding_similarity,
        ) in selected_assessments:
            db.add(
                AlignmentEdge(
                    course_id=course.id,
                    audit_run_id=run.id,
                    source_type="learning_objective",
                    source_id=objective.id,
                    target_type="assessment_item",
                    target_id=assessment.id,
                    relation_type="assesses",
                    score=score,
                    evidence=[
                        {
                            "object_type": "learning_objective",
                            "object_id": objective.id,
                            "quote": objective.text,
                            "document_id": objective.document_id,
                            "start": objective.source_start,
                            "end": objective.source_end,
                        },
                        {
                            "object_type": "assessment_item",
                            "object_id": assessment.id,
                            "quote": assessment.text,
                            "document_id": assessment.document_id,
                            "start": assessment.source_start,
                            "end": assessment.source_end,
                            "matched_terms": matches,
                        },
                    ],
                    method=relation_method,
                    model_info={
                        "matched_terms": matches,
                        "same_module": same_module,
                        "embedding_similarity": embedding_similarity,
                    },
                )
            )
            counters["assesses"] += 1
    db.flush()
    return counters


def _alignment_embeddings(
    objectives, materials, assessments
) -> dict[tuple[str, int], list[float]]:
    objects = (
        [("objective", item.id, item.text) for item in objectives]
        + [("material", item.id, item.source_text) for item in materials]
        + [("assessment", item.id, item.text) for item in assessments]
    )
    if not objects:
        return {}
    try:
        vectors = embed_texts([item[2] for item in objects])
    except Exception:
        return {}
    return {
        (kind, object_id): vector
        for (kind, object_id, _), vector in zip(objects, vectors)
    }


def _embedding_similarity(
    lookup: dict[tuple[str, int], list[float]],
    left_key: tuple[str, int],
    right_key: tuple[str, int],
) -> float | None:
    left = lookup.get(left_key)
    right = lookup.get(right_key)
    if left is None or right is None or len(left) != len(right):
        return None
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return round(sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm), 4)


@dataclass(frozen=True)
class FindingDraft:
    finding_type: str
    severity: str
    title: str
    description: str
    evidence: list
    recommendation: str
    confidence: float
    uncertainty_reasons: list
    module_id: int | None
    fingerprint: str


def finding_fingerprint(
    finding_type: str, module_id: int | None, stable_text: str
) -> str:
    raw = f"{finding_type}|{module_id or 0}|{' '.join(stable_text.lower().split())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def detect_findings(db: Session, course: Course, run: AuditRun) -> dict[str, int]:
    objectives = (
        db.query(LearningObjective)
        .filter(LearningObjective.audit_run_id == run.id)
        .all()
    )
    assessments = {
        item.id: item
        for item in db.query(AssessmentItem)
        .filter(AssessmentItem.audit_run_id == run.id)
        .all()
    }
    edges = db.query(AlignmentEdge).filter(AlignmentEdge.audit_run_id == run.id).all()
    by_objective: dict[int, dict[str, list[AlignmentEdge]]] = {}
    for edge in edges:
        by_objective.setdefault(edge.source_id, {}).setdefault(
            edge.relation_type, []
        ).append(edge)

    previous_reviews = {}
    previous = (
        db.query(CourseFinding)
        .filter(
            CourseFinding.course_id == course.id, CourseFinding.audit_run_id != run.id
        )
        .order_by(CourseFinding.created_at.desc(), CourseFinding.id.desc())
        .all()
    )
    for item in previous:
        fingerprint = (item.model_info or {}).get("fingerprint")
        if fingerprint and fingerprint not in previous_reviews and item.status != "new":
            previous_reviews[fingerprint] = item

    drafts: list[FindingDraft] = []
    for objective in objectives:
        objective_edges = by_objective.get(objective.id, {})
        objective_evidence = [
            {
                "object_type": "learning_objective",
                "object_id": objective.id,
                "quote": objective.text,
                "document_id": objective.document_id,
                "start": objective.source_start,
                "end": objective.source_end,
            }
        ]
        if not objective_edges.get("teaches"):
            finding_type = "objective_without_material"
            drafts.append(
                FindingDraft(
                    finding_type,
                    "medium",
                    "Цель не обеспечена учебным материалом",
                    f"Для цели «{objective.text}» не найден материал с достаточным подтверждением связи.",
                    objective_evidence,
                    "Добавьте или явно свяжите материал, который объясняет эту цель.",
                    round(min(0.95, objective.confidence * 0.9), 3),
                    ["Связи ниже порога могли быть отброшены"],
                    objective.module_id,
                    finding_fingerprint(
                        finding_type, objective.module_id, objective.normalized_text
                    ),
                )
            )
        if not objective_edges.get("assesses"):
            finding_type = "objective_without_assessment"
            drafts.append(
                FindingDraft(
                    finding_type,
                    "high",
                    "Цель не проверяется заданием",
                    f"Для цели «{objective.text}» не найдено проверяющее задание.",
                    objective_evidence,
                    "Добавьте задание, которое непосредственно проверяет достижение цели.",
                    round(min(0.95, objective.confidence * 0.9), 3),
                    ["Связи ниже порога могли быть отброшены"],
                    objective.module_id,
                    finding_fingerprint(
                        finding_type, objective.module_id, objective.normalized_text
                    ),
                )
            )

        for edge in objective_edges.get("assesses", []):
            assessment = assessments.get(edge.target_id)
            if assessment is None:
                continue
            magnitude, expected_difference, direction_sign = bloom_mismatch_magnitude(
                objective.bloom_vector, assessment.bloom_vector
            )
            if magnitude < 2.0:
                continue
            direction = "over_assessment" if direction_sign > 0 else "under_assessment"
            finding_type = "bloom_mismatch"
            stable_text = f"{objective.normalized_text}|{' '.join(assessment.text.lower().split())}|{direction}"
            drafts.append(
                FindingDraft(
                    finding_type,
                    "high" if magnitude >= 3 else "medium",
                    "Несоответствие уровней Блума",
                    f"Цель и задание различаются по когнитивному уровню ({direction}, {magnitude:.2f}; "
                    f"разница математических ожиданий {abs(expected_difference):.2f}).",
                    edge.evidence,
                    "Скорректируйте формулировку цели или сложность задания и повторите аудит.",
                    round(
                        min(objective.confidence, assessment.confidence, edge.score), 3
                    ),
                    (
                        []
                        if edge.score >= 0.5
                        else ["Семантическая связь имеет среднюю уверенность"]
                    ),
                    objective.module_id,
                    finding_fingerprint(finding_type, objective.module_id, stable_text),
                )
            )

    counts: dict[str, int] = {}
    for draft in drafts:
        prior = previous_reviews.get(draft.fingerprint)
        finding = CourseFinding(
            course_id=course.id,
            module_id=draft.module_id,
            audit_run_id=run.id,
            finding_type=draft.finding_type,
            severity=draft.severity,
            title=draft.title,
            description=draft.description,
            evidence=draft.evidence,
            recommendation=draft.recommendation,
            confidence=draft.confidence,
            uncertainty_reasons=draft.uncertainty_reasons,
            status=prior.status if prior else "new",
            reviewed_by=prior.reviewed_by if prior else None,
            reviewed_at=prior.reviewed_at if prior else None,
            model_info={
                "detector_version": "course-findings-v1",
                "fingerprint": draft.fingerprint,
                "carried_review_from": prior.id if prior else None,
            },
        )
        db.add(finding)
        counts[draft.finding_type] = counts.get(draft.finding_type, 0) + 1
    db.flush()
    counts["total"] = len(drafts)
    return counts
