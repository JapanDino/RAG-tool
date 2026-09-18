from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

CanvasSyncState = Literal[
    "oauth_required",
    "scope_mismatch",
    "ready",
    "course_source_unverified",
    "source_unavailable",
]


class CanvasSyncBoundaryOut(BaseModel):
    selection: Literal["lti_current_course"]
    canvas_origin: str
    canvas_course_id: str
    exact_context_binding: Literal[True]


class CanvasManifestItemOut(BaseModel):
    source_ref: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    published: bool | None


class CanvasManifestGroupOut(BaseModel):
    kind: Literal["modules", "pages", "assignments"]
    total: int = Field(ge=0, le=500)
    returned: int = Field(ge=0, le=5)
    preview_truncated: bool
    read_truncated: bool
    items: list[CanvasManifestItemOut] = Field(max_length=5)


class CanvasManifestLimitsOut(BaseModel):
    source_pages_per_collection: Literal[10]
    objects_per_collection: Literal[500]
    preview_items_per_group: Literal[5]
    title_characters: Literal[200]


class SyntheticDevelopmentProvenanceOut(BaseModel):
    kind: Literal["synthetic_development"]
    canvas_contacted: Literal[False]
    generator_version: Literal["canvas-manifest-v1"]


class TestFixtureProvenanceOut(BaseModel):
    kind: Literal["test_fixture"]
    canvas_contacted: Literal[False]
    fixture_version: Literal["canvas-manifest-fixture-v1"]


CanvasManifestProvenanceOut = Annotated[
    SyntheticDevelopmentProvenanceOut | TestFixtureProvenanceOut,
    Field(discriminator="kind"),
]


class CanvasCourseManifestOut(BaseModel):
    course_title: str = Field(min_length=1, max_length=500)
    captured_at: datetime
    provenance: CanvasManifestProvenanceOut
    limits: CanvasManifestLimitsOut
    groups: list[CanvasManifestGroupOut] = Field(min_length=3, max_length=3)


class CanvasSyncPreviewOut(BaseModel):
    schema_version: Literal[2]
    state: CanvasSyncState
    read_only: Literal[True]
    course_id: int = Field(gt=0)
    course_title: str = Field(min_length=1, max_length=500)
    boundary: CanvasSyncBoundaryOut | None
    required_scopes: list[str]
    missing_scopes: list[str]
    excluded_data: list[
        Literal[
            "rosters",
            "users",
            "submissions",
            "grades",
            "student_activity",
            "canvas_writes",
        ]
    ]
    manifest: CanvasCourseManifestOut | None
