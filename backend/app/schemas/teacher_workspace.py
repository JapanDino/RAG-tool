from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .tutor_policy import TutorPolicyOut

ConfidenceBand = Literal["strong", "review", "weak"]
ThreadFocus = Literal["objective_material", "objective_assessment", "whole_course"]
TutorQualitySignal = Literal[
    "empty", "early", "coverage", "review", "limited", "steady"
]


class TeacherCourseOut(BaseModel):
    id: int
    title: str
    description: str
    source_type: str


class TeacherAuditOut(BaseModel):
    id: int
    status: str
    progress: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None
    failure_message: str | None = None


class TeacherHealthOut(BaseModel):
    objectives_total: int = 0
    materials_total: int = 0
    assessments_total: int = 0
    objective_material_coverage: float = 0.0
    objective_assessment_coverage: float = 0.0
    findings_total: int = 0
    high_severity_findings: int = 0
    findings_reviewed: int = 0


class TutorQualityOut(BaseModel):
    period_days: int = 30
    minimum_feedback_sample: int = 3
    signal: TutorQualitySignal = "empty"
    questions_total: int = 0
    answer_responses: int = 0
    supported_answers: int = 0
    guidance_answers: int = 0
    abstained_answers: int = 0
    answers_needing_review: int = 0
    rated_answers: int = 0
    helpful_answers: int | None = None
    helpful_rate: float | None = None


class EvidenceExcerptOut(BaseModel):
    object_type: str
    object_id: int | None = None
    document_id: int | None = None
    quote: str = Field(max_length=800)
    source_start: int | None = None
    source_end: int | None = None


class AttentionFindingOut(BaseModel):
    id: int
    finding_type: str
    severity: str
    status: str
    title: str
    description: str
    recommendation: str
    confidence: float
    confidence_band: ConfidenceBand
    confidence_label: str
    attention_label: str
    thread_focus: ThreadFocus
    evidence: list[EvidenceExcerptOut]
    uncertainty_reasons: list[str]
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class TeacherWorkspaceOut(BaseModel):
    course: TeacherCourseOut
    latest_audit: TeacherAuditOut | None = None
    health: TeacherHealthOut
    tutor_quality: TutorQualityOut
    tutor_policy: TutorPolicyOut
    findings: list[AttentionFindingOut]
