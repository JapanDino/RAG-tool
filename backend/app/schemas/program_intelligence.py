from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ContributionStage = Literal["introduced", "developed", "assessed"]
EvidenceType = Literal["learning_objective", "assessment_item", "manual_note"]
EvidenceState = Literal["live", "manual", "missing"]
CoverageState = Literal["unmapped", "learning_only", "assessed"]
ProgramAuditKind = Literal[
    "coverage_gap",
    "assessment_gap",
    "evidence_gap",
    "duplication_check",
    "sequence_check",
]
ProgramAuditAttention = Literal["review", "watch"]
ProgramAdministrationState = Literal[
    "not_started",
    "mapping_gap",
    "assessment_gap",
    "declared_assessment_complete",
]
PrerequisiteStructuralState = Literal["needs_evidence", "order_check", "declared_order"]


class ProgramCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=4000)


class ProgramSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    code: str
    title: str
    description: str
    version: int
    is_active: bool
    competency_count: int = 0
    course_count: int = 0
    assessed_competency_count: int = 0
    updated_at: datetime | None = None


class CompetencyCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    code: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=4000)
    position: int = Field(default=0, ge=0, le=10000)


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    program_id: int
    code: str
    title: str
    description: str
    position: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    program_version: int


class CourseContributionUpsertIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    competency_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_position: int = Field(ge=1, le=500)
    stage: ContributionStage
    rationale: str = Field(min_length=10, max_length=4000)
    evidence_type: EvidenceType
    evidence_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_evidence_reference(self):
        if self.evidence_type == "manual_note" and self.evidence_id is not None:
            raise ValueError("manual evidence cannot have an evidence_id")
        if self.evidence_type != "manual_note" and self.evidence_id is None:
            raise ValueError("live course evidence requires evidence_id")
        return self


class ProgramCourseOut(BaseModel):
    id: int
    title: str
    position: int


class ProgramCourseOrderIn(BaseModel):
    expected_version: int = Field(ge=1)
    course_ids: list[int] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_courses(self):
        if any(course_id <= 0 for course_id in self.course_ids):
            raise ValueError("course ids must be positive")
        if len(set(self.course_ids)) != len(self.course_ids):
            raise ValueError("course ids must be unique")
        return self


class ProgramCourseOrderOut(BaseModel):
    courses: list[ProgramCourseOut]
    program_version: int
    changed: bool


class ProgramAuthoringCourseOut(BaseModel):
    id: int
    title: str
    description: str
    in_program: bool
    position: int | None = None


class ProgramAuthoringContextOut(BaseModel):
    program_id: int
    program_version: int
    courses: list[ProgramAuthoringCourseOut]
    courses_truncated: bool


class ProgramEvidenceOptionOut(BaseModel):
    evidence_type: Literal["learning_objective", "assessment_item"]
    evidence_id: int
    label: str
    excerpt: str
    confidence: float | None = None
    review_status: str


class ProgramEvidenceOptionsOut(BaseModel):
    course_id: int
    options: list[ProgramEvidenceOptionOut]
    options_truncated: bool


class ContributionEvidenceOut(BaseModel):
    state: EvidenceState
    evidence_type: EvidenceType
    evidence_id: int | None = None
    label: str
    excerpt: str
    confidence: float | None = None
    review_status: str


class CourseContributionOut(BaseModel):
    id: int
    program_id: int
    competency_id: int
    course_id: int
    stage: ContributionStage
    rationale: str
    evidence: ContributionEvidenceOut
    updated_at: datetime | None = None
    program_version: int


class CompetencyMapOut(BaseModel):
    id: int
    code: str
    title: str
    description: str
    position: int
    coverage_state: CoverageState
    contributions: list[CourseContributionOut]


class PrerequisiteRelationUpsertIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    prerequisite_competency_id: int = Field(gt=0)
    target_competency_id: int = Field(gt=0)
    rationale: str = Field(min_length=10, max_length=4000)


class PrerequisiteRelationDeleteIn(BaseModel):
    expected_version: int = Field(ge=1)


class PrerequisiteRelationMutationOut(BaseModel):
    relation_id: int
    program_version: int
    changed: bool


class PrerequisiteEvidenceOut(BaseModel):
    contribution_id: int
    competency_id: int
    course_id: int
    course_title: str
    course_position: int
    stage: ContributionStage
    evidence_state: EvidenceState
    evidence_label: str
    evidence_excerpt: str
    evidence_review_status: str


class PrerequisiteRelationOut(BaseModel):
    id: int
    program_id: int
    prerequisite_competency_id: int
    prerequisite_competency_code: str
    prerequisite_competency_title: str
    target_competency_id: int
    target_competency_code: str
    target_competency_title: str
    rationale: str
    structural_state: PrerequisiteStructuralState
    structural_state_label: str
    confidence_label: Literal["Явная связь — порядок по сохранённой карте"] = (
        "Явная связь — порядок по сохранённой карте"
    )
    prerequisite_assessment: PrerequisiteEvidenceOut | None = None
    target_start: PrerequisiteEvidenceOut | None = None
    updated_at: datetime | None = None


class ProgramMapCountsOut(BaseModel):
    competencies: int
    courses: int
    mapped_cells: int
    assessed_competencies: int
    learning_only_competencies: int
    unmapped_competencies: int
    missing_evidence_cells: int


class ProgramMapOut(BaseModel):
    program: ProgramSummaryOut
    courses: list[ProgramCourseOut]
    competencies: list[CompetencyMapOut]
    prerequisites: list[PrerequisiteRelationOut]
    prerequisites_truncated: bool
    counts: ProgramMapCountsOut


class ProgramAuditEvidenceOut(BaseModel):
    contribution_id: int
    course_id: int
    course_title: str
    course_position: int
    stage: ContributionStage
    rationale: str
    evidence_state: EvidenceState
    evidence_type: EvidenceType
    evidence_label: str
    evidence_excerpt: str
    evidence_confidence: float | None = None
    evidence_review_status: str


class ProgramAuditFindingOut(BaseModel):
    key: str
    kind: ProgramAuditKind
    attention: ProgramAuditAttention
    competency_id: int
    competency_code: str
    competency_title: str
    title: str
    detail: str
    confidence: Literal["high", "medium"]
    confidence_label: str
    review_status: Literal["not_reviewed"] = "not_reviewed"
    evidence_status: Literal["none", "declared", "missing"]
    evidence_truncated: bool = False
    evidence: list[ProgramAuditEvidenceOut]


class ProgramAuditCountsOut(BaseModel):
    total: int
    review: int
    watch: int
    coverage_gap: int
    assessment_gap: int
    evidence_gap: int
    duplication_check: int
    sequence_check: int


class ProgramAuditPreviewOut(BaseModel):
    program_id: int
    program_version: int
    analyzed_competencies: int
    analyzed_contributions: int
    analysis_truncated: bool
    findings_truncated: bool
    counts: ProgramAuditCountsOut
    findings: list[ProgramAuditFindingOut]


class ProgramReviewNoteSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_ref: str = Field(
        min_length=40,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    decision: Literal["act", "observe", "dismiss"]
    content: str = Field(min_length=40, max_length=2000)
    expected_version: int = Field(ge=0)
    confirmation: Literal["save_program_review_note"]


class ProgramReviewNoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_ref: str = Field(min_length=21, max_length=80)
    program_id: int = Field(gt=0)
    finding_key: str = Field(min_length=1, max_length=160)
    finding_kind: Literal[
        "coverage_gap",
        "assessment_gap",
        "evidence_gap",
        "duplication_check",
    ]
    decision: Literal["act", "observe", "dismiss"]
    content: str = Field(min_length=40, max_length=2000)
    version: int = Field(ge=1)
    source_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{16}$")
    created_at: datetime
    updated_at: datetime
    program_changed: Literal[False] = False
    canvas_changed: Literal[False] = False


class ProgramAdministrationItemOut(BaseModel):
    program_id: int
    program_code: str
    program_title: str
    program_version: int
    updated_at: datetime | None = None
    course_count: int
    competency_count: int
    mapped_competency_count: int
    assessed_competency_count: int
    unmapped_competency_count: int
    without_assessment_count: int
    route_state: ProgramAdministrationState
    route_state_label: str
    confidence_label: Literal["Факт по сохранённой карте"] = "Факт по сохранённой карте"
    review_status: Literal["not_reviewed"] = "not_reviewed"


class ProgramAdministrationTotalsOut(BaseModel):
    programs: int
    courses: int
    competencies: int
    mapped_competencies: int
    assessed_competencies: int
    programs_requiring_review: int
    programs_not_started: int


class ProgramAdministrationOverviewOut(BaseModel):
    organization_id: int
    analysis_truncated: bool
    totals: ProgramAdministrationTotalsOut
    programs: list[ProgramAdministrationItemOut]


class ProgramDemoOut(BaseModel):
    program_id: int
    created: bool
    courses_created: int
    competencies_created: int
    contributions_created: int
