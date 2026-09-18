from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CopilotAction = Literal["create_material", "create_assessment", "revise_assessment"]


class CopilotRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=8)
    language: Literal["ru", "en"] = "ru"


class CopilotCitationOut(BaseModel):
    source_id: str
    chunk_id: int
    document_id: int
    document_title: str
    module_id: int | None = None
    module_title: str | None = None
    quote: str
    source_url: str | None = None
    score: float = Field(ge=0.0, le=1.0)


class CopilotSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    finding_id: int
    action_type: CopilotAction
    title: str
    draft: str
    target_bloom_level: str
    rationale: str
    citations: list[CopilotCitationOut]
    confidence: float = Field(ge=0.0, le=1.0)
    retrieval_method: str
    generation_provider: str
    generation_model: str | None = None
    insufficient_context: bool = False
    status: Literal["draft", "accepted", "rejected"] = "draft"
    version: int = Field(default=1, ge=1)
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None


class CopilotSuggestionReviewIn(BaseModel):
    status: Literal["accepted", "rejected"]
    reviewed_by: str | None = Field(default=None, min_length=1, max_length=255)
    draft: str | None = Field(default=None, min_length=10, max_length=6000)


class CourseQuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=8)
    language: Literal["ru", "en"] = "ru"
    module_id: int | None = Field(default=None, ge=1)


class CourseAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    course_id: int
    question: str
    answer: str
    citations: list[CopilotCitationOut]
    confidence: float = Field(ge=0.0, le=1.0)
    retrieval_method: str
    generation_provider: str
    generation_model: str | None = None
    insufficient_context: bool = False
    response_mode: Literal["answer", "guidance", "abstained"] = "answer"
    policy_reason: str | None = None
    tutor_policy_version: int = 0
    tutor_answer_style: Literal["balanced", "guided", "concise"] = "balanced"
    feedback_status: Literal["unreviewed", "helpful", "unhelpful"] = "unreviewed"
    feedback_comment: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None


class CourseAnswerReviewIn(BaseModel):
    status: Literal["helpful", "unhelpful"]
    reviewed_by: str | None = Field(default=None, min_length=1, max_length=255)
    comment: str | None = Field(default=None, max_length=2000)


class CourseQaFeedbackEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    answer_id: int
    course_id: int
    from_status: str
    to_status: str
    reviewed_by: str | None = None
    comment: str | None = None
    created_at: datetime | None = None
