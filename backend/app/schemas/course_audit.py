from datetime import datetime
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
)

from .copilot import CopilotSuggestionOut

SourceType = Literal["manual", "file_upload", "canvas"]
ReviewStatus = Literal["unreviewed", "confirmed", "rejected", "edited"]
FindingStatus = Literal["new", "confirmed", "rejected", "resolved", "ignored"]
FindingSeverity = Literal["info", "low", "medium", "high"]


class CourseModuleCreate(BaseModel):
    external_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    position: int = Field(default=0, ge=0)
    source_url: str | None = None
    metadata: dict = Field(default_factory=dict)


class CourseModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    course_id: int
    external_id: str | None = None
    title: str
    description: str
    position: int
    source_url: str | None = None
    metadata: dict = Field(
        default_factory=dict, validation_alias=AliasChoices("meta", "metadata")
    )


class CourseCreate(BaseModel):
    organization_id: int | None = Field(default=None, ge=1)
    dataset_id: int | None = None
    external_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    source_type: SourceType = "manual"
    source_url: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    modules: list[CourseModuleCreate] = Field(default_factory=list)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    source_url: str | None = None
    source_metadata: dict | None = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None = None
    dataset_id: int
    external_id: str | None = None
    title: str
    description: str
    source_type: SourceType
    source_url: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CourseDetailOut(CourseOut):
    modules: list[CourseModuleOut] = Field(default_factory=list)


class CourseDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    course_module_id: int | None = None
    title: str
    source: str
    mime: str
    status: str
    external_id: str | None = None
    content_hash: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    job_id: int | None = None
    duplicate: bool = False


class DemoCourseOut(BaseModel):
    course_id: int
    audit_run_id: int
    created: bool


class AuditRunCreate(BaseModel):
    config: dict = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_audit_config(cls, value: dict) -> dict:
        config = dict(value)
        threshold = float(config.get("min_relation_score", 0.22))
        top_k = int(config.get("top_k", 5))
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("min_relation_score must be between 0 and 1")
        if not 1 <= top_k <= 50:
            raise ValueError("top_k must be between 1 and 50")
        config["min_relation_score"] = threshold
        config["top_k"] = top_k
        source_id = config.get("calibration_source_audit_id")
        if source_id is not None:
            config["calibration_source_audit_id"] = int(source_id)
        return config


class AuditRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    status: str
    pipeline_version: str
    extractor_version: str
    classifier_version: str
    embedding_model: str
    relation_model: str
    config: dict
    metrics: dict
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class AuditStartOut(BaseModel):
    audit_run_id: int
    job_id: int
    status: str


class LearningObjectiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    module_id: int | None = None
    document_id: int | None = None
    audit_run_id: int | None = None
    text: str
    normalized_text: str
    bloom_vector: list
    top_bloom_levels: list
    source_start: int | None = None
    source_end: int | None = None
    source_page: int | None = None
    extraction_method: str
    confidence: float
    model_info: dict
    review_status: str


class LearningMaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    course_id: int
    module_id: int | None = None
    document_id: int | None = None
    audit_run_id: int | None = None
    material_type: str
    title: str
    source_url: str | None = None
    source_text: str
    metadata: dict = Field(
        default_factory=dict, validation_alias=AliasChoices("meta", "metadata")
    )


class AssessmentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    module_id: int | None = None
    document_id: int | None = None
    audit_run_id: int | None = None
    external_id: str | None = None
    assessment_type: str
    title: str
    text: str
    expected_answer: str | None = None
    bloom_vector: list
    top_bloom_levels: list
    source_start: int | None = None
    source_end: int | None = None
    source_page: int | None = None
    extraction_method: str
    confidence: float
    model_info: dict
    review_status: str


class AlignmentEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    audit_run_id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    relation_type: str
    score: float
    evidence: list
    method: str
    model_info: dict
    review_status: str
    created_at: datetime | None = None


class FindingReviewIn(BaseModel):
    status: FindingStatus
    reviewed_by: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("status")
    @classmethod
    def require_review_state(cls, value: str) -> str:
        if value == "new":
            raise ValueError("review cannot reset a finding to new")
        return value


class CourseFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    module_id: int | None = None
    audit_run_id: int
    finding_type: str
    severity: FindingSeverity
    title: str
    description: str
    evidence: list
    recommendation: str
    confidence: float
    uncertainty_reasons: list
    status: FindingStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    model_info: dict
    created_at: datetime | None = None


class AuditReportOut(BaseModel):
    audit: AuditRunOut
    summary: dict
    findings: list[CourseFindingOut]
    copilot_suggestions: list[CopilotSuggestionOut] = Field(default_factory=list)


class AuditComparisonSnapshot(BaseModel):
    audit_run_id: int
    summary: dict = Field(default_factory=dict)
    finding_types: dict[str, int] = Field(default_factory=dict)


class AuditComparisonOut(BaseModel):
    available: bool
    before: AuditComparisonSnapshot | None = None
    after: AuditComparisonSnapshot | None = None
    delta: dict[str, float | int] = Field(default_factory=dict)
    new_findings: int = 0
    removed_findings: int = 0
    persisted_findings: int = 0


class FindingReviewEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int
    course_id: int
    audit_run_id: int
    from_status: str
    to_status: str
    reviewed_by: str
    created_at: datetime | None = None


class CanvasImportIn(BaseModel):
    base_url: HttpUrl
    access_token: SecretStr
    canvas_course_id: int = Field(ge=1)


class CanvasImportOut(BaseModel):
    course_id: int
    dataset_id: int
    modules_imported: int
    documents_created: int
    documents_updated: int
    explicit_alignments_imported: int = 0
    source_url: str | None = None


class CanvasAlignmentPairOut(BaseModel):
    outcome_external_id: str
    assignment_external_id: str
    outcome_text: str | None = None
    assignment_title: str | None = None


class CanvasAlignmentEvaluationOut(BaseModel):
    available: bool
    explicit_pairs: int = 0
    inferred_pairs: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    mapping_coverage: float = 0.0
    matched: list[CanvasAlignmentPairOut] = Field(default_factory=list)
    missing_in_inference: list[CanvasAlignmentPairOut] = Field(default_factory=list)
    inferred_only: list[CanvasAlignmentPairOut] = Field(default_factory=list)
    unmapped_explicit: list[CanvasAlignmentPairOut] = Field(default_factory=list)


class ThresholdMetricOut(BaseModel):
    threshold: float
    inferred_pairs: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


class CanvasAlignmentCalibrationOut(BaseModel):
    available: bool
    reason: str | None = None
    current_threshold: float | None = None
    current: ThresholdMetricOut | None = None
    recommended_threshold: float | None = None
    recommended: ThresholdMetricOut | None = None
    top_k: int = 5
    labeled_positive_pairs: int = 0
    comparable_candidates: int = 0
    mapping_coverage: float = 0.0
    reliable: bool = False
    caveat: str = ""
    curve: list[ThresholdMetricOut] = Field(default_factory=list)
