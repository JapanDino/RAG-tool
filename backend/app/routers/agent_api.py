from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Any, Callable, Coroutine

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    AgentRun,
    AgentToolEvent,
    Course,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
)
from ..schemas.agent_api import (
    AgentAcceptedOut,
    AgentAdminOrganizationOut,
    AgentConfidenceOut,
    AgentEventOut,
    AgentEventsOut,
    AgentEvidenceOut,
    AgentFeedbackIn,
    AgentFeedbackOut,
    AgentInstructorCanvasChangeOut,
    AgentInstructorCourseSummaryOut,
    AgentInstructorDraftOut,
    AgentInstructorDraftReviewIn,
    AgentInstructorDraftReviewOut,
    AgentInstructorEvidenceOut,
    AgentInstructorFindingOut,
    AgentInstructorGapOut,
    AgentInstructorHealthOut,
    AgentInstructorInterventionDraftOut,
    AgentInstructorInterventionReviewIn,
    AgentInstructorInterventionReviewOut,
    AgentInstructorPriorityOut,
    AgentInstructorQuestionGapsOut,
    AgentLearnerResponseOut,
    AgentMessageIn,
    AgentProgramOptionsOut,
    AgentRunOut,
    AgentSourceActionOut,
    AgentUserStateOut,
    AgentWorkflowPlanOut,
)
from ..services.admin_agent import (
    EXECUTABLE_ADMIN_WORKFLOWS,
    admin_organization_option,
    execute_admin_run,
    project_admin_analytics_brief,
    project_admin_operations_brief,
    project_admin_policy_status,
)
from ..services.agent_run import (
    CONTRACT_VERSION,
    create_or_replay_agent_run,
    event_replay_available,
    owned_agent_run,
    planned_step_count,
    resolve_agent_context,
    validate_agent_run_input,
)
from ..services.authorization import Principal, get_current_principal
from ..services.course_copilot import validate_copilot_suggestion_citations
from ..services.course_map import build_course_map
from ..services.instructor_agent import (
    EXECUTABLE_INSTRUCTOR_WORKFLOWS,
    create_instructor_intervention,
    execute_instructor_run,
    instructor_change_set_ref,
    instructor_intervention_ref,
    preview_instructor_canvas_change,
    project_instructor_course_summary,
    project_instructor_question_gaps,
    resolve_instructor_draft,
    resolve_instructor_finding,
    review_instructor_draft,
    review_instructor_intervention,
)
from ..services.learner_agent import (
    EXECUTABLE_LEARNER_WORKFLOWS,
    LearnerToolAuditSnapshot,
    evidence_ref,
    evidence_source_for_citation,
    execute_learner_run,
    learner_tool_audit_snapshots,
    resolve_evidence_source,
    resolve_source_action,
    revalidate_stored_learner_answer,
)
from ..services.organization_agent_policy import (
    AgentPolicyScopeDenied,
    lock_and_assert_agent_workflow_enabled,
)
from ..services.program_agent import (
    EXECUTABLE_PROGRAM_WORKFLOWS,
    execute_program_run,
    list_program_options,
    project_program_evidence_route,
    project_program_review_draft,
    project_program_route_brief,
)

AGENT_REQUEST_BODY_MAX_BYTES = 24 * 1024


def _error_response(status_code: int, code: str) -> JSONResponse:
    copy = {
        "INVALID_REQUEST": (
            "Запрос не удалось проверить.",
            False,
            "check_request",
        ),
        "AUTHENTICATION_REQUIRED": (
            "Откройте помощника из Canvas или выберите локального пользователя.",
            False,
            "relaunch_from_canvas",
        ),
        "SESSION_EXPIRED": (
            "Сессия курса завершилась. Откройте помощника снова из Canvas.",
            False,
            "relaunch_from_canvas",
        ),
        "CSRF_INVALID": (
            "Запрос сессии не удалось подтвердить.",
            False,
            "refresh_session",
        ),
        "ACCESS_DENIED": (
            "Запрашиваемый ресурс недоступен.",
            False,
            "return_to_canvas",
        ),
        "RESOURCE_UNAVAILABLE": (
            "История событий для этого запроса больше недоступна.",
            False,
            "refresh_run",
        ),
        "CONFLICT": (
            "Запрос конфликтует с текущим состоянием.",
            False,
            "refresh_session",
        ),
        "BUDGET_EXCEEDED": (
            "Запрос слишком велик для одного шага помощника.",
            False,
            "check_request",
        ),
        "TEMPORARY_FAILURE": (
            "Сервис временно недоступен.",
            True,
            "retry_later",
        ),
    }
    message, retryable, recovery_action = copy[code]
    return JSONResponse(
        status_code=status_code,
        content={
            "contract_version": CONTRACT_VERSION,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "recovery_action": recovery_action,
                "request_id": f"req_{secrets.token_urlsafe(12)}",
            },
        },
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


class AgentContractRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                if request.method in {"POST", "PUT", "PATCH"}:
                    content_length = request.headers.get("content-length")
                    if content_length is not None:
                        try:
                            if int(content_length) > AGENT_REQUEST_BODY_MAX_BYTES:
                                return _error_response(400, "INVALID_REQUEST")
                        except ValueError:
                            return _error_response(400, "INVALID_REQUEST")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in request.stream():
                        total += len(chunk)
                        if total > AGENT_REQUEST_BODY_MAX_BYTES:
                            return _error_response(400, "INVALID_REQUEST")
                        chunks.append(chunk)
                    request._body = b"".join(chunks)
                return await original(request)
            except RequestValidationError:
                return _error_response(400, "INVALID_REQUEST")
            except HTTPException as exc:
                detail_code = (
                    exc.detail.get("code") if isinstance(exc.detail, dict) else None
                )
                if exc.status_code == 403 and detail_code == "csrf_invalid":
                    return _error_response(403, "CSRF_INVALID")
                if exc.status_code == 401:
                    code = (
                        "SESSION_EXPIRED"
                        if detail_code == "session_required"
                        else "AUTHENTICATION_REQUIRED"
                    )
                    return _error_response(401, code)
                if exc.status_code == 404:
                    if detail_code == "event_replay_expired":
                        return _error_response(404, "RESOURCE_UNAVAILABLE")
                    return _error_response(404, "ACCESS_DENIED")
                if exc.status_code == 409:
                    return _error_response(409, "CONFLICT")
                if exc.status_code == 429:
                    return _error_response(429, "BUDGET_EXCEEDED")
                if exc.status_code == 400:
                    return _error_response(400, "INVALID_REQUEST")
                return _error_response(503, "TEMPORARY_FAILURE")
            except Exception:
                return _error_response(503, "TEMPORARY_FAILURE")

        return route_handler


router = APIRouter(
    prefix="/agent/v1",
    tags=["agent"],
    route_class=AgentContractRoute,
)


def _persist_execution_terminal(
    db: Session,
    *,
    run_id: int,
    status: str,
    label: str,
    tool_audits: tuple[LearnerToolAuditSnapshot, ...] = (),
) -> None:
    """Persist a safe terminal state without discarding flushed tool audits."""

    def apply_terminal(current: AgentRun | None) -> None:
        if current is None or current.status not in {"generating", "tool_running"}:
            return
        for tool_audit in tool_audits:
            exists = (
                db.query(AgentToolEvent.id)
                .filter(
                    AgentToolEvent.agent_run_id == current.id,
                    AgentToolEvent.tool_name == tool_audit.tool_name,
                )
                .first()
            )
            if exists is None:
                db.add(
                    AgentToolEvent(
                        agent_run_id=current.id,
                        tool_name=tool_audit.tool_name,
                        status=tool_audit.status,
                        latency_ms=max(0, tool_audit.latency_ms),
                        failure_class=tool_audit.failure_class,
                    )
                )
        current.status = status
        current.label = label
        current.recovery_action = "choose_supported_task"

    try:
        current = db.get(AgentRun, run_id)
        apply_terminal(current)
        db.commit()
    except SQLAlchemyError:
        # Only a failed SQL transaction requires rollback. Ordinary tool and
        # policy failures keep their content-free audit events atomically.
        db.rollback()
        current = (
            db.query(AgentRun)
            .filter(AgentRun.id == run_id)
            .with_for_update()
            .one_or_none()
        )
        apply_terminal(current)
        db.commit()


AgentRunId = Annotated[
    str,
    Path(min_length=5, max_length=64, pattern=r"^run_[A-Za-z0-9_-]+$"),
]
AgentEvidenceRef = Annotated[
    str,
    Path(min_length=35, max_length=35, pattern=r"^ev_[a-f0-9]{32}$"),
]
AgentDraftRef = Annotated[
    str,
    Path(min_length=38, max_length=38, pattern=r"^draft_[a-f0-9]{32}$"),
]
AgentGapRef = Annotated[
    str,
    Path(min_length=36, max_length=36, pattern=r"^gap_[a-f0-9]{32}$"),
]
AgentInterventionRef = Annotated[
    str,
    Path(
        min_length=45,
        max_length=45,
        pattern=r"^intervention_[a-f0-9]{32}$",
    ),
]


def _no_store(response: Response) -> None:
    response.headers.update(
        {
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
    )


def _accepted(row: AgentRun) -> AgentAcceptedOut:
    return AgentAcceptedOut(
        contract_version=CONTRACT_VERSION,
        run_id=row.public_id,
        conversation_id=row.conversation_id,
        status="queued",
        status_url=f"/agent/v1/runs/{row.public_id}",
        events_url=f"/agent/v1/runs/{row.public_id}/events",
        execute_url=f"/agent/v1/runs/{row.public_id}/execute",
    )


@router.get("/programs", response_model=AgentProgramOptionsOut)
def get_agent_program_options(
    response: Response,
    organization_id: int | None = None,
    program_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    context = resolve_agent_context(db, principal, organization_id=organization_id)
    programs, truncated = list_program_options(
        db, context=context, selected_program_id=program_id
    )
    _no_store(response)
    return AgentProgramOptionsOut(
        contract_version=CONTRACT_VERSION,
        programs=programs,
        truncated=truncated,
    )


@router.get("/admin-organization", response_model=AgentAdminOrganizationOut)
def get_agent_admin_organization(
    organization_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    context = resolve_agent_context(db, principal, organization_id=organization_id)
    result = admin_organization_option(db, context=context)
    _no_store(response)
    return result


def _projection(db: Session, row: AgentRun) -> AgentRunOut:
    answer = db.get(CourseQuestionAnswer, row.answer_id) if row.answer_id else None
    learner_response = None
    projected_status = row.status
    projected_label = row.label
    projected_recovery = row.recovery_action
    if answer is not None:
        course = db.get(Course, row.course_id) if row.course_id is not None else None
        module_id = None
        module_ref_valid = row.module_ref is None
        if course is not None and row.module_ref is not None:
            matches = [
                module.id
                for module in build_course_map(db, course).modules
                if module.source_ref == row.module_ref
            ]
            if len(matches) == 1:
                module_id = matches[0]
                module_ref_valid = True
        citations = (
            revalidate_stored_learner_answer(
                db,
                course,
                answer,
                module_id=module_id,
            )
            if course is not None and module_ref_valid
            else None
        )
        if citations is None:
            projected_status = "abstained"
            projected_label = "Материал ответа больше недоступен"
            projected_recovery = "choose_supported_task"
            learner_response = AgentLearnerResponseOut(
                mode="abstained",
                content=(
                    "Источник этого ответа изменился или больше не доступен. "
                    "Выберите другой опубликованный материал курса."
                ),
                confidence=AgentConfidenceOut(
                    band="insufficient",
                    value=0.0,
                    explanation="Сохранённый ответ скрыт после повторной проверки источника",
                ),
                evidence=[],
                feedback_url=f"/agent/v1/runs/{row.public_id}/feedback",
            )
        else:
            evidence = []
            for citation in citations[:8]:
                if (
                    not isinstance(citation, dict)
                    or not str(citation.get("quote") or "").strip()
                ):
                    continue
                citation_ref = evidence_ref(row, citation)
                source = evidence_source_for_citation(db, course, citation)
                evidence.append(
                    AgentEvidenceOut(
                        evidence_ref=citation_ref,
                        kind="course_excerpt",
                        title=str(citation.get("document_title") or "Материал курса")[
                            :300
                        ],
                        excerpt=str(citation.get("quote") or "")[:700],
                        module_title=(
                            str(citation.get("module_title"))[:300]
                            if citation.get("module_title")
                            else None
                        ),
                        support="direct",
                        visibility="learner_published",
                        open_url=(
                            f"/agent/v1/runs/{row.public_id}/evidence/{citation_ref}/source"
                            if source is not None
                            else None
                        ),
                        source_label=(
                            "Открыть источник в Canvas"
                            if source is not None and source.provenance == "canvas"
                            else (
                                "Открыть внешний источник"
                                if source is not None
                                else None
                            )
                        ),
                        provenance=source.provenance if source is not None else None,
                    )
                )
            confidence_value = max(0.0, min(1.0, float(answer.confidence)))
            confidence_band = (
                "insufficient"
                if answer.insufficient_context
                else "supported" if confidence_value >= 0.65 else "partial"
            )
            learner_response = AgentLearnerResponseOut(
                mode=answer.response_mode,
                content=answer.answer,
                confidence=AgentConfidenceOut(
                    band=confidence_band,
                    value=confidence_value,
                    explanation=(
                        "В материалах курса не нашлось достаточной опоры"
                        if confidence_band == "insufficient"
                        else (
                            "Ответ опирается на показанные материалы курса"
                            if confidence_band == "supported"
                            else "Найдена частичная опора — проверьте фрагменты ниже"
                        )
                    ),
                ),
                evidence=evidence,
                feedback_url=f"/agent/v1/runs/{row.public_id}/feedback",
            )
    source_response = None
    if row.workflow == "learner.locate_source.v1" and row.status == "completed":
        source = resolve_source_action(db, row)
        source_response = AgentSourceActionOut(
            mode="source_action",
            title=source.title,
            label=(
                "Открыть источник в Canvas"
                if source.provenance == "canvas"
                else "Открыть внешний источник"
            ),
            open_url=f"/agent/v1/runs/{row.public_id}/source",
            provenance=source.provenance,
        )
    instructor_response = None
    if row.workflow == "instructor.course_summary.v1" and row.status == "completed":
        workspace, priorities = project_instructor_course_summary(db, row)
        raw_audit_state = (
            workspace.latest_audit.status if workspace.latest_audit else "missing"
        )
        audit_state = (
            raw_audit_state
            if raw_audit_state in {"missing", "queued", "running", "done", "failed"}
            else "failed"
        )
        if audit_state == "missing":
            headline = "Сначала запустите проверку материалов курса"
        elif audit_state in {"queued", "running"}:
            headline = "Проверка курса ещё выполняется"
        elif audit_state == "failed":
            headline = "Последнюю проверку курса нужно повторить"
        elif priorities:
            headline = "Начните с первого доказательного приоритета"
        else:
            headline = "Срочных наблюдений в текущей проверке нет"
        limitations = [
            "Сводка относится только к текущей сохранённой версии курса.",
            "Помощник не показывает вопросы, оценки или данные отдельных учеников.",
        ]
        if audit_state != "done":
            limitations.append(
                "Полный список приоритетов появится после завершённой проверки."
            )
        instructor_response = AgentInstructorCourseSummaryOut(
            mode="course_summary",
            course_title=workspace.course.title,
            headline=headline,
            health=AgentInstructorHealthOut(
                audit_state=audit_state,
                findings_total=workspace.health.findings_total,
                high_severity_findings=workspace.health.high_severity_findings,
                findings_reviewed=workspace.health.findings_reviewed,
            ),
            priorities=[
                AgentInstructorPriorityOut.model_validate(item) for item in priorities
            ],
            limitations=limitations,
        )
    elif row.workflow == "instructor.inspect_audit.v1" and row.status == "completed":
        try:
            _, finding, _ = resolve_instructor_finding(db, row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = "Приоритет относится к другой версии проверки"
            projected_recovery = "choose_supported_task"
        else:
            instructor_response = AgentInstructorFindingOut(
                mode="finding_review",
                finding_ref=row.selection_ref or "",
                title=finding.title,
                severity=finding.severity,
                status=finding.status,
                description=finding.description,
                recommendation=finding.recommendation,
                confidence=finding.confidence,
                confidence_label=finding.confidence_label,
                evidence=[
                    AgentInstructorEvidenceOut(
                        kind="course_excerpt",
                        source_label="Фрагмент текущей версии курса",
                        excerpt=item.quote,
                    )
                    for item in finding.evidence[:5]
                ],
                limitations=[
                    "Вывод относится только к текущей сохранённой версии курса.",
                    "Преподаватель должен проверить каждый фрагмент до подтверждения находки.",
                ],
            )
    elif (
        row.workflow == "instructor.inspect_question_gaps.v1"
        and row.status == "completed"
    ):
        course, gap_candidates = project_instructor_question_gaps(db, row)
        signal_labels = {
            "repeated_unsupported": "Помощник повторно не находил достаточную опору",
            "low_helpfulness": "Ответы по теме повторно отмечались как неполезные",
            "mixed": "Повторялись нехватка опоры и низкая полезность ответа",
        }
        instructor_response = AgentInstructorQuestionGapsOut(
            mode="question_gaps",
            course_title=course.title,
            window_days=30,
            privacy_threshold="Сигнал виден только для группы не менее трёх активных учеников.",
            candidates=[
                AgentInstructorGapOut(
                    gap_ref=gap_ref,
                    topic_label=candidate.topic_label,
                    module_title=candidate.module_title,
                    signal_kind=candidate.signal_kind,
                    signal_label=signal_labels[candidate.signal_kind],
                    cohort_band=candidate.cohort_band,
                    event_band=candidate.event_band,
                    confidence=candidate.confidence,
                    confidence_label=(
                        "Устойчивый групповой сигнал"
                        if candidate.confidence >= 0.75
                        else "Стоит проверить"
                    ),
                    evidence=AgentInstructorEvidenceOut(
                        kind="course_excerpt",
                        source_label=candidate.topic_label[:100],
                        excerpt=candidate.evidence_excerpt,
                    ),
                )
                for gap_ref, candidate in gap_candidates
            ],
            limitations=[
                "Это кандидат на улучшение курса, а не оценка учеников или преподавателя.",
                "Вопросы, ответы, личности и точные количества не показываются.",
                "Сигнал относится только к текущим материалам и последним 30 дням.",
            ],
        )
    elif (
        row.workflow == "instructor.draft_improvement.v1" and row.status == "completed"
    ):
        try:
            suggestion = resolve_instructor_draft(db, row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = "Черновик относится к другой версии проверки"
            projected_recovery = "choose_supported_task"
        else:
            course = db.get(Course, suggestion.course_id)
            validated_citations = (
                validate_copilot_suggestion_citations(db, course, suggestion)
                if course is not None
                else None
            )
            if validated_citations is None:
                projected_status = "abstained"
                projected_label = "Источники черновика относятся к другой версии курса"
                projected_recovery = "choose_supported_task"
                validated_citations = []
            citations = [
                AgentInstructorEvidenceOut(
                    kind="course_excerpt",
                    source_label=str(item.get("document_title") or "Материал курса")[
                        :100
                    ],
                    excerpt=str(item.get("quote") or "")[:800],
                )
                for item in validated_citations[:8]
                if isinstance(item, dict) and str(item.get("quote") or "").strip()
            ]
            if projected_status != "abstained":
                instructor_response = AgentInstructorDraftOut(
                    mode="improvement_draft",
                    draft_ref=row.selection_ref or "",
                    title=suggestion.title,
                    action_type=suggestion.action_type,
                    target_bloom_level=suggestion.target_bloom_level,
                    content=suggestion.draft,
                    rationale=suggestion.rationale,
                    confidence=suggestion.confidence,
                    citations=citations,
                    insufficient_context=suggestion.insufficient_context,
                    review_status=suggestion.status,
                    review_version=suggestion.version,
                    limitations=(
                        [
                            "Недостаточно подтверждающих материалов для принятия черновика."
                        ]
                        if suggestion.insufficient_context
                        else [
                            (
                                "Черновик требует проверки и отдельного решения преподавателя."
                                if suggestion.status == "draft"
                                else "Решение преподавателя сохранено; новый вариант создаётся отдельно."
                            ),
                            "Canvas не изменён.",
                        ]
                    ),
                )
    elif (
        row.workflow == "instructor.preview_canvas_change.v1"
        and row.status == "completed"
    ):
        try:
            suggestion, change_set, item = preview_instructor_canvas_change(db, row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = "Принятый черновик больше не доступен для предпросмотра"
            projected_recovery = "choose_supported_task"
        else:
            instructor_response = AgentInstructorCanvasChangeOut(
                mode="canvas_change_preview",
                change_set_ref=instructor_change_set_ref(row, suggestion.id),
                course_title=change_set.course_title,
                title=item.title,
                operation=item.operation,
                ready_for_canvas=item.ready_for_canvas,
                module_title=item.module_title,
                content=item.body,
                confidence=item.confidence,
                review_status="accepted",
                warnings=[
                    warning
                    for warning in [item.warning, *change_set.warnings]
                    if warning
                ][:4],
                read_only=True,
            )
    program_response = None
    if row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS and row.status == "completed":
        try:
            if row.workflow == "program.inspect_map.v1":
                program_response = project_program_route_brief(db, row=row)
            elif row.workflow == "program.draft_review_note.v1":
                program_response = project_program_review_draft(db, row=row)
            else:
                program_response = project_program_evidence_route(db, row=row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = {
                "program.inspect_map.v1": (
                    "Карта программы изменилась — соберите маршрут заново"
                ),
                "program.draft_review_note.v1": (
                    "Основания заметки изменились — подготовьте её заново"
                ),
            }.get(
                row.workflow,
                "Основания программы изменились — повторите выбранную проверку",
            )
            projected_recovery = "choose_supported_task"
    admin_response = None
    if row.workflow == "admin.integration_readiness.v1" and row.status == "completed":
        try:
            admin_response = project_admin_operations_brief(db, row=row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = (
                "Операционное состояние изменилось — соберите маршрут заново"
            )
            projected_recovery = "choose_supported_task"
    if row.workflow == "admin.analytics_health.v1" and row.status == "completed":
        try:
            admin_response = project_admin_analytics_brief(db, row=row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = "Данные контрольной ленты изменились — соберите её заново"
            projected_recovery = "choose_supported_task"
    if row.workflow == "admin.policy_status.v1" and row.status == "completed":
        try:
            admin_response = project_admin_policy_status(db, row=row)
        except HTTPException:
            projected_status = "abstained"
            projected_label = (
                "Политика или журнал очистки изменились — проверьте заново"
            )
            projected_recovery = "choose_supported_task"
    plan = (
        AgentWorkflowPlanOut(
            mode="workflow_plan",
            workflow=row.workflow,
            planned_steps=planned_step_count(row),
        )
        if row.workflow is not None
        and learner_response is None
        and source_response is None
        and instructor_response is None
        and program_response is None
        and admin_response is None
        and row.status == "completed"
        and (
            row.workflow not in EXECUTABLE_PROGRAM_WORKFLOWS
            and row.workflow != "admin.integration_readiness.v1"
            and row.workflow != "admin.analytics_health.v1"
            and row.workflow != "admin.policy_status.v1"
            or projected_status == "completed"
        )
        else None
    )
    return AgentRunOut(
        contract_version=CONTRACT_VERSION,
        run_id=row.public_id,
        conversation_id=row.conversation_id,
        workflow=row.workflow,
        status=projected_status,
        route_state=row.route_state,
        user_state=AgentUserStateOut(
            label=projected_label,
            recovery_action=projected_recovery,
        ),
        response=(
            learner_response
            or source_response
            or instructor_response
            or program_response
            or admin_response
            or plan
        ),
        review=None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/messages", response_model=AgentAcceptedOut, status_code=202)
def create_agent_message(
    payload: AgentMessageIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = create_or_replay_agent_run(
        db,
        principal=principal,
        payload=payload,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    _no_store(response)
    return _accepted(row)


def _intervention_draft_out(
    draft,
    *,
    intervention_ref: str,
) -> AgentInstructorInterventionDraftOut:
    citations = [
        AgentInstructorEvidenceOut(
            kind="course_excerpt",
            source_label=str(item.get("document_title") or "Материал курса")[:100],
            excerpt=str(item.get("quote") or "")[:800],
        )
        for item in (draft.citations or [])[:3]
        if isinstance(item, dict) and str(item.get("quote") or "").strip()
    ]
    return AgentInstructorInterventionDraftOut(
        mode="intervention_draft",
        intervention_ref=intervention_ref,
        title=draft.title,
        content=draft.content,
        rationale=draft.rationale,
        confidence=draft.confidence,
        citations=citations,
        signal_kind=draft.signal_kind,
        cohort_band=draft.cohort_band,
        event_band=draft.event_band,
        review_status=draft.status,
        review_version=draft.version,
        limitations=[
            "Черновик требует проверки и отдельного решения преподавателя.",
            "Вопросы и личности учеников не входят в черновик.",
            "Canvas не изменён.",
        ],
    )


@router.post(
    "/gaps/{gap_ref}/draft",
    response_model=AgentInstructorInterventionDraftOut,
    status_code=201,
)
def create_agent_instructor_intervention(
    gap_ref: AgentGapRef,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    draft, issuer = create_instructor_intervention(
        db,
        principal=principal,
        gap_ref=gap_ref,
    )
    intervention_ref = instructor_intervention_ref(issuer, draft.id)
    _no_store(response)
    return _intervention_draft_out(
        draft,
        intervention_ref=intervention_ref,
    )


@router.patch(
    "/interventions/{intervention_ref}/review",
    response_model=AgentInstructorInterventionReviewOut,
)
def review_agent_instructor_intervention(
    intervention_ref: AgentInterventionRef,
    payload: AgentInstructorInterventionReviewIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    draft = review_instructor_intervention(
        db,
        principal=principal,
        intervention_ref=intervention_ref,
        expected_version=payload.expected_version,
        status=payload.status,
        content=payload.content,
    )
    _no_store(response)
    return AgentInstructorInterventionReviewOut(
        contract_version=CONTRACT_VERSION,
        mode="reviewed_intervention",
        intervention_ref=intervention_ref,
        status=draft.status,
        version=draft.version,
        content=draft.content,
        edit_distance_ratio=draft.edit_distance_ratio or 0.0,
        decision_latency_seconds=draft.decision_latency_seconds or 0,
        canvas_changed=False,
    )


@router.patch(
    "/drafts/{draft_ref}/review",
    response_model=AgentInstructorDraftReviewOut,
)
def review_agent_instructor_draft(
    draft_ref: AgentDraftRef,
    payload: AgentInstructorDraftReviewIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    suggestion = review_instructor_draft(
        db,
        principal=principal,
        draft_ref=draft_ref,
        expected_version=payload.expected_version,
        status=payload.status,
        content=payload.content,
    )
    _no_store(response)
    return AgentInstructorDraftReviewOut(
        contract_version=CONTRACT_VERSION,
        mode="reviewed_draft",
        draft_ref=draft_ref,
        status=suggestion.status,
        version=suggestion.version,
        content=suggestion.draft,
        canvas_changed=False,
    )


@router.post("/runs/{run_id}/execute", response_model=AgentRunOut)
def advance_agent_run(
    run_id: AgentRunId,
    payload: AgentMessageIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    context = resolve_agent_context(db, principal, organization_id=row.organization_id)
    validate_agent_run_input(row, context=context, payload=payload)
    executable_workflows = (
        EXECUTABLE_LEARNER_WORKFLOWS
        | EXECUTABLE_INSTRUCTOR_WORKFLOWS
        | EXECUTABLE_PROGRAM_WORKFLOWS
        | EXECUTABLE_ADMIN_WORKFLOWS
    )
    if row.workflow not in executable_workflows:
        _no_store(response)
        return _projection(db, row)
    if row.status in {"completed", "abstained", "failed"}:
        _no_store(response)
        return _projection(db, row)
    try:
        lock_and_assert_agent_workflow_enabled(
            db,
            organization_id=row.organization_id,
            role=row.role,
            workflow=row.workflow,
        )
    except AgentPolicyScopeDenied as exc:
        raise HTTPException(status_code=404, detail="resource not found") from exc
    if row.status == "queued":
        row.status = "routing"
        row.label = (
            "Проверяем доступ к организации"
            if row.workflow in EXECUTABLE_ADMIN_WORKFLOWS
            else (
                "Проверяем доступ к выбранной программе"
                if row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS
                else "Проверяем доступ к текущему курсу"
            )
        )
        db.commit()
        db.refresh(row)
        _no_store(response)
        return _projection(db, row)
    if row.status == "routing":
        is_source = row.workflow == "learner.locate_source.v1"
        is_instructor = row.workflow in EXECUTABLE_INSTRUCTOR_WORKFLOWS
        is_program = row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS
        is_admin = row.workflow in EXECUTABLE_ADMIN_WORKFLOWS
        row.status = (
            "tool_running"
            if is_source or is_instructor or is_program or is_admin
            else "generating"
        )
        row.label = (
            "Проверяем выбранный источник"
            if is_source
            else (
                (
                    "Собираем контрольную ленту организации"
                    if row.workflow == "admin.analytics_health.v1"
                    else (
                        "Сверяем срок хранения и агрегированный итог очистки"
                        if row.workflow == "admin.policy_status.v1"
                        else "Собираем операционный маршрут организации"
                    )
                )
                if is_admin
                else (
                    "Собираем маршрут по сохранённой карте программы"
                    if is_program
                    else (
                        "Собираем приоритеты текущего курса"
                        if row.workflow == "instructor.course_summary.v1"
                        else (
                            "Проверяем находку и её доказательства"
                            if row.workflow == "instructor.inspect_audit.v1"
                            else (
                                "Готовим проверяемый черновик по материалам курса"
                                if row.workflow == "instructor.draft_improvement.v1"
                                else (
                                    "Готовим безопасный предпросмотр изменения Canvas"
                                    if row.workflow
                                    == "instructor.preview_canvas_change.v1"
                                    else "Ищем опору в выбранном материале"
                                )
                            )
                        )
                    )
                )
            )
        )
        db.commit()
        db.refresh(row)
        _no_store(response)
        return _projection(db, row)
    try:
        if row.workflow in EXECUTABLE_INSTRUCTOR_WORKFLOWS:
            row = execute_instructor_run(
                db,
                principal=principal,
                run_id=row.id,
            )
        elif row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS:
            row = execute_program_run(
                db,
                principal=principal,
                run_id=row.id,
            )
        elif row.workflow in EXECUTABLE_ADMIN_WORKFLOWS:
            row = execute_admin_run(
                db,
                principal=principal,
                run_id=row.id,
            )
        else:
            row = execute_learner_run(
                db,
                principal=principal,
                run_id=row.id,
                question=payload.message,
                module_ref=payload.selection.module_ref if payload.selection else None,
                selection_ref=(
                    payload.selection.evidence_ref if payload.selection else None
                ),
            )
    except HTTPException as exc:
        _persist_execution_terminal(
            db,
            run_id=row.id,
            status="abstained",
            label=(
                "Организация или её текущее состояние больше недоступны"
                if row.workflow in EXECUTABLE_ADMIN_WORKFLOWS
                else (
                    "Программа или её текущая версия больше недоступна"
                    if row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS
                    else (
                        "Курс или результаты проверки больше недоступны"
                        if row.workflow in EXECUTABLE_INSTRUCTOR_WORKFLOWS
                        else "Выбранный материал больше недоступен"
                    )
                )
            ),
            tool_audits=learner_tool_audit_snapshots(exc),
        )
        raise
    except Exception as exc:
        _persist_execution_terminal(
            db,
            run_id=row.id,
            status="failed",
            label=(
                "Не удалось собрать операционный маршрут"
                if row.workflow in EXECUTABLE_ADMIN_WORKFLOWS
                else (
                    "Не удалось собрать маршрут программы"
                    if row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS
                    else (
                        "Не удалось собрать сводку текущего курса"
                        if row.workflow in EXECUTABLE_INSTRUCTOR_WORKFLOWS
                        else "Не удалось подготовить ответ по материалам курса"
                    )
                )
            ),
            tool_audits=learner_tool_audit_snapshots(exc),
        )
        raise HTTPException(status_code=503, detail="temporary failure") from exc
    _no_store(response)
    return _projection(db, row)


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_agent_run(
    run_id: AgentRunId,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    _no_store(response)
    return _projection(db, row)


@router.get("/runs/{run_id}/source", response_model=None)
def open_agent_source(
    run_id: AgentRunId,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    source = resolve_source_action(db, row)
    response = RedirectResponse(source.destination_url, status_code=303)
    _no_store(response)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/runs/{run_id}/evidence/{candidate_ref}/source", response_model=None)
def open_agent_evidence_source(
    run_id: AgentRunId,
    candidate_ref: AgentEvidenceRef,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    source = resolve_evidence_source(db, row, candidate_ref)
    response = RedirectResponse(source.destination_url, status_code=303)
    _no_store(response)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.patch("/runs/{run_id}/feedback", response_model=AgentFeedbackOut)
def set_agent_feedback(
    run_id: AgentRunId,
    payload: AgentFeedbackIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    answer = db.get(CourseQuestionAnswer, row.answer_id) if row.answer_id else None
    if (
        answer is None
        or answer.course_id != row.course_id
        or answer.asked_by_user_id != principal.user_id
    ):
        raise HTTPException(status_code=404, detail="resource not found")
    previous_status = answer.feedback_status
    answer.feedback_status = payload.status
    answer.feedback_comment = None
    answer.reviewed_by = principal.email or f"user:{principal.user_id}"
    answer.reviewed_at = datetime.now(timezone.utc)
    db.add(
        CourseQaFeedbackEvent(
            answer_id=answer.id,
            course_id=answer.course_id,
            reviewed_by_user_id=principal.user_id,
            from_status=previous_status,
            to_status=payload.status,
            reviewed_by=answer.reviewed_by,
            comment=None,
        )
    )
    db.commit()
    _no_store(response)
    return AgentFeedbackOut(status=payload.status)


@router.get("/runs/{run_id}/events", response_model=AgentEventsOut)
def get_agent_run_events(
    run_id: AgentRunId,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    row = owned_agent_run(db, principal=principal, public_id=run_id)
    if not event_replay_available(row):
        raise HTTPException(
            status_code=404,
            detail={"code": "event_replay_expired"},
        )
    events = [
        AgentEventOut(
            contract_version=CONTRACT_VERSION,
            run_id=row.public_id,
            sequence=1,
            type="run.accepted",
            occurred_at=row.created_at,
            payload={"status": "queued", "label": "Запрос принят"},
        ),
    ]
    if row.status != "queued":
        events.append(
            AgentEventOut(
                contract_version=CONTRACT_VERSION,
                run_id=row.public_id,
                sequence=len(events) + 1,
                type="run.routing",
                occurred_at=row.updated_at,
                payload={
                    "status": "routing",
                    "label": "Проверяем доступ к текущему курсу",
                },
            )
        )
    if row.status in {"tool_running", "generating", "completed", "abstained", "failed"}:
        stage = (
            "tool_running"
            if row.workflow == "learner.locate_source.v1"
            or row.workflow in EXECUTABLE_PROGRAM_WORKFLOWS
            else "generating"
        )
        events.append(
            AgentEventOut(
                contract_version=CONTRACT_VERSION,
                run_id=row.public_id,
                sequence=len(events) + 1,
                type=f"run.{stage}",
                occurred_at=row.updated_at,
                payload={"status": stage, "label": "Готовим результат по материалу"},
            )
        )
    if row.status in {"completed", "abstained", "failed"}:
        events.append(
            AgentEventOut(
                contract_version=CONTRACT_VERSION,
                run_id=row.public_id,
                sequence=len(events) + 1,
                type=f"run.{row.status}",
                occurred_at=row.updated_at,
                payload={"status": row.status, "label": row.label},
            )
        )
    _no_store(response)
    return AgentEventsOut(
        contract_version=CONTRACT_VERSION,
        run_id=row.public_id,
        events=events,
    )


__all__ = ["router"]
