from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ModelCompatibilityProfileId = Literal[
    "deepseek_openai_v1",
    "gemma_openai_v1",
]
ModelPreflightStatus = Literal[
    "configuration_required",
    "configuration_blocked",
    "ready_for_credentialed_probe",
]
ModelPreflightCheckStatus = Literal["passed", "blocked", "external"]
OrganizationModelRouteState = Literal[
    "allowed",
    "deterministic_only",
    "not_assessed",
]


class ModelCompatibilityProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ModelCompatibilityProfileId
    label: str = Field(min_length=1, max_length=80)
    contract: Literal["openai_chat_completions_v1"]
    summary: str = Field(min_length=1, max_length=240)


class ModelPreflightCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9_]{3,80}$")
    status: ModelPreflightCheckStatus
    owner: Literal["application", "system_administrator"]
    label: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=360)


class ModelHostPreflightOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    profile: ModelCompatibilityProfileOut
    available_profiles: list[ModelCompatibilityProfileOut] = Field(
        min_length=2, max_length=2
    )
    status: ModelPreflightStatus
    configuration_state: Literal[
        "disabled",
        "setup_required",
        "misconfigured",
        "configured",
    ]
    organization_model_route: OrganizationModelRouteState
    network_probe_performed: Literal[False] = False
    credentials_included: Literal[False] = False
    course_data_used: Literal[False] = False
    checks: list[ModelPreflightCheckOut] = Field(min_length=8, max_length=16)
    required_server_fields: list[str] = Field(min_length=6, max_length=20)
    operator_command: str = Field(min_length=1, max_length=240)
    limitations: list[str] = Field(min_length=3, max_length=8)
    bundle_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{16}$")


__all__ = [
    "ModelCompatibilityProfileId",
    "ModelCompatibilityProfileOut",
    "ModelHostPreflightOut",
    "ModelPreflightCheckOut",
    "ModelPreflightStatus",
    "OrganizationModelRouteState",
]
