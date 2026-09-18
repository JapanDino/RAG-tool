from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal[
    "student",
    "instructor",
    "methodologist",
    "program_designer",
    "administrator",
]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    is_active: bool


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    is_active: bool


class OrganizationAccessOut(OrganizationOut):
    role: Role


class CourseAccessOut(BaseModel):
    id: int
    organization_id: int
    title: str
    description: str
    source_type: str
    roles: list[Role]
    actions: list[str]
    updated_at: datetime | None = None


class CurrentUserOut(BaseModel):
    user: UserOut
    organizations: list[OrganizationAccessOut]
    courses: list[CourseAccessOut]
    auth_mode: str


class ProductSessionCourseOut(BaseModel):
    id: int
    organization_id: int
    title: str


class ProductSessionOut(BaseModel):
    user: UserOut
    course: ProductSessionCourseOut
    role: Literal["student", "instructor"]
    expires_at: datetime
    csrf_token: str


class DevelopmentIdentityOut(BaseModel):
    email: str
    display_name: str
    primary_role: Role


class DevelopmentBootstrapIn(BaseModel):
    organization_name: str = Field(
        default="Локальная школа", min_length=1, max_length=300
    )
    organization_slug: str = Field(
        default="local-school", pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120
    )
    include_existing_courses: bool = True


class DevelopmentBootstrapOut(BaseModel):
    organization: OrganizationOut
    identities: list[DevelopmentIdentityOut]
    courses_linked: int


class CourseMembershipUpsertIn(BaseModel):
    role: Role
    is_active: bool = True


class CourseMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    course_id: int
    user_id: int
    role: Role
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
