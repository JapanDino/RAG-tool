from typing import Literal

from pydantic import BaseModel, Field

CourseMapItemType = Literal[
    "page",
    "assignment",
    "file",
    "external",
    "section",
    "unsupported",
]
DestinationProvenance = Literal["canvas", "external"]


class CourseMapItemOut(BaseModel):
    source_ref: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    item_type: CourseMapItemType
    position: int = Field(ge=0)
    available: bool
    supported: bool
    destination_url: str | None = Field(default=None, max_length=2000)
    destination_provenance: DestinationProvenance | None = None


class CourseMapModuleOut(BaseModel):
    id: int
    source_ref: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    position: int = Field(ge=0)
    items: list[CourseMapItemOut]


class CourseMapCourseOut(BaseModel):
    id: int
    title: str = Field(min_length=1, max_length=300)
    syllabus_summary: str | None = Field(default=None, max_length=1200)
    destination_url: str | None = Field(default=None, max_length=2000)


class CourseMapOut(BaseModel):
    version: Literal["1"] = "1"
    read_only: Literal[True] = True
    exact_context: Literal[True] = True
    course: CourseMapCourseOut
    modules: list[CourseMapModuleOut]
    total_items: int = Field(ge=0)
    truncated: bool = False
