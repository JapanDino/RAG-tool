from pydantic import BaseModel, Field


class EvidenceArtifactOut(BaseModel):
    name: str
    included: bool
    description: str


class EvidencePackPreviewOut(BaseModel):
    course_id: int
    completeness_score: int = Field(ge=0, le=100)
    ready_for_submission: bool
    latest_audit_id: int | None = None
    latest_protocol_id: int | None = None
    artifacts: list[EvidenceArtifactOut] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
