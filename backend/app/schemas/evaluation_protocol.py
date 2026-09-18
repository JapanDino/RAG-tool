from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCheckOut(BaseModel):
    check_id: str
    label: str
    value: float | int | None = None
    threshold: float | int | None = None
    operator: str
    passed: bool | None = None
    required: bool = True
    notes: str = ""


class CourseEvaluationProtocolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    status: Literal["passed", "failed", "error"]
    protocol_version: str
    dataset_name: str
    dataset_hash: str
    thresholds: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    checks: list[EvaluationCheckOut] = Field(default_factory=list)
    methodology: list[str] = Field(default_factory=list)
    duration_ms: float
    error: str | None = None
    created_at: datetime | None = None
