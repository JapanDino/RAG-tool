from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentModelMode = Literal[
    "approved_host_with_safe_fallback",
    "deterministic_only",
]


class AgentPolicySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learner_enabled: bool = True
    instructor_enabled: bool = True
    program_enabled: bool = True
    model_mode: AgentModelMode = "approved_host_with_safe_fallback"


class OrganizationAgentPolicyOut(AgentPolicySettings):
    organization_id: int
    version: int = 0
    updated_at: datetime | None = None
    safety_boundaries: list[str] = Field(
        default_factory=lambda: [
            "evidence_required",
            "hidden_conversation_memory_disabled",
            "canvas_writes_disabled",
            "individual_surveillance_disabled",
        ]
    )


class OrganizationAgentPolicyDraftIn(AgentPolicySettings):
    expected_version: int = Field(ge=0)


class OrganizationAgentPolicyUpdateIn(OrganizationAgentPolicyDraftIn):
    confirmation: Literal["apply_agent_policy"]


class AgentPolicyChangeOut(BaseModel):
    field: Literal[
        "learner_enabled",
        "instructor_enabled",
        "program_enabled",
        "model_mode",
    ]
    label: str
    before: str
    after: str
    impact: str


class OrganizationAgentPolicyPreviewOut(BaseModel):
    current: OrganizationAgentPolicyOut
    proposed: AgentPolicySettings
    changes: list[AgentPolicyChangeOut]
    confirmation: Literal["apply_agent_policy"] = "apply_agent_policy"
