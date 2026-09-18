from __future__ import annotations

import hashlib
import hmac
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    AgentToolEvent,
    AssessmentItem,
    Chunk,
    Course,
    CourseModule,
    CourseQuestionAnswer,
    Document,
)
from .agent_policy import TOOL_REGISTRY, WORKFLOW_REGISTRY
from .agent_run import AgentTrustedContext, resolve_agent_context
from .authorization import Principal
from .course_map import build_course_map, resolve_document_course_map_item
from .course_qa import answer_course_question, retrieve_student_tutor_context
from .course_retrieval import document_is_student_visible
from .embedding_provider import EmbeddingProvider, HashingProvider
from .tutor_policy import get_effective_tutor_policy

EXECUTABLE_LEARNER_WORKFLOWS = frozenset(
    {
        "learner.explain_material.v1",
        "learner.assessment_safe_hint.v1",
        "learner.self_check.v1",
        "learner.locate_source.v1",
    }
)


class LearnerToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    module_ref: str | None = Field(default=None, min_length=1, max_length=160)


class LearnerToolCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=20)
    chunk_id: int = Field(ge=1)
    document_id: int = Field(ge=1)
    document_title: str = Field(min_length=1, max_length=500)
    module_title: str | None = Field(default=None, max_length=500)
    quote: str = Field(min_length=1, max_length=2000)
    score: float = Field(ge=0.0, le=1.0)


class LearnerToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=6000)
    mode: str = Field(pattern=r"^(answer|guidance|self_check|abstained)$")
    confidence: float = Field(ge=0.0, le=1.0)
    insufficient_context: bool
    citations: list[LearnerToolCitation] = Field(max_length=8)
    retrieval_method: str = Field(min_length=1, max_length=255)
    generation_provider: str = Field(min_length=1, max_length=100)
    generation_model: str | None = Field(default=None, max_length=255)
    policy_reason: str | None = Field(default=None, max_length=100)
    tutor_policy_version: int = Field(ge=0)
    tutor_answer_style: str = Field(pattern=r"^(balanced|guided|concise)$")


class LearnerSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_ref: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=160)


class LearnerSourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    destination_url: str = Field(min_length=1, max_length=2000)
    provenance: Literal["canvas", "external"]


class RetrievePublishedEvidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    module_ref: str | None = Field(default=None, max_length=160)
    top_k: int = Field(ge=1, le=8)


class RetrievePublishedEvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_refs: list[str] = Field(max_length=8)
    excerpts: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)


class ExplainWithCitationsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(max_length=8)


class ExplainWithCitationsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=6000)
    citations: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool


class AssessmentSafeHintOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["guidance", "abstained"]
    guidance: str = Field(min_length=1, max_length=6000)
    citations: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool


class CreateSelfCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(max_length=8)
    item_count: int = Field(ge=1, le=3)


class CreateSelfCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(max_length=3)
    feedback_policy: Literal["formative_no_answers"]
    citations: list[str] = Field(max_length=8)


class CurrentCourseMapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_ref: str | None = Field(default=None, max_length=160)


class CurrentCourseMapOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modules: list[str] = Field(max_length=100)
    destinations: list[str] = Field(max_length=500)


class OpenAuthoritativeSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_ref: str = Field(min_length=1, max_length=160)


class OpenAuthoritativeSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_ref: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=300)


@dataclass(frozen=True)
class LearnerToolAuditSnapshot:
    tool_name: str
    status: Literal["succeeded", "abstained", "failed"]
    latency_ms: int
    failure_class: str | None


def learner_tool_audit_snapshots(
    exc: Exception,
) -> tuple[LearnerToolAuditSnapshot, ...]:
    value = getattr(exc, "_learner_tool_audit_snapshots", ())
    if not isinstance(value, tuple) or not all(
        isinstance(item, LearnerToolAuditSnapshot) for item in value
    ):
        return ()
    return value


class _DeadlineHashingProvider(EmbeddingProvider):
    """Deterministic, network-free embeddings with cooperative deadline checks."""

    name = "hash"

    def __init__(self, deadline_monotonic: float):
        self._deadline_monotonic = deadline_monotonic
        self._provider = HashingProvider()

    @property
    def embedding_model(self) -> str:
        return self._provider.embedding_model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Small batches bound the interval between cooperative checks while
        # avoiding a network/model call that could outlive the tool deadline.
        for start in range(0, len(texts), 16):
            if time.monotonic() >= self._deadline_monotonic:
                raise TimeoutError("tool deadline exceeded")
            vectors.extend(self._provider.embed(texts[start : start + 16]))
        if time.monotonic() >= self._deadline_monotonic:
            raise TimeoutError("tool deadline exceeded")
        return vectors


def _configure_statement_timeout(db: Session, timeout_seconds: int) -> None:
    """Bound database work for the current PostgreSQL transaction."""

    if db.get_bind().dialect.name == "postgresql":
        timeout_ms = max(1, int(timeout_seconds * 1000))
        db.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        db.execute(text(f"SET LOCAL lock_timeout = {timeout_ms}"))


@contextmanager
def _database_deadline(db: Session, deadline_monotonic: float):
    """Apply the remaining absolute budget before every PostgreSQL statement."""

    if db.get_bind().dialect.name != "postgresql":
        yield
        return

    connection = db.connection()

    def set_remaining_timeout(
        _connection,
        cursor,
        _statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        remaining_ms = int((deadline_monotonic - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise TimeoutError("tool deadline exceeded")
        cursor.execute(f"SET LOCAL statement_timeout = {remaining_ms}")
        cursor.execute(f"SET LOCAL lock_timeout = {remaining_ms}")

    event.listen(connection, "before_cursor_execute", set_remaining_timeout)
    try:
        yield
    finally:
        event.remove(connection, "before_cursor_execute", set_remaining_timeout)


def _tool_event(
    db: Session,
    row: AgentRun,
    *,
    tool_name: str,
    status: Literal["succeeded", "abstained", "failed"],
    latency_ms: int,
    failure_class: str | None = None,
) -> None:
    exists = (
        db.query(AgentToolEvent.id)
        .filter(
            AgentToolEvent.agent_run_id == row.id,
            AgentToolEvent.tool_name == tool_name,
        )
        .first()
    )
    if exists is None:
        db.add(
            AgentToolEvent(
                agent_run_id=row.id,
                tool_name=tool_name,
                status=status,
                latency_ms=max(0, latency_ms),
                failure_class=failure_class,
            )
        )


def _run_validated_tool(
    db: Session,
    row: AgentRun,
    principal: Principal,
    *,
    tool_name: str,
    tool_input: BaseModel,
    call: Callable[[float], Any],
    output_projection: Callable[[Any], BaseModel],
    organization_id: int | None = None,
) -> Any:
    definition = TOOL_REGISTRY[tool_name]
    prior_audits: tuple[LearnerToolAuditSnapshot, ...] = tuple(
        getattr(row, "_learner_tool_audit_ledger", ())
    )
    if (
        row.workflow is None
        or tool_name not in WORKFLOW_REGISTRY[row.workflow].tools
        or row.role not in definition.roles
        or set(type(tool_input).model_fields) != set(definition.input_schema.fields)
    ):
        raise ValueError("tool adapter contract mismatch")
    if (
        len(tool_input.model_dump_json().encode("utf-8"))
        > definition.input_schema.max_bytes
    ):
        budget_audit = LearnerToolAuditSnapshot(
            tool_name=tool_name,
            status="failed",
            latency_ms=0,
            failure_class="budget_exceeded",
        )
        budget_exc = HTTPException(
            status_code=429,
            detail={"code": "budget_exceeded"},
        )
        audit_snapshots = (*prior_audits, budget_audit)
        setattr(budget_exc, "_learner_tool_audit_snapshots", audit_snapshots)
        try:
            _tool_event(
                db,
                row,
                tool_name=budget_audit.tool_name,
                status=budget_audit.status,
                latency_ms=budget_audit.latency_ms,
                failure_class=budget_audit.failure_class,
            )
            db.flush()
        except SQLAlchemyError as audit_exc:
            setattr(audit_exc, "_learner_tool_audit_snapshots", audit_snapshots)
            raise audit_exc from budget_exc
        raise budget_exc
    started_at = time.monotonic()
    deadline_monotonic = started_at + definition.timeout_seconds
    try:
        with _database_deadline(db, deadline_monotonic):
            current = resolve_agent_context(
                db, principal, organization_id=organization_id
            )
            if not _exact_context(row, current):
                _deny()
            value = call(deadline_monotonic)
            if time.monotonic() >= deadline_monotonic:
                raise TimeoutError("tool deadline exceeded")
            output = output_projection(value)
            latency_ms = round((time.monotonic() - started_at) * 1000)
            if set(type(output).model_fields) != set(definition.output_schema.fields):
                raise ValueError("tool result contract mismatch")
            if (
                len(output.model_dump_json().encode("utf-8"))
                > definition.max_output_bytes
            ):
                raise ValueError("tool output budget exceeded")
            if time.monotonic() >= deadline_monotonic:
                raise TimeoutError("tool deadline exceeded")
            current = resolve_agent_context(
                db, principal, organization_id=organization_id
            )
            if not _exact_context(row, current):
                _deny()
            succeeded_audit = LearnerToolAuditSnapshot(
                tool_name=tool_name,
                status=(
                    "abstained"
                    if bool(getattr(value, "insufficient_context", False))
                    else "succeeded"
                ),
                latency_ms=latency_ms,
                failure_class=(
                    "resource_unavailable"
                    if bool(getattr(value, "insufficient_context", False))
                    else None
                ),
            )
            _tool_event(
                db,
                row,
                tool_name=succeeded_audit.tool_name,
                status=succeeded_audit.status,
                latency_ms=succeeded_audit.latency_ms,
                failure_class=succeeded_audit.failure_class,
            )
            db.flush()
            setattr(
                row,
                "_learner_tool_audit_ledger",
                (*prior_audits, succeeded_audit),
            )
        return value
    except SQLAlchemyError as exc:
        # PostgreSQL statement/lock timeouts abort the whole transaction. Do
        # not attempt another statement here; the router recreates this
        # content-free audit together with the terminal state after rollback.
        failure_class = (
            "timeout"
            if "timeout" in str(exc).lower()
            or "canceling statement" in str(exc).lower()
            else "temporary_failure"
        )
        setattr(
            exc,
            "_learner_tool_audit_snapshots",
            (
                *prior_audits,
                LearnerToolAuditSnapshot(
                    tool_name=tool_name,
                    status="failed",
                    latency_ms=round((time.monotonic() - started_at) * 1000),
                    failure_class=failure_class,
                ),
            ),
        )
        raise
    except Exception as exc:
        failure_audit = LearnerToolAuditSnapshot(
            tool_name=tool_name,
            status="abstained" if isinstance(exc, HTTPException) else "failed",
            latency_ms=round((time.monotonic() - started_at) * 1000),
            failure_class=(
                "resource_unavailable"
                if isinstance(exc, HTTPException) and exc.status_code == 404
                else (
                    "budget_exceeded"
                    if isinstance(exc, HTTPException) and exc.status_code == 429
                    else (
                        "timeout"
                        if isinstance(exc, TimeoutError)
                        else "temporary_failure"
                    )
                )
            ),
        )
        audit_snapshots = (*prior_audits, failure_audit)
        setattr(exc, "_learner_tool_audit_snapshots", audit_snapshots)
        try:
            _tool_event(
                db,
                row,
                tool_name=tool_name,
                status=failure_audit.status,
                latency_ms=failure_audit.latency_ms,
                failure_class=failure_audit.failure_class,
            )
            db.flush()
        except SQLAlchemyError as audit_exc:
            setattr(audit_exc, "_learner_tool_audit_snapshots", audit_snapshots)
            raise audit_exc from exc
        raise


def _normalized_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def validate_learner_citations(
    db: Session,
    course: Course,
    citations: list[dict],
    *,
    module_id: int | None,
) -> list[dict]:
    assessment_document_ids = {
        document_id
        for (document_id,) in db.query(AssessmentItem.document_id)
        .filter(
            AssessmentItem.course_id == course.id,
            AssessmentItem.document_id.is_not(None),
        )
        .all()
        if document_id is not None
    }
    validated: list[dict] = []
    seen_chunks: set[int] = set()
    for raw in citations:
        citation = LearnerToolCitation.model_validate(
            {field: raw.get(field) for field in LearnerToolCitation.model_fields}
        )
        if citation.chunk_id in seen_chunks:
            raise ValueError("duplicate learner citation")
        chunk = db.get(Chunk, citation.chunk_id)
        document = db.get(Document, citation.document_id)
        module = (
            db.get(CourseModule, document.course_module_id)
            if document is not None and document.course_module_id is not None
            else None
        )
        expected_quote = (
            _normalized_quote(chunk.text)[:900] if chunk is not None else ""
        )
        document_type = (
            str(
                (
                    (document.source_metadata or {}).get("document_type")
                    if document
                    else ""
                )
                or ""
            )
            .strip()
            .lower()
        )
        if (
            chunk is None
            or document is None
            or module is None
            or chunk.document_id != document.id
            or document.dataset_id != course.dataset_id
            or document.status != "ready"
            or module.course_id != course.id
            or (module_id is not None and module.id != module_id)
            or not document_is_student_visible(document, course)
            or document.id in assessment_document_ids
            or document_type
            not in {
                "course_description",
                "learning_objectives",
                "lecture_material",
                "reading",
                "reference",
                "resource",
            }
            or _normalized_quote(citation.quote) != expected_quote
        ):
            raise ValueError("learner citation is not currently authorized")
        seen_chunks.add(chunk.id)
        validated.append(
            citation.model_copy(
                update={
                    "document_title": document.title[:500],
                    "module_title": module.title[:500],
                    "quote": expected_quote,
                }
            ).model_dump()
        )
    return validated


def validate_learner_tool_result(
    db: Session,
    course: Course,
    result: LearnerToolResult,
    *,
    module_id: int | None,
) -> LearnerToolResult:
    if result.insufficient_context != (result.mode == "abstained"):
        raise ValueError("learner result mode is inconsistent")
    if result.mode in {"answer", "guidance", "self_check"} and not result.citations:
        raise ValueError("grounded learner result requires citations")
    if result.mode == "abstained" and result.citations:
        raise ValueError("abstention must not expose citations")
    citations = validate_learner_citations(
        db,
        course,
        [item.model_dump() for item in result.citations],
        module_id=module_id,
    )
    return result.model_copy(
        update={
            "citations": [
                LearnerToolCitation.model_validate(item) for item in citations
            ]
        }
    )


def revalidate_stored_learner_answer(
    db: Session,
    course: Course,
    answer: CourseQuestionAnswer,
    *,
    module_id: int | None = None,
) -> list[dict] | None:
    raw = answer.citations if isinstance(answer.citations, list) else []
    if answer.insufficient_context != (answer.response_mode == "abstained"):
        return None
    if answer.response_mode in {"answer", "guidance", "self_check"} and not raw:
        return None
    if answer.response_mode == "abstained" and raw:
        return None
    try:
        return validate_learner_citations(
            db,
            course,
            raw,
            module_id=module_id,
        )
    except (TypeError, ValueError):
        return None


def _deny() -> None:
    raise HTTPException(status_code=404, detail="resource not found")


def _exact_context(row: AgentRun, context: AgentTrustedContext) -> bool:
    return (
        row.organization_id == context.organization_id
        and row.course_id == context.course_id
        and row.user_id == context.user_id
        and row.role == context.role
        and row.product_session_id == context.product_session_id
    )


def _finish_run(
    db: Session,
    row: AgentRun,
    *,
    status: Literal["completed", "abstained"],
    label: str,
    recovery_action: str | None,
) -> AgentRun:
    row.status = status
    row.label = label
    row.recovery_action = recovery_action
    db.commit()
    db.refresh(row)
    return row


def _module_id_for_ref(
    db: Session, course: Course, module_ref: str | None
) -> int | None:
    if module_ref is None:
        return None
    course_map = build_course_map(db, course)
    matches = [
        module for module in course_map.modules if module.source_ref == module_ref
    ]
    if len(matches) != 1:
        _deny()
    return matches[0].id


def _source_for_refs(
    db: Session,
    course: Course,
    *,
    module_ref: str,
    source_ref: str,
) -> LearnerSourceResult:
    course_map = build_course_map(db, course)
    return _source_from_course_map(
        course_map,
        module_ref=module_ref,
        source_ref=source_ref,
    )


def _source_from_course_map(
    course_map,
    *,
    module_ref: str,
    source_ref: str,
) -> LearnerSourceResult:
    modules = [item for item in course_map.modules if item.source_ref == module_ref]
    if len(modules) != 1:
        _deny()
    items = [item for item in modules[0].items if item.source_ref == source_ref]
    if len(items) != 1:
        _deny()
    item = items[0]
    if (
        not item.available
        or item.destination_url is None
        or item.destination_provenance not in {"canvas", "external"}
    ):
        _deny()
    return LearnerSourceResult.model_validate(
        {
            "title": item.title,
            "destination_url": item.destination_url,
            "provenance": item.destination_provenance,
        }
    )


def resolve_source_action(db: Session, row: AgentRun) -> LearnerSourceResult:
    if (
        row.workflow != "learner.locate_source.v1"
        or row.status != "completed"
        or row.course_id is None
        or row.module_ref is None
        or row.selection_ref is None
    ):
        _deny()
    course = db.get(Course, row.course_id)
    if course is None or course.organization_id != row.organization_id:
        _deny()
    return _source_for_refs(
        db,
        course,
        module_ref=row.module_ref,
        source_ref=row.selection_ref,
    )


def evidence_source_for_citation(
    db: Session,
    course: Course,
    citation: dict,
) -> LearnerSourceResult | None:
    document = db.get(Document, citation.get("document_id"))
    if document is None:
        return None
    item = resolve_document_course_map_item(db, course, document)
    if item is None:
        return None
    return LearnerSourceResult.model_validate(
        {
            "title": item.title,
            "destination_url": item.destination_url,
            "provenance": item.destination_provenance,
        }
    )


def resolve_evidence_source(
    db: Session,
    row: AgentRun,
    candidate_ref: str,
) -> LearnerSourceResult:
    if row.answer_id is None or row.course_id is None:
        _deny()
    answer = db.get(CourseQuestionAnswer, row.answer_id)
    course = db.get(Course, row.course_id)
    if (
        answer is None
        or course is None
        or answer.course_id != course.id
        or course.organization_id != row.organization_id
    ):
        _deny()
    module_id = _module_id_for_ref(db, course, row.module_ref)
    citations = revalidate_stored_learner_answer(
        db,
        course,
        answer,
        module_id=module_id,
    )
    if citations is None:
        _deny()
    matches = [
        citation
        for citation in citations
        if evidence_ref(row, citation) == candidate_ref
    ]
    if len(matches) != 1:
        _deny()
    source = evidence_source_for_citation(db, course, matches[0])
    if source is None:
        _deny()
    return source


def create_learner_self_check(
    db: Session,
    course: Course,
    *,
    question: str,
    module_id: int | None,
    module_title: str,
    tutor_policy_version: int,
    tutor_answer_style: str,
    retrieved_context: tuple[list, str] | None = None,
) -> dict:
    query = f"{question} {module_title}".strip()
    hits, retrieval_method = retrieved_context or retrieve_student_tutor_context(
        db,
        course,
        query,
        module_id=module_id,
        top_k=3,
    )
    citations = [
        {
            "source_id": f"S{index}",
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "document_title": hit.document_title,
            "module_title": hit.module_title,
            "quote": hit.quote,
            "score": hit.score,
        }
        for index, hit in enumerate(hits[:3], start=1)
    ]
    if not citations:
        return {
            "content": "В выбранном разделе пока недостаточно опоры для самопроверки.",
            "mode": "abstained",
            "confidence": 0.0,
            "insufficient_context": True,
            "citations": [],
            "retrieval_method": retrieval_method,
            "generation_provider": "deterministic-self-check",
            "generation_model": None,
            "policy_reason": None,
            "tutor_policy_version": tutor_policy_version,
            "tutor_answer_style": tutor_answer_style,
        }
    prompts = (
        f"Сформулируйте своими словами главную мысль материала «{citations[0]['document_title']}».",
        f"Как найденная идея связана с темой раздела «{module_title}»?",
        "Приведите собственный пример и объясните, какую часть идеи он показывает.",
    )
    content = "Проверьте понимание без оценки и готовых ответов:\n\n" + "\n".join(
        f"{index}. {prompt}" for index, prompt in enumerate(prompts, start=1)
    )
    confidence = max(
        0.0, min(1.0, sum(item["score"] for item in citations) / len(citations))
    )
    return {
        "content": content,
        "mode": "self_check",
        "confidence": confidence,
        "insufficient_context": False,
        "citations": citations,
        "retrieval_method": retrieval_method,
        "generation_provider": "deterministic-self-check",
        "generation_model": None,
        "policy_reason": "formative_self_check",
        "tutor_policy_version": tutor_policy_version,
        "tutor_answer_style": tutor_answer_style,
    }


def execute_learner_run(
    db: Session,
    *,
    principal: Principal,
    run_id: int,
    question: str,
    module_ref: str | None,
    selection_ref: str | None = None,
) -> AgentRun:
    tool_input = LearnerToolInput(question=question, module_ref=module_ref)
    context = resolve_agent_context(db, principal)
    _configure_statement_timeout(
        db,
        max(tool.timeout_seconds for tool in TOOL_REGISTRY.values()),
    )
    row = (
        db.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().one_or_none()
    )
    if (
        row is None
        or context.role != "student"
        or not _exact_context(row, context)
        or row.workflow not in EXECUTABLE_LEARNER_WORKFLOWS
    ):
        _deny()
    if row.answer_id is not None or row.status in {"completed", "abstained", "failed"}:
        return row
    if row.status not in {"generating", "tool_running"}:
        raise HTTPException(status_code=409, detail="run is not ready to execute")
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()
    if row.workflow == "learner.locate_source.v1":
        if module_ref is None or selection_ref is None:
            _deny()
        source_input = LearnerSourceInput(
            module_ref=module_ref,
            source_ref=selection_ref,
        )
        course_map = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_current_course_map",
            tool_input=CurrentCourseMapIn(focus_ref=source_input.module_ref),
            call=lambda _deadline: build_course_map(db, course),
            output_projection=lambda value: CurrentCourseMapOut(
                modules=[module.source_ref for module in value.modules],
                destinations=[
                    item.source_ref
                    for module in value.modules
                    for item in module.items
                    if item.destination_url is not None
                ],
            ),
        )
        source = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="open_authoritative_source",
            tool_input=OpenAuthoritativeSourceIn(destination_ref=selection_ref),
            call=lambda _deadline: _source_from_course_map(
                course_map,
                module_ref=source_input.module_ref,
                source_ref=source_input.source_ref,
            ),
            output_projection=lambda value: OpenAuthoritativeSourceOut(
                destination_ref=source_input.source_ref,
                label=value.title,
            ),
        )
        LearnerSourceResult.model_validate(source)
        row.module_ref = source_input.module_ref
        row.selection_ref = source_input.source_ref
        return _finish_run(
            db,
            row,
            status="completed",
            label="Источник готов к открытию",
            recovery_action=None,
        )
    module_id = _module_id_for_ref(db, course, tool_input.module_ref)
    module_title = (
        db.get(CourseModule, module_id).title if module_id is not None else course.title
    )
    tutor_policy = get_effective_tutor_policy(db, course.id)
    if not tutor_policy.enabled:
        return _finish_run(
            db,
            row,
            status="abstained",
            label="Помощник курса сейчас приостановлен преподавателем",
            recovery_action="choose_supported_task",
        )
    ready_documents = (
        db.query(Document)
        .filter(Document.dataset_id == course.dataset_id, Document.status == "ready")
        .count()
    )
    if ready_documents == 0:
        return _finish_run(
            db,
            row,
            status="abstained",
            label="В курсе пока нет доступных материалов для ответа",
            recovery_action="choose_supported_task",
        )

    retrieval_query = (
        f"{tool_input.question} {module_title}".strip()
        if row.workflow == "learner.self_check.v1"
        else tool_input.question
    )
    retrieval_top_k = 3 if row.workflow == "learner.self_check.v1" else 5
    hits, retrieval_method = _run_validated_tool(
        db,
        row,
        principal,
        tool_name="retrieve_published_course_evidence",
        tool_input=RetrievePublishedEvidenceIn(
            query=retrieval_query,
            module_ref=tool_input.module_ref,
            top_k=retrieval_top_k,
        ),
        call=lambda deadline: retrieve_student_tutor_context(
            db,
            course,
            retrieval_query,
            module_id=module_id,
            top_k=retrieval_top_k,
            embedding_provider=_DeadlineHashingProvider(deadline),
            deadline_monotonic=deadline,
        ),
        output_projection=lambda value: RetrievePublishedEvidenceOut(
            evidence_refs=[f"chunk:{hit.chunk_id}" for hit in value[0]],
            excerpts=[hit.quote for hit in value[0]],
            confidence=(
                sum(hit.score for hit in value[0]) / len(value[0]) if value[0] else 0.0
            ),
        ),
    )
    evidence_refs = [f"chunk:{hit.chunk_id}" for hit in hits]

    def build_result(_deadline_monotonic: float) -> LearnerToolResult:
        if row.workflow == "learner.self_check.v1":
            payload = create_learner_self_check(
                db,
                course,
                question=tool_input.question,
                module_id=module_id,
                module_title=module_title,
                tutor_policy_version=tutor_policy.version,
                tutor_answer_style=tutor_policy.answer_style,
                retrieved_context=(hits, retrieval_method),
            )
        else:
            generated = answer_course_question(
                db,
                course,
                tool_input.question,
                top_k=retrieval_top_k,
                language="ru",
                module_id=module_id,
                answer_style=tutor_policy.answer_style,
                tutor_policy_version=tutor_policy.version,
                force_guidance=row.workflow == "learner.assessment_safe_hint.v1",
                allow_generative=False,
                require_grounded_guidance=True,
                retrieved_context=(hits, retrieval_method),
            )
            payload = {
                "content": generated.answer,
                "mode": generated.response_mode,
                "confidence": generated.confidence,
                "insufficient_context": generated.insufficient_context,
                "citations": [
                    {
                        "source_id": item.source_id,
                        "chunk_id": item.chunk_id,
                        "document_id": item.document_id,
                        "document_title": item.document_title,
                        "module_title": item.module_title,
                        "quote": item.quote,
                        "score": item.score,
                    }
                    for item in generated.citations
                ],
                "retrieval_method": generated.retrieval_method,
                "generation_provider": generated.generation_provider,
                "generation_model": generated.generation_model,
                "policy_reason": generated.policy_reason,
                "tutor_policy_version": generated.tutor_policy_version,
                "tutor_answer_style": generated.tutor_answer_style,
            }
        return validate_learner_tool_result(
            db,
            course,
            LearnerToolResult.model_validate(payload),
            module_id=module_id,
        )

    if row.workflow == "learner.self_check.v1":
        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="create_self_check",
            tool_input=CreateSelfCheckIn(
                topic=tool_input.question,
                evidence_refs=evidence_refs,
                item_count=3,
            ),
            call=build_result,
            output_projection=lambda value: CreateSelfCheckOut(
                items=[
                    line.split(". ", 1)[1]
                    for line in value.content.splitlines()
                    if re.match(r"^[1-3]\. ", line)
                ],
                feedback_policy="formative_no_answers",
                citations=[item.source_id for item in value.citations],
            ),
        )
    elif row.workflow == "learner.assessment_safe_hint.v1":
        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="give_assessment_safe_hint",
            tool_input=ExplainWithCitationsIn(
                question=tool_input.question,
                evidence_refs=evidence_refs,
            ),
            call=build_result,
            output_projection=lambda value: AssessmentSafeHintOut(
                mode=value.mode,
                guidance=value.content,
                citations=[item.source_id for item in value.citations],
                confidence=value.confidence,
                abstained=value.insufficient_context,
            ),
        )
    else:
        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="explain_with_citations",
            tool_input=ExplainWithCitationsIn(
                question=tool_input.question,
                evidence_refs=evidence_refs,
            ),
            call=build_result,
            output_projection=lambda value: ExplainWithCitationsOut(
                content=value.content,
                citations=[item.source_id for item in value.citations],
                confidence=value.confidence,
                abstained=value.insufficient_context,
            ),
        )
    current = resolve_agent_context(db, principal)
    if not _exact_context(row, current):
        _deny()
    answer = CourseQuestionAnswer(
        course_id=course.id,
        asked_by_user_id=context.user_id,
        question=tool_input.question,
        answer=result.content,
        citations=[item.model_dump() for item in result.citations],
        confidence=result.confidence,
        retrieval_method=result.retrieval_method,
        generation_provider=result.generation_provider,
        generation_model=result.generation_model,
        insufficient_context=result.insufficient_context,
        response_mode=result.mode,
        policy_reason=result.policy_reason,
        tutor_policy_version=result.tutor_policy_version,
        tutor_answer_style=result.tutor_answer_style,
    )
    db.add(answer)
    db.flush()
    row.answer_id = answer.id
    terminal_status = "abstained" if result.insufficient_context else "completed"
    terminal_label = (
        "В материалах курса недостаточно информации"
        if result.insufficient_context
        else (
            "Самопроверка готова"
            if result.mode == "self_check"
            else (
                "Подсказка готова" if result.mode == "guidance" else "Объяснение готово"
            )
        )
    )
    return _finish_run(
        db,
        row,
        status=terminal_status,
        label=terminal_label,
        recovery_action=(
            "choose_supported_task" if result.insufficient_context else None
        ),
    )


def evidence_ref(run: AgentRun, citation: dict) -> str:
    raw = ":".join(
        (
            run.public_id,
            str(run.answer_id or 0),
            str(citation.get("chunk_id") or 0),
            str(citation.get("document_id") or 0),
        )
    )
    digest = hmac.new(
        run.idempotency_digest.encode("ascii"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return f"ev_{digest}"


__all__ = [
    "EXECUTABLE_LEARNER_WORKFLOWS",
    "LearnerToolInput",
    "LearnerToolResult",
    "create_learner_self_check",
    "evidence_source_for_citation",
    "evidence_ref",
    "execute_learner_run",
    "revalidate_stored_learner_answer",
    "resolve_evidence_source",
    "resolve_source_action",
    "validate_learner_citations",
    "validate_learner_tool_result",
]
