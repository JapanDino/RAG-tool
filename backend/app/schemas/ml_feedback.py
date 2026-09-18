from datetime import datetime

from pydantic import BaseModel, Field


class MlFeedbackSummaryOut(BaseModel):
    course_id: int
    generated_at: datetime
    total_examples: int
    positive_examples: int
    negative_examples: int
    by_type: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
