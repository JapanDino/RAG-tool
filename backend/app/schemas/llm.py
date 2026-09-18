from typing import Literal

from pydantic import BaseModel, Field, ValidationError

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class LLMAnnotation(BaseModel):
    level: BloomLevel
    label: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=4000)
    score: float = Field(ge=0.0, le=1.0)


__all__ = ["LLMAnnotation", "BloomLevel", "ValidationError"]
