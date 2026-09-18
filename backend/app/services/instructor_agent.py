from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseInterventionDraft,
    FindingReviewEvent,
)
from ..schemas.canvas_changes import CanvasChangeItemOut, CanvasChangeSetOut
from ..schemas.teacher_workspace import AttentionFindingOut, TeacherWorkspaceOut
from .agent_policy import TOOL_REGISTRY
from .agent_run import AgentTrustedContext, resolve_agent_context
from .authorization import Principal
from .canvas_change_set import build_canvas_change_set
from .course_copilot import (
    create_copilot_suggestion,
    validate_copilot_suggestion_citations,
)
from .learner_agent import _configure_statement_timeout, _run_validated_tool
from .learning_gap_aggregation import (
    LearningGapCandidate,
    aggregate_learning_gaps,
    create_intervention_draft,
    review_intervention_draft,
    validate_intervention_evidence,
)
from .teacher_workspace import build_teacher_workspace

EXECUTABLE_INSTRUCTOR_WORKFLOWS = frozenset(
    {
        "instructor.course_summary.v1",
        "instructor.inspect_audit.v1",
        "instructor.inspect_question_gaps.v1",
        "instructor.draft_improvement.v1",
        "instructor.preview_canvas_change.v1",
    }
)


class TeacherCourseSummaryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: Literal["current_course"]


class TeacherCourseSummaryToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priorities: list[str] = Field(max_length=3)
    evidence: list[str] = Field(max_length=8)
    aggregate_signals: list[str] = Field(max_length=8)


class OpenCourseAuditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_ref: Literal["current"]
    refresh: Literal[False]


class OpenCourseAuditToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_ref: str = Field(min_length=1, max_length=64)
    status: Literal["missing", "queued", "running", "done", "failed"]
    findings: list[str] = Field(max_length=3)


class InspectFindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ref: str = Field(min_length=40, max_length=40)


class InspectFindingToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    history: list[str] = Field(max_length=12)


class InspectQuestionGapsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: Literal[30]


class InspectQuestionGapsToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[str] = Field(max_length=3)
    cohort_size: list[str] = Field(max_length=3)
    limitations: list[str] = Field(max_length=4)


class DraftImprovementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ref: str = Field(min_length=40, max_length=40)
    instruction: Literal["prepare_reviewable_draft"]


class DraftImprovementToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_ref: str = Field(min_length=38, max_length=38)
    content: str = Field(min_length=10, max_length=6000)
    citations: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(max_length=4)


class PreviewCanvasChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_ref: str = Field(min_length=38, max_length=38)


class PreviewCanvasChangeToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_set_ref: str = Field(min_length=39, max_length=39)
    operations: list[str] = Field(max_length=1)
    warnings: list[str] = Field(max_length=4)


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


def instructor_finding_ref(row: AgentRun, finding_id: int) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:{finding_id}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"finding_{digest}"


def instructor_audit_ref(row: AgentRun, audit_id: int) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:audit:{audit_id}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"audit_{digest}"


def instructor_draft_ref(row: AgentRun, suggestion_id: int) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:draft:{suggestion_id}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"draft_{digest}"


def instructor_gap_ref(row: AgentRun, candidate: LearningGapCandidate) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:gap:{candidate.aggregate_digest}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"gap_{digest}"


def instructor_intervention_ref(row: AgentRun, draft_id: int) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:intervention:{draft_id}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"intervention_{digest}"


def instructor_change_set_ref(row: AgentRun, suggestion_id: int) -> str:
    raw = f"{row.public_id}:{row.course_id or 0}:change:{suggestion_id}"
    digest = hmac.new(
        row.idempotency_digest.encode("ascii"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"change_{digest}"


def _current_question_gaps(
    db: Session,
    course: Course,
) -> list[LearningGapCandidate]:
    timeout_seconds = TOOL_REGISTRY["inspect_aggregate_question_gaps"].timeout_seconds
    deadline = time.monotonic() + timeout_seconds
    _configure_statement_timeout(db, timeout_seconds)
    return aggregate_learning_gaps(
        db,
        course,
        deadline_monotonic=deadline,
    )


def project_instructor_course_summary(
    db: Session,
    row: AgentRun,
) -> tuple[TeacherWorkspaceOut, list[dict]]:
    if row.role != "instructor" or row.course_id is None:
        _deny()
    course = db.get(Course, row.course_id)
    if course is None:
        _deny()
    workspace = build_teacher_workspace(db, course)
    priorities = [
        {
            "finding_ref": instructor_finding_ref(row, finding.id),
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
            "confidence": finding.confidence,
            "confidence_label": finding.confidence_label,
            "evidence_count": len(finding.evidence),
        }
        for finding in workspace.findings[:3]
    ]
    return workspace, priorities


def resolve_instructor_finding(
    db: Session,
    row: AgentRun,
) -> tuple[TeacherWorkspaceOut, AttentionFindingOut, AgentRun]:
    if row.role != "instructor" or row.course_id is None or not row.selection_ref:
        _deny()
    course = db.get(Course, row.course_id)
    if course is None:
        _deny()
    workspace = build_teacher_workspace(db, course)
    if workspace.latest_audit is None or workspace.latest_audit.status != "done":
        _deny()
    issuers = (
        db.query(AgentRun)
        .filter(
            AgentRun.organization_id == row.organization_id,
            AgentRun.course_id == row.course_id,
            AgentRun.user_id == row.user_id,
            AgentRun.role == row.role,
            AgentRun.product_session_id == row.product_session_id,
            AgentRun.workflow == "instructor.course_summary.v1",
            AgentRun.status == "completed",
        )
        .order_by(AgentRun.id.desc())
        .limit(20)
        .all()
    )
    for issuer in issuers:
        for finding in workspace.findings:
            candidate = instructor_finding_ref(issuer, finding.id)
            if hmac.compare_digest(candidate, row.selection_ref):
                return workspace, finding, issuer
    _deny()


def project_instructor_question_gaps(
    db: Session,
    row: AgentRun,
) -> tuple[Course, list[tuple[str, LearningGapCandidate]]]:
    if row.role != "instructor" or row.course_id is None:
        _deny()
    course = db.get(Course, row.course_id)
    if course is None:
        _deny()
    candidates = _current_question_gaps(db, course)
    return course, [
        (instructor_gap_ref(row, candidate), candidate) for candidate in candidates
    ]


def resolve_instructor_gap_ref(
    db: Session,
    context: AgentTrustedContext,
    gap_ref: str,
) -> tuple[LearningGapCandidate, AgentRun]:
    if context.role != "instructor" or context.course_id is None:
        _deny()
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()
    issuers = (
        db.query(AgentRun)
        .filter(
            AgentRun.organization_id == context.organization_id,
            AgentRun.course_id == context.course_id,
            AgentRun.user_id == context.user_id,
            AgentRun.role == context.role,
            AgentRun.product_session_id == context.product_session_id,
            AgentRun.workflow == "instructor.inspect_question_gaps.v1",
            AgentRun.status == "completed",
        )
        .order_by(AgentRun.id.desc())
        .limit(20)
        .all()
    )
    candidates = _current_question_gaps(db, course)
    for issuer in issuers:
        for candidate in candidates:
            if hmac.compare_digest(instructor_gap_ref(issuer, candidate), gap_ref):
                return candidate, issuer
    _deny()


def create_instructor_intervention(
    db: Session,
    *,
    principal: Principal,
    gap_ref: str,
) -> tuple[CourseInterventionDraft, AgentRun]:
    context = resolve_agent_context(db, principal)
    candidate, issuer = resolve_instructor_gap_ref(db, context, gap_ref)
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()
    draft = create_intervention_draft(db, course, candidate)
    db.commit()
    db.refresh(draft)
    return draft, issuer


def resolve_instructor_intervention_ref(
    db: Session,
    context: AgentTrustedContext,
    intervention_ref: str,
    *,
    for_update: bool = False,
) -> tuple[CourseInterventionDraft, AgentRun]:
    if context.role != "instructor" or context.course_id is None:
        _deny()
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()
    issuers = (
        db.query(AgentRun)
        .filter(
            AgentRun.organization_id == context.organization_id,
            AgentRun.course_id == context.course_id,
            AgentRun.user_id == context.user_id,
            AgentRun.role == context.role,
            AgentRun.product_session_id == context.product_session_id,
            AgentRun.workflow == "instructor.inspect_question_gaps.v1",
            AgentRun.status == "completed",
        )
        .order_by(AgentRun.id.desc())
        .limit(20)
        .all()
    )
    query = (
        db.query(CourseInterventionDraft)
        .populate_existing()
        .filter(CourseInterventionDraft.course_id == context.course_id)
        .order_by(CourseInterventionDraft.id.desc())
        .limit(50)
    )
    if for_update:
        query = query.with_for_update()
    drafts = query.all()
    current_candidates = _current_question_gaps(db, course)
    for draft in drafts:
        issuer = next(
            (
                item
                for item in issuers
                if hmac.compare_digest(
                    instructor_intervention_ref(item, draft.id),
                    intervention_ref,
                )
            ),
            None,
        )
        if issuer is None:
            continue
        threshold_still_met = any(
            hmac.compare_digest(candidate.aggregate_digest, draft.aggregate_digest)
            and candidate.document_id == draft.source_document_id
            and candidate.chunk_id == draft.source_chunk_id
            and candidate.signal_kind == draft.signal_kind
            and candidate.cohort_band == draft.cohort_band
            and candidate.event_band == draft.event_band
            for candidate in current_candidates
        )
        if (
            not threshold_still_met
            or validate_intervention_evidence(db, course, draft) is None
        ):
            _deny()
        return draft, issuer
    _deny()


def review_instructor_intervention(
    db: Session,
    *,
    principal: Principal,
    intervention_ref: str,
    expected_version: int,
    status: Literal["accepted", "rejected"],
    content: str | None,
) -> CourseInterventionDraft:
    context = resolve_agent_context(db, principal)
    draft, _ = resolve_instructor_intervention_ref(
        db,
        context,
        intervention_ref,
        for_update=True,
    )
    if draft.version != expected_version or draft.status != "draft":
        raise HTTPException(status_code=409, detail="intervention review state changed")
    if context.user_id is None:
        _deny()
    review_intervention_draft(
        db,
        draft,
        reviewer_user_id=context.user_id,
        status=status,
        content=content,
    )
    db.commit()
    db.refresh(draft)
    return draft


def resolve_instructor_draft(
    db: Session,
    row: AgentRun,
) -> CourseCopilotSuggestion:
    if row.role != "instructor" or row.course_id is None or not row.selection_ref:
        _deny()
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    return resolve_instructor_draft_ref(db, context, row.selection_ref)


def resolve_instructor_draft_ref(
    db: Session,
    context: AgentTrustedContext,
    draft_ref: str,
    *,
    for_update: bool = False,
) -> CourseCopilotSuggestion:
    if context.role != "instructor" or context.course_id is None:
        _deny()
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()
    issuers = (
        db.query(AgentRun)
        .filter(
            AgentRun.organization_id == context.organization_id,
            AgentRun.course_id == context.course_id,
            AgentRun.user_id == context.user_id,
            AgentRun.role == context.role,
            AgentRun.product_session_id == context.product_session_id,
            AgentRun.workflow == "instructor.draft_improvement.v1",
            AgentRun.status == "completed",
            AgentRun.selection_ref == draft_ref,
        )
        .order_by(AgentRun.id.desc())
        .limit(20)
        .all()
    )
    suggestions_query = (
        db.query(CourseCopilotSuggestion)
        .filter(CourseCopilotSuggestion.course_id == context.course_id)
        .order_by(CourseCopilotSuggestion.id.desc())
        .limit(50)
    )
    if for_update:
        suggestions_query = suggestions_query.with_for_update()
    suggestions = suggestions_query.all()
    for suggestion in suggestions:
        issuer = next(
            (
                candidate
                for candidate in issuers
                if hmac.compare_digest(
                    instructor_draft_ref(candidate, suggestion.id),
                    draft_ref,
                )
            ),
            None,
        )
        if issuer is None:
            continue
        finding = db.get(CourseFinding, suggestion.finding_id)
        workspace = build_teacher_workspace(db, course)
        if (
            finding is None
            or finding.course_id != context.course_id
            or finding.status != "confirmed"
            or workspace.latest_audit is None
            or workspace.latest_audit.status != "done"
            or finding.audit_run_id != workspace.latest_audit.id
            or suggestion.audit_run_id != workspace.latest_audit.id
            or validate_copilot_suggestion_citations(db, course, suggestion) is None
        ):
            _deny()
        return suggestion
    _deny()


def review_instructor_draft(
    db: Session,
    *,
    principal: Principal,
    draft_ref: str,
    expected_version: int,
    status: Literal["accepted", "rejected"],
    content: str | None,
) -> CourseCopilotSuggestion:
    context = resolve_agent_context(db, principal)
    suggestion = resolve_instructor_draft_ref(
        db,
        context,
        draft_ref,
        for_update=True,
    )
    if suggestion.version != expected_version or suggestion.status != "draft":
        raise HTTPException(status_code=409, detail="draft review state changed")
    finding = (
        db.query(CourseFinding)
        .populate_existing()
        .filter(
            CourseFinding.id == suggestion.finding_id,
            CourseFinding.course_id == context.course_id,
            CourseFinding.audit_run_id == suggestion.audit_run_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if finding is None or finding.status != "confirmed":
        raise HTTPException(status_code=409, detail="finding review state changed")
    if status == "accepted" and suggestion.insufficient_context:
        raise HTTPException(
            status_code=409, detail="draft requires more course evidence"
        )
    if status == "accepted" and content is not None:
        suggestion.draft = content
    now = datetime.now(timezone.utc)
    if status == "accepted":
        previous = (
            db.query(CourseCopilotSuggestion)
            .filter(
                CourseCopilotSuggestion.finding_id == suggestion.finding_id,
                CourseCopilotSuggestion.id != suggestion.id,
                CourseCopilotSuggestion.status == "accepted",
            )
            .with_for_update()
            .all()
        )
        for item in previous:
            item.status = "rejected"
            item.version += 1
            item.review_reason = "superseded"
            item.reviewed_by = principal.email
            item.reviewed_at = now
    suggestion.status = status
    suggestion.version += 1
    suggestion.review_reason = (
        "teacher_accepted" if status == "accepted" else "teacher_rejected"
    )
    suggestion.reviewed_by = principal.email
    suggestion.reviewed_at = now
    db.commit()
    db.refresh(suggestion)
    return suggestion


def preview_instructor_canvas_change(
    db: Session,
    row: AgentRun,
) -> tuple[CourseCopilotSuggestion, CanvasChangeSetOut, CanvasChangeItemOut]:
    suggestion = resolve_instructor_draft(db, row)
    if suggestion.status != "accepted":
        _deny()
    course = db.get(Course, row.course_id)
    if course is None:
        _deny()
    change_set = build_canvas_change_set(db, course)
    item = next(
        (
            candidate
            for candidate in change_set.items
            if candidate.suggestion_id == suggestion.id
        ),
        None,
    )
    if item is None:
        _deny()
    return suggestion, change_set, item


def execute_instructor_run(
    db: Session,
    *,
    principal: Principal,
    run_id: int,
) -> AgentRun:
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
        or context.role != "instructor"
        or not _exact_context(row, context)
        or row.workflow not in EXECUTABLE_INSTRUCTOR_WORKFLOWS
    ):
        _deny()
    if row.status in {"completed", "abstained", "failed"}:
        return row
    if row.status != "tool_running":
        raise HTTPException(status_code=409, detail="run is not ready to execute")
    course = db.get(Course, context.course_id)
    if course is None:
        _deny()

    if row.workflow == "instructor.course_summary.v1":
        workspace = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="get_teacher_course_summary",
            tool_input=TeacherCourseSummaryIn(focus="current_course"),
            call=lambda _deadline: build_teacher_workspace(db, course),
            output_projection=lambda value: TeacherCourseSummaryToolOut(
                priorities=[item.title for item in value.findings[:3]],
                evidence=[
                    evidence.quote
                    for item in value.findings[:3]
                    for evidence in item.evidence[:2]
                ][:8],
                aggregate_signals=[
                    f"audit:{value.latest_audit.status if value.latest_audit else 'missing'}",
                    f"findings:{value.health.findings_total}",
                    f"high:{value.health.high_severity_findings}",
                    f"tutor:{value.tutor_quality.signal}",
                ],
            ),
        )
        if not isinstance(workspace, TeacherWorkspaceOut):
            raise ValueError("teacher workspace result is invalid")
    elif row.workflow == "instructor.inspect_audit.v1":
        workspace = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="run_or_open_course_audit",
            tool_input=OpenCourseAuditIn(audit_ref="current", refresh=False),
            call=lambda _deadline: build_teacher_workspace(db, course),
            output_projection=lambda value: OpenCourseAuditToolOut(
                audit_ref=(
                    instructor_audit_ref(row, value.latest_audit.id)
                    if value.latest_audit
                    else "audit_missing"
                ),
                status=(
                    value.latest_audit.status
                    if value.latest_audit
                    and value.latest_audit.status
                    in {"queued", "running", "done", "failed"}
                    else "missing"
                ),
                findings=[item.title for item in value.findings[:3]],
            ),
        )
        finding_result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="inspect_finding_evidence",
            tool_input=InspectFindingIn(finding_ref=row.selection_ref or ""),
            call=lambda _deadline: resolve_instructor_finding(db, row),
            output_projection=lambda value: InspectFindingToolOut(
                finding=value[1].title,
                evidence=[item.quote for item in value[1].evidence[:5]],
                confidence=value[1].confidence,
                history=[
                    f"{event.from_status}->{event.to_status}"
                    for event in db.query(FindingReviewEvent)
                    .filter(FindingReviewEvent.finding_id == value[1].id)
                    .order_by(FindingReviewEvent.id.desc())
                    .limit(12)
                    .all()
                ],
            ),
        )
        if (
            not isinstance(workspace, TeacherWorkspaceOut)
            or not isinstance(finding_result, tuple)
            or len(finding_result) != 3
        ):
            raise ValueError("teacher finding result is invalid")
    elif row.workflow == "instructor.inspect_question_gaps.v1":
        candidates = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="inspect_aggregate_question_gaps",
            tool_input=InspectQuestionGapsIn(window_days=30),
            call=lambda deadline: aggregate_learning_gaps(
                db,
                course,
                deadline_monotonic=deadline,
            ),
            output_projection=lambda value: InspectQuestionGapsToolOut(
                topics=[item.topic_label for item in value[:3]],
                cohort_size=[item.cohort_band for item in value[:3]],
                limitations=[
                    "Только группы не менее трёх активных учеников.",
                    "Вопросы, ответы и личности не входят в результат.",
                ],
            ),
        )
        if not isinstance(candidates, list):
            raise ValueError("aggregate question gaps result is invalid")
    elif row.workflow == "instructor.draft_improvement.v1":
        finding_ref = row.selection_ref or ""
        finding_result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="inspect_finding_evidence",
            tool_input=InspectFindingIn(finding_ref=finding_ref),
            call=lambda _deadline: resolve_instructor_finding(db, row),
            output_projection=lambda value: InspectFindingToolOut(
                finding=value[1].title,
                evidence=[item.quote for item in value[1].evidence[:5]],
                confidence=value[1].confidence,
                history=[
                    f"{event.from_status}->{event.to_status}"
                    for event in db.query(FindingReviewEvent)
                    .filter(FindingReviewEvent.finding_id == value[1].id)
                    .order_by(FindingReviewEvent.id.desc())
                    .limit(12)
                    .all()
                ],
            ),
        )
        workspace, finding, _ = finding_result
        finding_row = db.get(CourseFinding, finding.id)
        if finding_row is None:
            _deny()
        suggestion = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="draft_course_improvement",
            tool_input=DraftImprovementIn(
                finding_ref=finding_ref,
                instruction="prepare_reviewable_draft",
            ),
            call=lambda deadline: create_copilot_suggestion(
                db,
                finding_row,
                top_k=5,
                language="ru",
                deadline_monotonic=deadline,
            ),
            output_projection=lambda value: DraftImprovementToolOut(
                draft_ref=instructor_draft_ref(row, value.id),
                content=value.draft,
                citations=[
                    str(item.get("quote") or "")[:800]
                    for item in (value.citations or [])[:8]
                    if str(item.get("quote") or "").strip()
                ],
                confidence=value.confidence,
                limitations=(
                    ["Недостаточно подтверждающих материалов для принятия черновика."]
                    if value.insufficient_context
                    else [
                        "Черновик требует проверки и отдельного решения преподавателя.",
                        "Создание черновика не изменяет Canvas.",
                    ]
                ),
            ),
        )
        if suggestion.id is None:
            raise ValueError("draft was not persisted")
        row.selection_ref = instructor_draft_ref(row, suggestion.id)
    else:
        preview = _run_validated_tool(
            db,
            row,
            principal,
            tool_name="preview_canvas_change_set",
            tool_input=PreviewCanvasChangeIn(
                suggestion_ref=row.selection_ref or "",
            ),
            call=lambda _deadline: preview_instructor_canvas_change(db, row),
            output_projection=lambda value: PreviewCanvasChangeToolOut(
                change_set_ref=instructor_change_set_ref(row, value[0].id),
                operations=[f"{value[2].api_method} {value[2].api_path}"],
                warnings=[
                    warning
                    for warning in [value[2].warning, *value[1].warnings]
                    if warning
                ][:4],
            ),
        )
        if not isinstance(preview, tuple) or len(preview) != 3:
            raise ValueError("Canvas change preview is invalid")
    current = resolve_agent_context(db, principal)
    if not _exact_context(row, current):
        _deny()
    row.status = "completed"
    row.label = (
        "Доказательства приоритета готовы к проверке"
        if row.workflow == "instructor.inspect_audit.v1"
        else (
            (
                "Повторяющиеся трудности готовы к проверке"
                if candidates
                else "Недостаточно обезличенных данных для общего сигнала"
            )
            if row.workflow == "instructor.inspect_question_gaps.v1"
            else (
                "Черновик готов к проверке преподавателем"
                if row.workflow == "instructor.draft_improvement.v1"
                else (
                    "Изменение Canvas готово к предпросмотру"
                    if row.workflow == "instructor.preview_canvas_change.v1"
                    else (
                        "Приоритеты курса готовы к проверке"
                        if workspace.findings
                        else "Сводка курса готова — срочных наблюдений нет"
                    )
                )
            )
        )
    )
    row.recovery_action = None
    db.commit()
    db.refresh(row)
    return row


__all__ = [
    "EXECUTABLE_INSTRUCTOR_WORKFLOWS",
    "execute_instructor_run",
    "instructor_audit_ref",
    "instructor_change_set_ref",
    "instructor_draft_ref",
    "instructor_finding_ref",
    "instructor_gap_ref",
    "instructor_intervention_ref",
    "preview_instructor_canvas_change",
    "project_instructor_question_gaps",
    "project_instructor_course_summary",
    "resolve_instructor_draft",
    "resolve_instructor_draft_ref",
    "resolve_instructor_finding",
    "resolve_instructor_gap_ref",
    "resolve_instructor_intervention_ref",
    "review_instructor_draft",
    "create_instructor_intervention",
    "review_instructor_intervention",
]
