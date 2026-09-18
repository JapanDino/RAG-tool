from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TutorRetentionDays = Literal[30, 90, 180, 365]
TutorDeletionReason = Literal["student_request", "automatic_retention", "admin_purge"]


class TutorDataPolicyOut(BaseModel):
    organization_id: int
    course_id: int | None = None
    retention_days: TutorRetentionDays = 90
    version: int = 0
    automatic_purge: bool = True
    student_self_delete: bool = True
    updated_at: datetime | None = None


class TutorDataPolicyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: TutorRetentionDays
    expected_version: int = Field(ge=0)


class TutorHistoryDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["delete_my_tutor_history"]


class TutorExpiredDataPurgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["purge_expired_tutor_history"]
    expected_version: int = Field(ge=0)


class TutorDataDeletionOut(BaseModel):
    reason: TutorDeletionReason
    policy_version: int
    answers_deleted: int = Field(ge=0)
    feedback_events_deleted: int = Field(ge=0)
    agent_runs_deleted: int = Field(default=0, ge=0)
    cutoff: datetime | None = None
    agent_run_cutoff: datetime | None = None
    deleted_at: datetime
