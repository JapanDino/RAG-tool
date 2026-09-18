from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .copilot import CopilotCitationOut

CanvasOperation = Literal["create_page", "create_assignment", "update_assignment"]


class CanvasChangeItemOut(BaseModel):
    suggestion_id: int
    finding_id: int
    audit_run_id: int
    action_type: str
    operation: CanvasOperation
    api_method: Literal["POST", "PUT"]
    api_path: str
    ready_for_canvas: bool
    module_external_id: str | None = None
    module_title: str | None = None
    target_external_id: str | None = None
    target_url: str | None = None
    title: str
    body: str
    target_bloom_level: str
    rationale: str
    citations: list[CopilotCitationOut] = Field(default_factory=list)
    confidence: float
    warning: str | None = None


class CanvasChangeSetOut(BaseModel):
    available: bool
    reason: str | None = None
    course_id: int
    canvas_course_id: str | None = None
    course_title: str
    source_url: str | None = None
    generated_at: datetime
    accepted_suggestions: int = 0
    ready_items: int = 0
    items: list[CanvasChangeItemOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
