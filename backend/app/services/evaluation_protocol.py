from __future__ import annotations

import json
import logging
import re
from time import perf_counter

from sqlalchemy.orm import Session

from ..models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseCopilotSuggestion,
    CourseEvaluationProtocol,
    CourseQuestionAnswer,
    Document,
)
from .canvas_alignment_evaluation import evaluate_canvas_alignment
from .course_qa import STUDENT_TUTOR_DOCUMENT_TYPES, retrieve_student_tutor_context
from .course_retrieval import (
    document_is_student_visible,
    resolve_retrieval_limits,
    tokenize,
)
from .tutor_evaluation import (
    TUTOR_BENCHMARK_THRESHOLDS,
    evaluate_tutor_benchmark,
    tutor_benchmark_path,
)

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = "course-quality-evaluation-v2"
DEFAULT_THRESHOLDS = {
    **TUTOR_BENCHMARK_THRESHOLDS,
    "course_tutor_index_ready": 1,
    "citation_integrity": 1.0,
    "audit_success_rate": 0.9,
    "runtime_ms": 5000,
}
METHODOLOGY = [
    "Student tutor benchmark: run the committed bilingual synthetic cases with production normalization, hybrid scoring weights, and assessment-guard logic.",
    "Retrieval and abstention: measure Recall@K, MRR, and unsupported-question refusal using deterministic hash embeddings.",
    "Assessment guard: compare fixed ready-answer and assessment-overlap classifications with labeled expected outcomes.",
    "Labeled citation support: verify selected synthetic evidence contains the labeled support terms; this lexical proxy does not prove semantic entailment.",
    "Offline latency: report per-case p95 for retrieval and policy classification, excluding database, network, and hosted-model time.",
    "Course readiness smoke: require at least one indexed student-visible learning resource and retrieve a seed through the complete tutor path using the effective deployment provider and limits.",
    "Citation integrity audit: verify course scope, chunk/document identity, and that every stored quote exists in its chunk.",
    "Operational audit: calculate the success rate of completed course audit runs.",
    "Optional Canvas validation: include teacher-authored Outcome Alignment precision/recall/F1 when available.",
    "The bundled tutor set is a synthetic regression benchmark, not an independent production acceptance sample.",
]


def _course_tutor_readiness(db: Session, course: Course) -> dict:
    effective_max_candidates, effective_min_score = resolve_retrieval_limits()
    documents = (
        db.query(Document)
        .filter(
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .order_by(Document.id)
        .all()
    )
    visible_documents = [
        item
        for item in documents
        if str((item.source_metadata or {}).get("document_type", "unknown"))
        in STUDENT_TUTOR_DOCUMENT_TYPES
        and document_is_student_visible(item, course)
    ]
    document_ids = [item.id for item in visible_documents]
    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id.in_(document_ids))
        .order_by(Chunk.document_id, Chunk.idx)
        .all()
        if document_ids
        else []
    )
    seed = next(
        (
            item
            for item in chunks
            if any(not token.startswith("~") for token in tokenize(item.text))
        ),
        None,
    )
    result = {
        "ready": False,
        "student_visible_documents": len(visible_documents),
        "indexed_chunks": len(chunks),
        "smoke_hit": False,
        "retrieval_method": None,
        "seed_chunk_id": seed.id if seed is not None else None,
        "effective_min_score": effective_min_score,
        "effective_max_candidates": effective_max_candidates,
    }
    if seed is None:
        return result
    query_tokens = []
    for token in tokenize(seed.text):
        if token.startswith("~") or token in query_tokens:
            continue
        query_tokens.append(token)
        if len(query_tokens) >= 10:
            break
    if not query_tokens:
        return result
    hits, method = retrieve_student_tutor_context(
        db,
        course,
        " ".join(query_tokens),
        top_k=5,
        max_candidates=effective_max_candidates,
        min_score=effective_min_score,
    )
    smoke_hit = any(item.chunk_id == seed.id for item in hits)
    result.update(
        {
            "ready": smoke_hit,
            "smoke_hit": smoke_hit,
            "retrieval_method": method,
        }
    )
    return result


def _normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _citation_integrity(db: Session, course: Course) -> dict:
    documents = (
        db.query(Document).filter(Document.dataset_id == course.dataset_id).all()
    )
    document_ids = {item.id for item in documents}
    chunks = (
        db.query(Chunk).filter(Chunk.document_id.in_(document_ids)).all()
        if document_ids
        else []
    )
    chunk_by_id = {item.id: item for item in chunks}
    citation_groups = [
        ("course_qa", item.id, item.citations or [])
        for item in db.query(CourseQuestionAnswer).filter(
            CourseQuestionAnswer.course_id == course.id
        )
    ] + [
        ("copilot_remediation", item.id, item.citations or [])
        for item in db.query(CourseCopilotSuggestion).filter(
            CourseCopilotSuggestion.course_id == course.id
        )
    ]
    total = valid = 0
    invalid = []
    for artifact_type, artifact_id, citations in citation_groups:
        for citation in citations:
            total += 1
            try:
                document_id = int(citation.get("document_id"))
                chunk_id = int(citation.get("chunk_id"))
            except (TypeError, ValueError):
                invalid.append(
                    {
                        "artifact_type": artifact_type,
                        "artifact_id": artifact_id,
                        "reason": "invalid IDs",
                    }
                )
                continue
            chunk = chunk_by_id.get(chunk_id)
            quote = _normalize_quote(str(citation.get("quote") or ""))
            chunk_text = _normalize_quote(chunk.text) if chunk is not None else ""
            is_valid = (
                document_id in document_ids
                and chunk is not None
                and chunk.document_id == document_id
                and bool(quote)
                and quote in chunk_text
            )
            if is_valid:
                valid += 1
            else:
                invalid.append(
                    {
                        "artifact_type": artifact_type,
                        "artifact_id": artifact_id,
                        "reason": "scope or quote mismatch",
                    }
                )
    return {
        "citations_total": total,
        "citations_valid": valid,
        "integrity_rate": round(valid / total, 4) if total else None,
        "invalid": invalid[:50],
    }


def _check(
    check_id: str,
    label: str,
    value: float | int | None,
    threshold: float | int,
    operator: str,
    *,
    required: bool = True,
    notes: str = "",
) -> dict:
    if value is None:
        passed = None
    elif operator == ">=":
        passed = value >= threshold
    elif operator == "<=":
        passed = value <= threshold
    else:
        raise ValueError(f"unsupported operator: {operator}")
    return {
        "check_id": check_id,
        "label": label,
        "value": value,
        "threshold": threshold,
        "operator": operator,
        "passed": passed,
        "required": required,
        "notes": notes,
    }


def run_evaluation_protocol(db: Session, course: Course) -> CourseEvaluationProtocol:
    started = perf_counter()
    path = tutor_benchmark_path()
    dataset_name = path.name
    try:
        raw = path.read_bytes()
        benchmark = evaluate_tutor_benchmark(raw, dataset_name=dataset_name)
        dataset_hash = benchmark["dataset_hash"]
        retrieval = benchmark["retrieval"]
        citations = _citation_integrity(db, course)
        course_tutor = _course_tutor_readiness(db, course)
        runs = db.query(AuditRun).filter(AuditRun.course_id == course.id).all()
        terminal_runs = [item for item in runs if item.status in {"done", "failed"}]
        audit_success_rate = (
            sum(item.status == "done" for item in terminal_runs) / len(terminal_runs)
            if terminal_runs
            else None
        )
        questions = (
            db.query(CourseQuestionAnswer)
            .filter(CourseQuestionAnswer.course_id == course.id)
            .all()
        )
        reviewed = [item for item in questions if item.feedback_status != "unreviewed"]
        feedback = {
            "questions_total": len(questions),
            "grounded_rate": (
                round(
                    sum(not item.insufficient_context for item in questions)
                    / len(questions),
                    4,
                )
                if questions
                else None
            ),
            "reviewed_answers": len(reviewed),
            "helpful_rate": (
                round(
                    sum(item.feedback_status == "helpful" for item in reviewed)
                    / len(reviewed),
                    4,
                )
                if reviewed
                else None
            ),
        }
        latest_done = next(
            (
                item
                for item in sorted(runs, key=lambda item: item.id, reverse=True)
                if item.status == "done"
            ),
            None,
        )
        canvas = (
            evaluate_canvas_alignment(db, latest_done.id)
            if latest_done is not None
            else {"available": False}
        )
        checks = [
            {**item, "notes": "Synthetic offline regression gate."}
            for item in benchmark["checks"]
        ] + [
            _check(
                "course_tutor_index_ready",
                "Student-visible course index ready",
                int(course_tutor["ready"]),
                DEFAULT_THRESHOLDS["course_tutor_index_ready"],
                ">=",
                notes=(
                    "Required course-scoped smoke through the complete student tutor "
                    "retrieval path."
                ),
            ),
            _check(
                "citation_integrity",
                "Stored citation integrity",
                citations["integrity_rate"],
                DEFAULT_THRESHOLDS["citation_integrity"],
                ">=",
                required=citations["citations_total"] > 0,
                notes="Not run until at least one Q&A or Copilot citation exists.",
            ),
            _check(
                "audit_success_rate",
                "Course audit success rate",
                (
                    round(audit_success_rate, 4)
                    if audit_success_rate is not None
                    else None
                ),
                DEFAULT_THRESHOLDS["audit_success_rate"],
                ">=",
                required=bool(terminal_runs),
                notes="Not run until at least one audit reaches a terminal state.",
            ),
        ]
        duration_ms = round((perf_counter() - started) * 1000, 2)
        checks.append(
            _check(
                "runtime_ms",
                "Evaluation runtime",
                duration_ms,
                DEFAULT_THRESHOLDS["runtime_ms"],
                "<=",
            )
        )
        required_results = [
            item["passed"]
            for item in checks
            if item["required"] and item["passed"] is not None
        ]
        status = "passed" if required_results and all(required_results) else "failed"
        protocol = CourseEvaluationProtocol(
            course_id=course.id,
            status=status,
            protocol_version=PROTOCOL_VERSION,
            dataset_name=dataset_name,
            dataset_hash=dataset_hash,
            thresholds=DEFAULT_THRESHOLDS,
            metrics={
                "retrieval": retrieval,
                "student_tutor": {
                    "schema_version": benchmark["schema_version"],
                    "embedding_model": benchmark["embedding_model"],
                    "retrieval_pipeline_version": benchmark[
                        "retrieval_pipeline_version"
                    ],
                    "min_score": benchmark["min_score"],
                    "max_candidates": benchmark["max_candidates"],
                    "course_index": course_tutor,
                    "guard": benchmark["guard"],
                    "citation_support": benchmark["citation_support"],
                    "latency": benchmark["latency"],
                    "case_details": benchmark["details"],
                },
                "citations": citations,
                "operations": {
                    "audit_runs_total": len(runs),
                    "terminal_audit_runs": len(terminal_runs),
                    "audit_success_rate": (
                        round(audit_success_rate, 4)
                        if audit_success_rate is not None
                        else None
                    ),
                },
                "feedback": feedback,
                "canvas_alignment": canvas,
            },
            checks=checks,
            methodology=METHODOLOGY,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        logger.exception("evaluation protocol failed for course_id=%s", course.id)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        protocol = CourseEvaluationProtocol(
            course_id=course.id,
            status="error",
            protocol_version=PROTOCOL_VERSION,
            dataset_name=dataset_name,
            dataset_hash="",
            thresholds=DEFAULT_THRESHOLDS,
            metrics={},
            checks=[],
            methodology=METHODOLOGY,
            duration_ms=duration_ms,
            error=(
                f"{type(exc).__name__}: evaluation protocol could not be completed; "
                "inspect server logs for details."
            ),
        )
    db.add(protocol)
    db.commit()
    db.refresh(protocol)
    return protocol


def evaluation_protocol_markdown(
    protocol: CourseEvaluationProtocol, course: Course
) -> str:
    lines = [
        f"# Протокол испытаний Course Quality Auditor #{protocol.id}",
        "",
        f"- Курс: {course.title}",
        f"- Статус: **{protocol.status.upper()}**",
        f"- Версия методики: `{protocol.protocol_version}`",
        f"- Набор данных: `{protocol.dataset_name}`",
        f"- SHA-256: `{protocol.dataset_hash or 'unavailable'}`",
        f"- Продолжительность: {protocol.duration_ms:.2f} ms",
        "",
        "## Программа и методика испытаний",
        "",
        *[
            f"{index}. {step}"
            for index, step in enumerate(protocol.methodology or [], start=1)
        ],
        "",
        "## Критерии приёмки",
        "",
        "| Проверка | Результат | Порог | Статус |",
        "|---|---:|---:|---|",
    ]
    for check in protocol.checks or []:
        state = (
            "PASS"
            if check.get("passed") is True
            else "FAIL" if check.get("passed") is False else "NOT RUN"
        )
        value = check.get("value")
        rendered_value = (
            "—"
            if value is None
            else f"{value:.4f}" if isinstance(value, float) else str(value)
        )
        lines.append(
            f"| {check['label']} | {rendered_value} | {check['operator']} {check['threshold']} | {state} |"
        )
    lines.extend(
        [
            "",
            "## Измеренные показатели",
            "",
            "```json",
            json.dumps(protocol.metrics or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "> Ограничение: встроенный tutor benchmark является синтетическим regression-набором. Labeled citation support — лексический proxy, а offline latency не включает модель и сеть. Для production-приёмки нужна независимая teacher-validated выборка.",
        ]
    )
    if protocol.error:
        lines.extend(["", "## Ошибка", "", protocol.error])
    return "\n".join(lines).strip() + "\n"
