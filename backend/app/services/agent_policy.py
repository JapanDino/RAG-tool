from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

AgentRole = Literal[
    "student", "instructor", "methodologist", "program_designer", "administrator"
]
RouteState = Literal["routed", "clarification_required", "unsupported"]
CATALOG_VERSION = "agent-tools.v1"
TRUSTED_CONTEXT_FIELDS = frozenset(
    {
        "organization_id",
        "course_id",
        "user_id",
        "role",
        "registration_id",
        "product_session_id",
        "provider",
        "model",
        "system_prompt",
    }
)


@dataclass(frozen=True)
class ToolSchemaDefinition:
    schema_id: str
    fields: frozenset[str]
    max_bytes: int
    additional_properties: Literal[False] = False


@dataclass(frozen=True)
class ToolAuditDefinition:
    event_type: str
    fields: frozenset[str]
    content_safe: Literal[True] = True


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    catalog_version: Literal["agent-tools.v1"]
    roles: frozenset[AgentRole]
    implementation_refs: tuple[str, ...]
    implementation_state: Literal["existing", "adapter", "planned"]
    input_schema: ToolSchemaDefinition
    output_schema: ToolSchemaDefinition
    evidence_contract: str
    failure_mapping: tuple[str, ...]
    audit: ToolAuditDefinition
    timeout_seconds: int
    max_output_bytes: int


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    roles: frozenset[AgentRole]
    tools: tuple[str, ...]
    requires_course: bool


@dataclass(frozen=True)
class RouteDecision:
    state: RouteState
    workflow: str | None
    label: str
    recovery_action: Literal["clarify_request", "choose_supported_task"] | None


def _tool(
    name: str,
    roles: tuple[AgentRole, ...],
    implementation_refs: str | tuple[str, ...],
    state: Literal["existing", "adapter", "planned"],
    *,
    input_fields: tuple[str, ...],
    output_fields: tuple[str, ...],
    evidence_contract: str,
) -> ToolDefinition:
    refs = (
        (implementation_refs,)
        if isinstance(implementation_refs, str)
        else implementation_refs
    )
    return ToolDefinition(
        name=name,
        catalog_version=CATALOG_VERSION,
        roles=frozenset(roles),
        implementation_refs=refs,
        implementation_state=state,
        input_schema=ToolSchemaDefinition(
            schema_id=f"{CATALOG_VERSION}.{name}.input",
            fields=frozenset(input_fields),
            max_bytes=8 * 1024,
        ),
        output_schema=ToolSchemaDefinition(
            schema_id=f"{CATALOG_VERSION}.{name}.output",
            fields=frozenset(output_fields),
            max_bytes=64 * 1024,
        ),
        evidence_contract=evidence_contract,
        failure_mapping=(
            "access_denied",
            "resource_unavailable",
            "budget_exceeded",
            "temporary_failure",
        ),
        audit=ToolAuditDefinition(
            event_type=f"agent.tool.{name}.v1",
            fields=frozenset(
                {"run_id", "tool_name", "status", "latency_ms", "failure_class"}
            ),
        ),
        timeout_seconds=20,
        max_output_bytes=64 * 1024,
    )


def _checked_registry(items):
    rows = tuple(items)
    registry = {item.name: item for item in rows}
    if len(registry) != len(rows):
        raise ValueError("duplicate_registry_name")
    return MappingProxyType(registry)


TOOL_REGISTRY = _checked_registry(
    (
        _tool(
            "get_current_course_map",
            ("student",),
            "backend/app/services/course_map.py::build_course_map",
            "existing",
            input_fields=("focus_ref",),
            output_fields=("modules", "destinations"),
            evidence_contract="Published exact-course topology only",
        ),
        _tool(
            "retrieve_published_course_evidence",
            ("student",),
            "backend/app/services/course_qa.py::retrieve_student_tutor_context",
            "existing",
            input_fields=("query", "module_ref", "top_k"),
            output_fields=("evidence_refs", "excerpts", "confidence"),
            evidence_contract="Student-visible non-assessment retrieval hits",
        ),
        _tool(
            "explain_with_citations",
            ("student",),
            "backend/app/services/course_qa.py::answer_course_question",
            "existing",
            input_fields=("question", "evidence_refs"),
            output_fields=("content", "citations", "confidence", "abstained"),
            evidence_contract="Validated citations or abstention",
        ),
        _tool(
            "give_assessment_safe_hint",
            ("student",),
            (
                "backend/app/services/course_qa.py::classify_student_tutor_request",
                "backend/app/services/course_qa.py::answer_course_question",
            ),
            "existing",
            input_fields=("question", "evidence_refs"),
            output_fields=("mode", "guidance", "citations", "confidence", "abstained"),
            evidence_contract="Guidance only; expected answers excluded",
        ),
        _tool(
            "create_self_check",
            ("student",),
            "backend/app/services/learner_agent.py::create_learner_self_check",
            "adapter",
            input_fields=("topic", "evidence_refs", "item_count"),
            output_fields=("items", "feedback_policy", "citations"),
            evidence_contract="Formative check without graded answers or rubrics",
        ),
        _tool(
            "open_authoritative_source",
            ("student",),
            "backend/app/services/learner_agent.py::resolve_source_action",
            "adapter",
            input_fields=("destination_ref",),
            output_fields=("destination_ref", "label"),
            evidence_contract="Validated opaque destination; no backend fetch",
        ),
        _tool(
            "get_teacher_course_summary",
            ("instructor",),
            "backend/app/services/teacher_workspace.py::build_teacher_workspace",
            "existing",
            input_fields=("focus",),
            output_fields=("priorities", "evidence", "aggregate_signals"),
            evidence_contract="Exact-course evidence and aggregate tutor signals",
        ),
        _tool(
            "run_or_open_course_audit",
            ("instructor",),
            "backend/app/services/course_audit.py::CourseAuditService",
            "adapter",
            input_fields=("audit_ref", "refresh"),
            output_fields=("audit_ref", "status", "findings"),
            evidence_contract="Bounded run status and evidence-backed results",
        ),
        _tool(
            "inspect_finding_evidence",
            ("instructor",),
            "backend/app/services/instructor_agent.py::resolve_instructor_finding",
            "adapter",
            input_fields=("finding_ref",),
            output_fields=("finding", "evidence", "confidence", "history"),
            evidence_contract="Exact-course finding and content-safe history",
        ),
        _tool(
            "inspect_aggregate_question_gaps",
            ("instructor",),
            "backend/app/services/learning_gap_aggregation.py::aggregate_learning_gaps",
            "adapter",
            input_fields=("window_days",),
            output_fields=("topics", "cohort_size", "limitations"),
            evidence_contract="Minimum-cohort aggregate without transcript or identity",
        ),
        _tool(
            "draft_course_improvement",
            ("instructor",),
            "backend/app/services/course_copilot.py::create_copilot_suggestion",
            "adapter",
            input_fields=("finding_ref", "instruction"),
            output_fields=(
                "draft_ref",
                "content",
                "citations",
                "confidence",
                "limitations",
            ),
            evidence_contract="Editable cited draft with confidence and limitations",
        ),
        _tool(
            "preview_canvas_change_set",
            ("instructor",),
            "backend/app/services/instructor_agent.py::preview_instructor_canvas_change",
            "adapter",
            input_fields=("suggestion_ref",),
            output_fields=("change_set_ref", "operations", "warnings"),
            evidence_contract="Read-only exact-target preview",
        ),
        _tool(
            "get_program_competency_map",
            ("methodologist", "program_designer", "administrator"),
            (
                "backend/app/services/program_agent.py::current_program_route_brief",
                "backend/app/services/program_intelligence.py::get_program_audit_preview",
            ),
            "adapter",
            input_fields=("program_ref",),
            output_fields=(
                "program_title",
                "program_version",
                "counts",
                "priorities",
                "analysis_truncated",
                "findings_truncated",
                "limitations",
            ),
            evidence_contract="Bounded authorized map counts and current deterministic audit findings",
        ),
        _tool(
            "inspect_program_gap",
            ("methodologist", "program_designer", "administrator"),
            "backend/app/services/program_agent.py::current_program_evidence_route",
            "adapter",
            input_fields=("program_ref",),
            output_fields=(
                "route_kind",
                "state",
                "program_title",
                "program_version",
                "headline",
                "candidate",
                "analysis_truncated",
                "action_target",
                "action_label",
                "limitations",
            ),
            evidence_contract="Evidence-backed candidate, not automatic verdict",
        ),
        _tool(
            "inspect_prerequisite_path",
            ("methodologist", "program_designer", "administrator"),
            "backend/app/services/program_agent.py::current_program_evidence_route",
            "adapter",
            input_fields=("program_ref",),
            output_fields=(
                "route_kind",
                "state",
                "program_title",
                "program_version",
                "headline",
                "candidate",
                "analysis_truncated",
                "action_target",
                "action_label",
                "limitations",
            ),
            evidence_contract="Explicit relation and contribution evidence only",
        ),
        _tool(
            "draft_program_review_note",
            ("program_designer", "administrator"),
            "backend/app/services/program_agent.py::current_program_review_draft",
            "adapter",
            input_fields=("program_ref",),
            output_fields=(
                "state",
                "program_title",
                "program_version",
                "headline",
                "draft_ref",
                "candidate",
                "content",
                "source_fingerprint",
                "current_note",
                "limitations",
                "program_changed",
                "canvas_changed",
            ),
            evidence_contract="Editable evidence-linked note without map mutation",
        ),
        _tool(
            "get_aggregate_adoption_health",
            ("administrator",),
            "backend/app/services/admin_agent.py::current_admin_adoption_segment",
            "adapter",
            input_fields=("organization_ref",),
            output_fields=("segment",),
            evidence_contract="Five-user-threshold organization aggregate without breakdowns",
        ),
        _tool(
            "get_agent_latency_cost_health",
            ("administrator",),
            "backend/app/services/admin_agent.py::current_admin_runtime_segments",
            "adapter",
            input_fields=("organization_ref",),
            output_fields=("runtime", "cost"),
            evidence_contract="Content-free runtime facts and optional configured cost estimate",
        ),
        _tool(
            "get_integration_readiness",
            ("administrator",),
            (
                "backend/app/services/admin_agent.py::current_admin_operations_brief",
                "backend/app/services/lti_registration.py::tool_registration_readiness",
                "backend/app/services/lti_pilot_health.py::pilot_launch_health",
                "backend/app/services/model_gateway.py::model_runtime_readiness",
                "backend/app/services/tutor_data.py::get_effective_tutor_data_policy",
            ),
            "adapter",
            input_fields=("organization_ref",),
            output_fields=(
                "organization_name",
                "overall_state",
                "headline",
                "stations",
                "priorities",
                "limitations",
            ),
            evidence_contract="Content-free integration, launch, runtime, and retention route",
        ),
        _tool(
            "get_retention_and_policy_status",
            ("administrator",),
            (
                "backend/app/services/admin_agent.py::current_admin_policy_status",
                "backend/app/services/tutor_data.py::get_effective_tutor_data_policy",
            ),
            "adapter",
            input_fields=("organization_ref",),
            output_fields=("retention", "policy_versions", "purge_status"),
            evidence_contract="Policy versions and aggregate purge status",
        ),
    )
)


def _workflow(
    name: str,
    roles: tuple[AgentRole, ...],
    tools: tuple[str, ...],
    *,
    course: bool = False,
) -> WorkflowDefinition:
    return WorkflowDefinition(name, frozenset(roles), tools, course)


WORKFLOW_REGISTRY = _checked_registry(
    (
        _workflow(
            "learner.explain_material.v1",
            ("student",),
            ("retrieve_published_course_evidence", "explain_with_citations"),
            course=True,
        ),
        _workflow(
            "learner.assessment_safe_hint.v1",
            ("student",),
            ("retrieve_published_course_evidence", "give_assessment_safe_hint"),
            course=True,
        ),
        _workflow(
            "learner.self_check.v1",
            ("student",),
            ("retrieve_published_course_evidence", "create_self_check"),
            course=True,
        ),
        _workflow(
            "learner.locate_source.v1",
            ("student",),
            ("get_current_course_map", "open_authoritative_source"),
            course=True,
        ),
        _workflow(
            "instructor.course_summary.v1",
            ("instructor",),
            ("get_teacher_course_summary",),
            course=True,
        ),
        _workflow(
            "instructor.inspect_audit.v1",
            ("instructor",),
            ("run_or_open_course_audit", "inspect_finding_evidence"),
            course=True,
        ),
        _workflow(
            "instructor.inspect_question_gaps.v1",
            ("instructor",),
            ("inspect_aggregate_question_gaps",),
            course=True,
        ),
        _workflow(
            "instructor.draft_improvement.v1",
            ("instructor",),
            ("inspect_finding_evidence", "draft_course_improvement"),
            course=True,
        ),
        _workflow(
            "instructor.preview_canvas_change.v1",
            ("instructor",),
            ("preview_canvas_change_set",),
            course=True,
        ),
        _workflow(
            "program.inspect_map.v1",
            ("methodologist", "program_designer", "administrator"),
            ("get_program_competency_map",),
        ),
        _workflow(
            "program.inspect_gap.v1",
            ("methodologist", "program_designer", "administrator"),
            ("inspect_program_gap",),
        ),
        _workflow(
            "program.inspect_prerequisite.v1",
            ("methodologist", "program_designer", "administrator"),
            ("inspect_prerequisite_path",),
        ),
        _workflow(
            "program.draft_review_note.v1",
            ("program_designer", "administrator"),
            ("draft_program_review_note",),
        ),
        _workflow(
            "admin.adoption_health.v1",
            ("administrator",),
            ("get_aggregate_adoption_health",),
        ),
        _workflow(
            "admin.runtime_health.v1",
            ("administrator",),
            ("get_agent_latency_cost_health",),
        ),
        _workflow(
            "admin.analytics_health.v1",
            ("administrator",),
            ("get_aggregate_adoption_health", "get_agent_latency_cost_health"),
        ),
        _workflow(
            "admin.integration_readiness.v1",
            ("administrator",),
            ("get_integration_readiness",),
        ),
        _workflow(
            "admin.policy_status.v1",
            ("administrator",),
            ("get_retention_and_policy_status",),
        ),
    )
)


ROLE_WORKFLOWS = MappingProxyType(
    {
        role: frozenset(
            name
            for name, workflow in WORKFLOW_REGISTRY.items()
            if role in workflow.roles
        )
        for role in (
            "student",
            "instructor",
            "methodologist",
            "program_designer",
            "administrator",
        )
    }
)


PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "learner.assessment_safe_hint.v1",
        (
            "контрольн",
            "экзамен",
            "ответ на задание",
            "реши за",
            "assessment",
            "quiz answer",
        ),
    ),
    (
        "learner.self_check.v1",
        ("самопроверк", "проверь меня", "тест для себя", "self check", "practice quiz"),
    ),
    (
        "learner.locate_source.v1",
        (
            "где материал",
            "найди источник",
            "открой источник",
            "where is",
            "find source",
        ),
    ),
    (
        "learner.explain_material.v1",
        ("объясни", "почему", "как связан", "не понимаю", "explain", "why", "how does"),
    ),
    (
        "instructor.inspect_audit.v1",
        ("аудит", "ошибк курса", "finding", "course audit"),
    ),
    (
        "instructor.inspect_question_gaps.v1",
        ("вопросы учен", "непонятные темы", "question gaps"),
    ),
    (
        "instructor.draft_improvement.v1",
        ("улучшить курс", "черновик улучш", "draft improvement"),
    ),
    (
        "instructor.preview_canvas_change.v1",
        ("изменения canvas", "предпросмотр измен", "canvas change"),
    ),
    (
        "instructor.course_summary.v1",
        ("сводка курса", "что требует внимания", "course summary"),
    ),
    (
        "program.inspect_prerequisite.v1",
        ("пререквизит", "предварительн", "prerequisite"),
    ),
    ("program.inspect_gap.v1", ("пробел программ", "дублирован", "program gap")),
    ("program.draft_review_note.v1", ("заметк", "review note")),
    ("program.inspect_map.v1", ("компетенц", "структура программ", "competency map")),
    (
        "admin.integration_readiness.v1",
        (
            "готовность canvas",
            "интеграц",
            "lti",
            "операционн маршрут",
            "маршрут действий",
            "integration readiness",
        ),
    ),
    (
        "admin.analytics_health.v1",
        (
            "контрольную ленту",
            "контрольная лента",
            "сводк использован",
            "использование и нагрузка",
            "adoption and runtime",
            "analytics health",
        ),
    ),
    (
        "admin.analytics_health.v1",
        ("задержк ai", "стоимость ai", "ошибки ai", "latency", "cost health"),
    ),
    ("admin.policy_status.v1", ("хранение данных", "политик", "retention")),
    ("admin.analytics_health.v1", ("использование ai", "внедрение ai", "adoption")),
)


def role_policy(role: AgentRole) -> frozenset[str]:
    return ROLE_WORKFLOWS[role]


def route_message(
    *,
    role: AgentRole,
    message: str,
    has_course_scope: bool,
    has_material_scope: bool = False,
) -> RouteDecision:
    normalized = unicodedata.normalize("NFKC", message).strip().casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in {"помоги", "help", "что ты умеешь", "что можно сделать"}:
        return RouteDecision(
            "clarification_required",
            None,
            "Уточните, что нужно сделать",
            "clarify_request",
        )
    if role == "student":
        from .course_qa import classify_student_tutor_texts

        if classify_student_tutor_texts(message) is not None:
            if not has_course_scope:
                return RouteDecision(
                    "unsupported",
                    None,
                    "Откройте помощника из нужного курса Canvas",
                    "choose_supported_task",
                )
            return RouteDecision(
                "routed",
                "learner.assessment_safe_hint.v1",
                "Задача определена",
                None,
            )
    matches: list[str] = []
    for workflow_name, markers in PATTERNS:
        workflow = WORKFLOW_REGISTRY[workflow_name]
        if (
            workflow_name in ROLE_WORKFLOWS[role]
            and any(marker in normalized for marker in markers)
            and workflow_name not in matches
        ):
            matches.append(workflow_name)
    if len(matches) > 1:
        return RouteDecision(
            "clarification_required",
            None,
            "Уточните одну задачу, с которой нужно начать",
            "clarify_request",
        )
    if matches:
        workflow_name = matches[0]
        workflow = WORKFLOW_REGISTRY[workflow_name]
        if workflow.requires_course and not has_course_scope:
            return RouteDecision(
                "unsupported",
                None,
                "Откройте помощника из нужного курса Canvas",
                "choose_supported_task",
            )
        return RouteDecision("routed", workflow_name, "Задача определена", None)
    if role == "student" and has_course_scope and has_material_scope:
        return RouteDecision(
            "routed",
            "learner.explain_material.v1",
            "Задача определена",
            None,
        )
    return RouteDecision(
        "unsupported",
        None,
        "Эта задача пока не поддерживается",
        "choose_supported_task",
    )


def validate_registries() -> None:
    expected_audit_fields = frozenset(
        {"run_id", "tool_name", "status", "latency_ms", "failure_class"}
    )
    allowed_failures = frozenset(
        {
            "access_denied",
            "resource_unavailable",
            "budget_exceeded",
            "temporary_failure",
        }
    )
    for tool in TOOL_REGISTRY.values():
        if tool.catalog_version != CATALOG_VERSION:
            raise ValueError("tool_catalog_version_mismatch")
        if not tool.implementation_refs or any(
            not target or "::" not in target for target in tool.implementation_refs
        ):
            raise ValueError("tool_implementation_boundary_invalid")
        if tool.input_schema.additional_properties is not False:
            raise ValueError("tool_input_schema_not_closed")
        if tool.output_schema.additional_properties is not False:
            raise ValueError("tool_output_schema_not_closed")
        if tool.input_schema.fields & TRUSTED_CONTEXT_FIELDS:
            raise ValueError("tool_input_contains_trusted_context")
        if not 0 < tool.input_schema.max_bytes <= 8 * 1024:
            raise ValueError("tool_input_budget_invalid")
        if tool.output_schema.max_bytes != tool.max_output_bytes:
            raise ValueError("tool_output_budget_mismatch")
        if not tool.evidence_contract or len(tool.evidence_contract) > 300:
            raise ValueError("tool_evidence_contract_invalid")
        if (
            not tool.failure_mapping
            or not set(tool.failure_mapping) <= allowed_failures
        ):
            raise ValueError("tool_failure_mapping_invalid")
        if (
            not tool.audit.content_safe
            or tool.audit.fields != expected_audit_fields
            or any(
                field in tool.audit.fields
                for field in {"message", "prompt", "response", "evidence", "content"}
            )
        ):
            raise ValueError("tool_audit_contract_invalid")
    for workflow in WORKFLOW_REGISTRY.values():
        if len(workflow.tools) > 4:
            raise ValueError("workflow_tool_budget_exceeded")
        for tool_name in workflow.tools:
            tool = TOOL_REGISTRY[tool_name]
            if not workflow.roles.issubset(tool.roles):
                raise ValueError("workflow_tool_role_mismatch")


validate_registries()


__all__ = [
    "CATALOG_VERSION",
    "ROLE_WORKFLOWS",
    "TOOL_REGISTRY",
    "WORKFLOW_REGISTRY",
    "RouteDecision",
    "role_policy",
    "route_message",
    "validate_registries",
]
