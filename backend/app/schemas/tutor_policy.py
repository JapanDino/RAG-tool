from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TutorAnswerStyle = Literal["balanced", "guided", "concise"]


class TutorSafetyOut(BaseModel):
    student_visible_content_only: bool = True
    assessment_guard: bool = True
    abstain_without_support: bool = True
    citations_required: bool = True


class TutorPolicyOut(BaseModel):
    course_id: int
    enabled: bool = True
    answer_style: TutorAnswerStyle = "balanced"
    version: int = 0
    safety: TutorSafetyOut = Field(default_factory=TutorSafetyOut)
    updated_at: datetime | None = None


class TutorPolicyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    answer_style: TutorAnswerStyle
    expected_version: int = Field(ge=0)
