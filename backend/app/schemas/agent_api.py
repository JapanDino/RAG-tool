from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
OPAQUE_REF_PATTERN = re.compile(r"^[A-Za-z0-9:_-]+$")


def _normalize_opaque(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not OPAQUE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("opaque identifier is invalid")
    return normalized


def _normalize_ref(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not OPAQUE_REF_PATTERN.fullmatch(normalized):
        raise ValueError("opaque reference is invalid")
    return normalized


class AgentSelectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_ref: str | None = Field(default=None, min_length=1, max_length=160)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=160)
    program_ref: str | None = Field(default=None, min_length=1, max_length=160)
    organization_ref: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("module_ref", "evidence_ref", "program_ref", "organization_ref")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        return _normalize_ref(value) if value is not None else None

    @model_validator(mode="after")
    def validate_resource_scope(self):
        selected_scopes = sum(
            value is not None for value in (self.program_ref, self.organization_ref)
        )
        if selected_scopes > 1:
            raise ValueError("resource selection scopes cannot be mixed")
        if (self.program_ref is not None or self.organization_ref is not None) and (
            self.module_ref is not None or self.evidence_ref is not None
        ):
            raise ValueError("organization selections cannot include course references")
        return self


class AgentMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    message: str
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)
    selection: AgentSelectionIn | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        if not 1 <= len(normalized) <= 4000:
            raise ValueError("message must contain 1-4000 characters")
        if any(unicodedata.category(char) == "Cc" for char in normalized):
            raise ValueError("message contains unsupported control characters")
        return normalized

    @field_validator("conversation_id", "client_request_id")
    @classmethod
    def validate_id(cls, value: str | None) -> str | None:
        return _normalize_opaque(value) if value is not None else None


class AgentAcceptedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    run_id: str
    conversation_id: str
    status: Literal["queued"]
    status_url: str
    events_url: str
    execute_url: str


class AgentUserStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    recovery_action: Literal["clarify_request", "choose_supported_task"] | None


class AgentWorkflowPlanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["workflow_plan"]
    workflow: str = Field(min_length=1, max_length=100)
    planned_steps: int = Field(ge=1, le=4)


class AgentEvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref: str = Field(min_length=1, max_length=128)
    kind: Literal["course_excerpt"]
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=700)
    module_title: str | None = Field(default=None, max_length=300)
    support: Literal["direct"]
    visibility: Literal["learner_published"]
    open_url: str | None = Field(default=None, min_length=1, max_length=240)
    source_label: str | None = Field(default=None, min_length=1, max_length=100)
    provenance: Literal["canvas", "external"] | None = None


class AgentConfidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: Literal["supported", "partial", "insufficient"]
    value: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1, max_length=300)


class AgentLearnerResponseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["answer", "guidance", "self_check", "abstained"]
    content: str = Field(min_length=1, max_length=6000)
    confidence: AgentConfidenceOut
    evidence: list[AgentEvidenceOut] = Field(max_length=8)
    feedback_url: str = Field(min_length=1, max_length=200)


class AgentFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["helpful", "unhelpful"]


class AgentFeedbackOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["helpful", "unhelpful"]


class AgentSourceActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["source_action"]
    title: str = Field(min_length=1, max_length=300)
    label: Literal["Открыть источник в Canvas", "Открыть внешний источник"]
    open_url: str = Field(min_length=1, max_length=200)
    provenance: Literal["canvas", "external"]


class AgentInstructorPriorityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ref: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    severity: Literal["info", "low", "medium", "high"]
    status: Literal["new", "confirmed", "rejected", "resolved", "ignored"]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str = Field(min_length=1, max_length=200)
    evidence_count: int = Field(ge=0, le=5)


class AgentInstructorHealthOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_state: Literal["missing", "queued", "running", "done", "failed"]
    findings_total: int = Field(ge=0)
    high_severity_findings: int = Field(ge=0)
    findings_reviewed: int = Field(ge=0)


class AgentInstructorCourseSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["course_summary"]
    course_title: str = Field(min_length=1, max_length=500)
    headline: str = Field(min_length=1, max_length=300)
    health: AgentInstructorHealthOut
    priorities: list[AgentInstructorPriorityOut] = Field(max_length=3)
    limitations: list[str] = Field(max_length=4)


class AgentInstructorEvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["course_excerpt"]
    source_label: str = Field(min_length=1, max_length=100)
    excerpt: str = Field(min_length=1, max_length=800)


class AgentInstructorFindingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["finding_review"]
    finding_ref: str = Field(min_length=40, max_length=40)
    title: str = Field(min_length=1, max_length=500)
    severity: Literal["info", "low", "medium", "high"]
    status: Literal["new", "confirmed", "rejected", "resolved", "ignored"]
    description: str = Field(min_length=1, max_length=6000)
    recommendation: str = Field(min_length=1, max_length=6000)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str = Field(min_length=1, max_length=200)
    evidence: list[AgentInstructorEvidenceOut] = Field(max_length=5)
    limitations: list[str] = Field(max_length=4)


class AgentInstructorGapOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_ref: str = Field(min_length=36, max_length=36)
    topic_label: str = Field(min_length=1, max_length=300)
    module_title: str | None = Field(default=None, max_length=300)
    signal_kind: Literal["repeated_unsupported", "low_helpfulness", "mixed"]
    signal_label: str = Field(min_length=1, max_length=120)
    cohort_band: Literal["3–5", "6–10", "11+"]
    event_band: Literal["3–5", "6–10", "11+"]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str = Field(min_length=1, max_length=120)
    evidence: AgentInstructorEvidenceOut


class AgentInstructorQuestionGapsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["question_gaps"]
    course_title: str = Field(min_length=1, max_length=500)
    window_days: Literal[30]
    privacy_threshold: str = Field(min_length=1, max_length=200)
    candidates: list[AgentInstructorGapOut] = Field(max_length=3)
    limitations: list[str] = Field(max_length=4)


class AgentInstructorInterventionDraftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["intervention_draft"]
    intervention_ref: str = Field(min_length=45, max_length=45)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=10, max_length=6000)
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[AgentInstructorEvidenceOut] = Field(min_length=1, max_length=3)
    signal_kind: Literal["repeated_unsupported", "low_helpfulness", "mixed"]
    cohort_band: Literal["3–5", "6–10", "11+"]
    event_band: Literal["3–5", "6–10", "11+"]
    review_status: Literal["draft", "accepted", "rejected"]
    review_version: int = Field(ge=1)
    limitations: list[str] = Field(max_length=4)


class AgentInstructorInterventionReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]
    expected_version: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=10, max_length=6000)


class AgentInstructorInterventionReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    mode: Literal["reviewed_intervention"]
    intervention_ref: str = Field(min_length=45, max_length=45)
    status: Literal["accepted", "rejected"]
    version: int = Field(ge=2)
    content: str = Field(min_length=10, max_length=6000)
    edit_distance_ratio: float = Field(ge=0.0, le=1.0)
    decision_latency_seconds: int = Field(ge=0)
    canvas_changed: Literal[False]


class AgentInstructorDraftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["improvement_draft"]
    draft_ref: str = Field(min_length=38, max_length=38)
    title: str = Field(min_length=1, max_length=500)
    action_type: Literal["create_material", "create_assessment", "revise_assessment"]
    target_bloom_level: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=10, max_length=6000)
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[AgentInstructorEvidenceOut] = Field(max_length=8)
    insufficient_context: bool
    review_status: Literal["draft", "accepted", "rejected"]
    review_version: int = Field(ge=1)
    limitations: list[str] = Field(max_length=4)


class AgentInstructorDraftReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]
    expected_version: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=10, max_length=6000)


class AgentInstructorDraftReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    mode: Literal["reviewed_draft"]
    draft_ref: str = Field(min_length=38, max_length=38)
    status: Literal["accepted", "rejected"]
    version: int = Field(ge=2)
    content: str = Field(min_length=10, max_length=6000)
    canvas_changed: Literal[False]


class AgentInstructorCanvasChangeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["canvas_change_preview"]
    change_set_ref: str = Field(min_length=39, max_length=39)
    course_title: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    operation: Literal["create_page", "create_assignment", "update_assignment"]
    ready_for_canvas: bool
    module_title: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=10, max_length=6000)
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: Literal["accepted"]
    warnings: list[str] = Field(max_length=4)
    read_only: Literal[True]


class AgentProgramOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_ref: str = Field(min_length=44, max_length=160)
    program_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class AgentProgramOptionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    programs: list[AgentProgramOptionOut] = Field(max_length=100)
    truncated: bool


class AgentProgramRouteCountsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: int = Field(ge=0)
    competencies: int = Field(ge=0)
    assessed_competencies: int = Field(ge=0)
    learning_only_competencies: int = Field(ge=0)
    unmapped_competencies: int = Field(ge=0)
    missing_evidence_cells: int = Field(ge=0)


class AgentProgramPriorityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "coverage_gap",
        "assessment_gap",
        "evidence_gap",
        "duplication_check",
        "sequence_check",
    ]
    attention: Literal["review", "watch"]
    title: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=1000)
    confidence: Literal["high", "medium"]
    confidence_label: str = Field(min_length=1, max_length=300)
    review_status: Literal["not_reviewed"]
    evidence_status: Literal["none", "declared", "missing"]
    evidence_count: int = Field(ge=0, le=8)
    evidence_truncated: bool


class AgentProgramRouteBriefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["program_route_brief"]
    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    headline: str = Field(min_length=1, max_length=300)
    counts: AgentProgramRouteCountsOut
    priorities: list[AgentProgramPriorityOut] = Field(max_length=3)
    analysis_truncated: bool
    findings_truncated: bool
    limitations: list[str] = Field(max_length=4)
    read_only: Literal[True]


class AgentProgramEvidenceAnchorOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    context: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(max_length=500)
    evidence_state: Literal["live", "manual", "missing"]
    review_label: str = Field(min_length=1, max_length=180)


class AgentProgramEvidenceCandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_key: str = Field(min_length=1, max_length=160)
    candidate_type: Literal[
        "coverage_gap",
        "assessment_gap",
        "evidence_gap",
        "duplication_check",
        "needs_evidence",
        "order_check",
        "declared_order",
    ]
    subject: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=1000)
    declared_rationale: str | None = Field(default=None, max_length=1000)
    confidence_label: str = Field(min_length=1, max_length=300)
    review_label: str = Field(min_length=1, max_length=240)
    evidence_status: Literal["none", "declared", "missing"]
    evidence: list[AgentProgramEvidenceAnchorOut] = Field(max_length=4)
    evidence_truncated: bool


class AgentProgramEvidenceRouteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["program_evidence_route"]
    route_kind: Literal["gap", "prerequisite"]
    state: Literal["candidate", "clear", "empty", "partial"]
    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    headline: str = Field(min_length=1, max_length=300)
    candidate: AgentProgramEvidenceCandidateOut | None
    analysis_truncated: bool
    action_target: Literal["audit", "prerequisites"]
    action_label: str = Field(min_length=1, max_length=120)
    limitations: list[str] = Field(min_length=1, max_length=4)
    read_only: Literal[True]


class AgentProgramSavedNoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_ref: str = Field(min_length=21, max_length=80)
    decision: Literal["act", "observe", "dismiss"]
    content: str = Field(min_length=40, max_length=2000)
    version: int = Field(ge=1)
    source_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{16}$")


class AgentProgramReviewDraftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["program_review_draft"]
    state: Literal["draft", "clear", "partial"]
    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    headline: str = Field(min_length=1, max_length=300)
    draft_ref: str | None = Field(default=None, min_length=40, max_length=200)
    candidate: AgentProgramEvidenceCandidateOut | None
    content: str | None = Field(default=None, min_length=40, max_length=2000)
    source_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{16}$")
    current_note: AgentProgramSavedNoteOut | None
    limitations: list[str] = Field(min_length=2, max_length=4)
    program_changed: Literal[False] = False
    canvas_changed: Literal[False] = False


class AgentAdminOrganizationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    organization_id: int = Field(gt=0)
    organization_name: str = Field(min_length=1, max_length=300)
    organization_ref: str = Field(min_length=1, max_length=160)


class AgentAdminStationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "canvas_configuration",
        "canvas_launch",
        "model_runtime",
        "data_retention",
    ]
    state: Literal["ready", "attention", "blocked", "not_started", "unavailable"]
    label: str = Field(min_length=1, max_length=180)
    detail: str = Field(min_length=1, max_length=500)
    evidence_window: str = Field(min_length=1, max_length=120)
    facts: list[str] = Field(min_length=1, max_length=3)
    action_target: Literal["registration", "pilot", "model", "retention"]


class AgentAdminPriorityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "canvas_configuration",
        "canvas_launch",
        "model_runtime",
        "data_retention",
    ]
    attention: Literal["blocker", "review", "continue"]
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(min_length=1, max_length=600)
    evidence_label: str = Field(min_length=1, max_length=180)
    action_target: Literal["registration", "pilot", "model", "retention"]
    action_label: str = Field(min_length=1, max_length=120)


class AgentAdminOperationsBriefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["admin_operations_brief"]
    organization_name: str = Field(min_length=1, max_length=300)
    overall_state: Literal["ready", "attention", "blocked", "not_started", "partial"]
    headline: str = Field(min_length=1, max_length=300)
    stations: list[AgentAdminStationOut] = Field(min_length=4, max_length=4)
    priorities: list[AgentAdminPriorityOut] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=4)
    read_only: Literal[True]


class AgentAdminAnalyticsSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["adoption", "runtime", "cost"]
    state: Literal[
        "available",
        "attention",
        "suppressed",
        "no_activity",
        "unconfigured",
        "unavailable",
    ]
    label: str = Field(min_length=1, max_length=180)
    detail: str = Field(min_length=1, max_length=500)
    current_window: str = Field(min_length=1, max_length=120)
    comparison_window: str = Field(min_length=1, max_length=120)
    trend: Literal["up", "down", "stable", "not_comparable"]
    current_facts: list[str] = Field(min_length=1, max_length=4)
    previous_facts: list[str] = Field(max_length=3)
    action_target: Literal["integration", "model"] | None
    action_label: str | None = Field(default=None, min_length=1, max_length=120)


class AgentAdminAnalyticsBriefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["admin_analytics_brief"]
    organization_name: str = Field(min_length=1, max_length=300)
    overall_state: Literal["available", "attention", "partial", "no_activity"]
    headline: str = Field(min_length=1, max_length=300)
    segments: list[AgentAdminAnalyticsSegmentOut] = Field(min_length=3, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=4)
    read_only: Literal[True]


class AgentAdminRetentionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["available", "unavailable"]
    source: Literal["default", "organization", "unavailable"]
    retention_days: Literal[30, 90, 180, 365] | None
    agent_metadata_retention_days: Literal[30]
    automatic_purge: bool | None
    student_self_delete: bool | None
    label: str = Field(min_length=1, max_length=180)
    detail: str = Field(min_length=1, max_length=500)


class AgentAdminPolicyVersionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["tutor_data", "agent_runtime"]
    label: str = Field(min_length=1, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=400)


class AgentAdminPurgeStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal[
        "current", "previous_policy", "recorded", "no_receipt", "unavailable"
    ]
    label: str = Field(min_length=1, max_length=180)
    detail: str = Field(min_length=1, max_length=600)
    recorded_at: datetime | None = None
    policy_version: int | None = Field(default=None, ge=0)
    facts: list[str] = Field(min_length=1, max_length=3)
    evidence_window: str = Field(min_length=1, max_length=180)


class AgentAdminPolicyStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["admin_policy_status"]
    organization_name: str = Field(min_length=1, max_length=300)
    overall_state: Literal["ready", "attention", "no_receipt", "partial"]
    headline: str = Field(min_length=1, max_length=300)
    retention: AgentAdminRetentionOut
    policy_versions: list[AgentAdminPolicyVersionOut] = Field(
        min_length=2, max_length=2
    )
    purge_status: AgentAdminPurgeStatusOut
    action_label: str = Field(min_length=1, max_length=120)
    limitations: list[str] = Field(min_length=1, max_length=4)
    read_only: Literal[True]


class AgentRunOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    run_id: str
    conversation_id: str
    workflow: str | None
    status: Literal[
        "queued",
        "routing",
        "tool_running",
        "generating",
        "completed",
        "abstained",
        "failed",
    ]
    route_state: Literal["routed", "clarification_required", "unsupported"]
    user_state: AgentUserStateOut
    response: (
        AgentWorkflowPlanOut
        | AgentLearnerResponseOut
        | AgentSourceActionOut
        | AgentInstructorCourseSummaryOut
        | AgentInstructorFindingOut
        | AgentInstructorQuestionGapsOut
        | AgentInstructorInterventionDraftOut
        | AgentInstructorDraftOut
        | AgentInstructorCanvasChangeOut
        | AgentProgramRouteBriefOut
        | AgentProgramEvidenceRouteOut
        | AgentProgramReviewDraftOut
        | AgentAdminOperationsBriefOut
        | AgentAdminAnalyticsBriefOut
        | AgentAdminPolicyStatusOut
        | None
    )
    review: None = None
    created_at: datetime
    updated_at: datetime


class AgentEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    run_id: str
    sequence: int = Field(ge=1, le=100)
    type: Literal[
        "run.accepted",
        "run.routing",
        "run.tool_running",
        "run.generating",
        "run.completed",
        "run.abstained",
        "run.failed",
    ]
    occurred_at: datetime
    payload: dict[str, str]


class AgentEventsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent.v1"]
    run_id: str
    events: list[AgentEventOut] = Field(max_length=100)


__all__ = [
    "AgentAcceptedOut",
    "AgentFeedbackIn",
    "AgentFeedbackOut",
    "AgentEventsOut",
    "AgentMessageIn",
    "AgentRunOut",
]
