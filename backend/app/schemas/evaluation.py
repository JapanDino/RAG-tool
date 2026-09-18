from pydantic import BaseModel, Field


class ExtractionEvaluationSet(BaseModel):
    predicted: list[str] = Field(default_factory=list)
    expected: list[str] = Field(default_factory=list)


class CourseAuditEvaluationIn(BaseModel):
    objectives: ExtractionEvaluationSet
    assessments: ExtractionEvaluationSet
    predicted_relations: list[str] = Field(default_factory=list)
    expected_relations: list[str] = Field(default_factory=list)
    predicted_findings: list[str] = Field(default_factory=list)
    expected_findings: list[str] = Field(default_factory=list)
    similarity_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
