from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CanvasOAuthConfigurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canvas_api_origin: str = Field(min_length=1, max_length=1000)
    oauth_client_id: str = Field(min_length=1, max_length=255)
    expected_version: int | None = Field(default=None, gt=0)


class CanvasOAuthConfigurationOut(BaseModel):
    canvas_api_origin: str
    oauth_client_id: str
    version: int = Field(gt=0)


class CanvasOAuthConnectionOut(BaseModel):
    state: Literal[
        "not_configured",
        "ready_to_connect",
        "connected",
        "reconnect_required",
        "production_disabled",
    ]
    owner: Literal["current_user"]
    mode: Literal["fake_development"] | None
    granted_scopes: list[str]
    expires_at: datetime | None
    connected_at: datetime | None


class CanvasOAuthStatusOut(BaseModel):
    schema_version: Literal[1]
    registration_id: int = Field(gt=0)
    production_connection_enabled: Literal[False]
    fake_flow_available: bool
    callback_uri: str
    required_scopes: list[str]
    excluded_data: list[str]
    configuration: CanvasOAuthConfigurationOut | None
    connection: CanvasOAuthConnectionOut


class CanvasOAuthStartOut(BaseModel):
    schema_version: Literal[1]
    authorization_url: str
    expires_at: datetime


class CanvasOAuthDisconnectOut(BaseModel):
    schema_version: Literal[1]
    state: Literal["disconnected"]


class InstructorCanvasOAuthConnectionOut(BaseModel):
    mode: Literal["fake_development"] | None
    connected_at: datetime | None
    expires_at: datetime | None


class InstructorCanvasOAuthStatusOut(BaseModel):
    schema_version: Literal[1]
    state: Literal[
        "configuration_required",
        "configuration_mismatch",
        "ready_to_connect",
        "connected",
        "reconnect_required",
        "production_disabled",
    ]
    fake_flow_available: bool
    read_only: Literal[True]
    required_scopes: list[str]
    excluded_data: list[str]
    connection: InstructorCanvasOAuthConnectionOut
