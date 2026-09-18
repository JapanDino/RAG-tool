from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DevelopmentLtiBootstrapIn(BaseModel):
    course_id: int
    public_base_url: str = Field(
        default="http://localhost:8000", min_length=1, max_length=1000
    )


class DevelopmentLtiBootstrapOut(BaseModel):
    registration_id: int
    bound_users: int
    chooser_url: str


class DevelopmentSimulatorBootstrapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lti_base_url: str = Field(
        default="http://localhost:8000", min_length=1, max_length=1000
    )
    canvas_base_url: str = Field(
        default="http://localhost:3000", min_length=1, max_length=1000
    )


class DevelopmentSimulatorCourseOut(BaseModel):
    fixture_id: Literal["demo-ai", "demo-review"]
    course_id: int
    registration_id: int
    learner_subject: str
    instructor_subject: str
    launch_url: str
    instructor_launch_url: str
    chooser_url: str


class DevelopmentSimulatorBootstrapOut(BaseModel):
    version: Literal["1"] = "1"
    organization_id: int
    learner_email: str
    instructor_email: str
    courses: list[DevelopmentSimulatorCourseOut]
    registration_map: dict[str, int]


class DevelopmentSimulatorLaunchOut(BaseModel):
    fixture_id: Literal["demo-ai", "demo-review"]
    course_id: int
    registration_id: int
    actor: Literal["learner", "instructor"]
    subject: str
    launch_url: str
    chooser_url: str


class LtiRegistrationDraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: str = Field(min_length=1, max_length=1000)
    client_id: str = Field(min_length=1, max_length=255)
    deployment_id: str = Field(min_length=1, max_length=255)
    authorization_endpoint: str = Field(min_length=1, max_length=2000)
    jwks_url: str = Field(min_length=1, max_length=2000)


class LtiRegistrationUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: str | None = Field(default=None, min_length=1, max_length=1000)
    client_id: str | None = Field(default=None, min_length=1, max_length=255)
    deployment_id: str | None = Field(default=None, min_length=1, max_length=255)
    authorization_endpoint: str | None = Field(
        default=None, min_length=1, max_length=2000
    )
    jwks_url: str | None = Field(default=None, min_length=1, max_length=2000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("at least one change is required")
        return self


class LtiRegistrationOut(BaseModel):
    id: int
    organization_id: int
    issuer: str
    client_id: str
    deployment_id: str
    authorization_endpoint: str
    jwks_url: str
    tool_launch_url: str
    is_active: bool
    subject_binding_count: int
    context_binding_count: int
    verified_launch_count: int
    last_verified_launch_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LtiRegistrationReadinessOut(BaseModel):
    configuration_ready: bool
    production_ready: bool
    blockers: list[str]
    warnings: list[str]
    public_origin: str | None
    configuration_url: str | None
    login_url: str | None
    launch_url: str | None
    jwks_url: str | None
    key_ids: list[str]
    canvas_configuration: dict[str, Any] | None


class LtiBindingCandidateOut(BaseModel):
    id: int
    candidate_type: Literal["subject", "context"]
    identifier_hint: str
    seen_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class LtiBindingUserTargetOut(BaseModel):
    id: int
    display_name: str
    email: str
    organization_role: str


class LtiBindingCourseTargetOut(BaseModel):
    id: int
    title: str


class LtiBindingReadinessOut(BaseModel):
    registration_id: int
    registration_active: bool
    candidates: list[LtiBindingCandidateOut]
    users: list[LtiBindingUserTargetOut]
    courses: list[LtiBindingCourseTargetOut]


class LtiBindingCandidateResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: int = Field(gt=0)


class LtiBindingCandidateResolutionOut(BaseModel):
    candidate_id: int
    candidate_type: Literal["subject", "context"]
    status: Literal["bound", "dismissed"]
    target_id: int | None


class LtiPilotFailureFamilyOut(BaseModel):
    code: Literal[
        "binding_required",
        "platform_configuration",
        "signature_or_replay",
        "other",
    ]
    count: int = Field(ge=1)


class LtiPilotPendingBindingsOut(BaseModel):
    total: int = Field(ge=0)
    subjects: int = Field(ge=0)
    contexts: int = Field(ge=0)


class LtiPilotHealthOut(BaseModel):
    schema_version: Literal[1]
    window_days: Literal[7]
    state: Literal[
        "not_started",
        "stable",
        "review_bindings",
        "review_failures",
    ]
    known_launches: int = Field(ge=0)
    accepted_launches: int = Field(ge=0)
    rejected_launches: int = Field(ge=0)
    active_registrations: int = Field(ge=0)
    pending_bindings: LtiPilotPendingBindingsOut
    failure_families: list[LtiPilotFailureFamilyOut]
    pause_triggers: list[Literal["no_verified_launch", "repeated_rejections"]]
    last_known_launch_at: datetime | None
    generated_at: datetime
