from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelRuntimeCountsOut(BaseModel):
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    fallback: int = Field(ge=0)
    failed: int = Field(ge=0)
    p95_latency_ms: int | None = Field(default=None, ge=0)


class AgentModelReadinessOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    state: Literal[
        "disabled",
        "setup_required",
        "misconfigured",
        "configured",
        "degraded",
        "ready",
    ]
    available: bool
    label: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)
    recovery_action: (
        Literal[
            "configure_model_host",
            "check_model_host",
            "wait_and_retry",
        ]
        | None
    )
    window_minutes: Literal[30]
    counts: ModelRuntimeCountsOut
    last_invocation_at: datetime | None


class CompatibilityProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class CompatibilityProbeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    detail: str = Field(min_length=1, max_length=200)


__all__ = [
    "AgentModelReadinessOut",
    "CompatibilityProbeInput",
    "CompatibilityProbeOutput",
    "ModelRuntimeCountsOut",
]
