import os
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    AuditRun,
    Course,
    CourseCopilotSuggestion,
    CourseEvaluationProtocol,
    CourseFinding,
    CourseMembership,
    CourseQuestionAnswer,
    OrganizationMembership,
    User,
)
from .product_session import (
    resolve_product_session,
    session_cookie_policy,
    valid_csrf_token,
)

ROLE_ORDER = {
    "administrator": 0,
    "instructor": 1,
    "methodologist": 2,
    "program_designer": 3,
    "student": 4,
}
ALL_ROLES = frozenset(ROLE_ORDER)
STAFF_READ_ROLES = frozenset(
    {"instructor", "methodologist", "program_designer", "administrator"}
)
REVIEW_ROLES = frozenset({"instructor", "methodologist", "administrator"})
MANAGE_ROLES = frozenset({"instructor", "administrator"})
TUTOR_ROLES = frozenset({"student", "instructor", "methodologist", "administrator"})


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    email: str
    display_name: str
    auth_mode: str
    bypass: bool = False
    course_scope_id: int | None = None
    session_id: int | None = None
    registration_id: int | None = None


def configured_auth_mode() -> str:
    configured = os.getenv("AUTH_MODE", "").strip().lower()
    if configured:
        return configured
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        return "external"
    return "development"


def development_auth_available() -> bool:
    return (
        configured_auth_mode() == "development"
        and os.getenv("APP_ENV", "development").strip().lower() != "production"
    )


def require_development_auth() -> None:
    if not development_auth_available():
        raise HTTPException(
            status_code=404, detail="development identity is unavailable"
        )


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
    dev_user: str | None = Header(default=None, alias="X-Dev-User"),
) -> Principal:
    mode = configured_auth_mode()
    if mode == "disabled":
        if os.getenv("APP_ENV", "development").strip().lower() == "production":
            raise HTTPException(status_code=503, detail="unsafe authentication mode")
        return Principal(
            user_id=None,
            email="system@disabled.local",
            display_name="Compatibility mode",
            auth_mode=mode,
            bypass=True,
        )
    normalized = (dev_user or "").strip().lower()
    if mode == "development" and normalized:
        if not development_auth_available():
            raise HTTPException(
                status_code=503, detail="development identity is disabled"
            )
        user = (
            db.query(User)
            .filter(User.email == normalized, User.is_active.is_(True))
            .first()
        )
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "identity_unknown",
                    "message": "The selected development identity is unavailable.",
                },
            )
        return Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            auth_mode=mode,
        )

    cookie_name = session_cookie_policy().name
    raw_session = request.cookies.get(cookie_name)
    resolved = resolve_product_session(db, raw_session)
    if resolved is not None:
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not valid_csrf_token(
            raw_session, request.headers.get("X-CSRF-Token")
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "csrf_invalid",
                    "message": "The session request could not be verified.",
                },
            )
        return Principal(
            user_id=resolved.user.id,
            email=resolved.user.email,
            display_name=resolved.user.display_name,
            auth_mode="lti_session",
            course_scope_id=resolved.course.id,
            session_id=resolved.row.id,
            registration_id=resolved.row.registration_id,
        )

    if mode == "development":
        raise HTTPException(
            status_code=401,
            detail={
                "code": "identity_required",
                "message": "Select a local development identity.",
            },
        )
    raise HTTPException(
        status_code=401,
        detail={
            "code": "session_required",
            "message": "Open the tool from Canvas to start a session.",
        },
    )


def organization_roles(db: Session, principal: Principal) -> dict[int, str]:
    if principal.bypass or principal.user_id is None:
        return {}
    query = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == principal.user_id,
        OrganizationMembership.is_active.is_(True),
    )
    if principal.course_scope_id is not None:
        course = db.get(Course, principal.course_scope_id)
        if course is None or course.organization_id is None:
            return {}
        query = query.filter(
            OrganizationMembership.organization_id == course.organization_id
        )
    rows = query.all()
    return {row.organization_id: row.role for row in rows}


def course_roles(db: Session, principal: Principal, course: Course) -> set[str]:
    if principal.bypass:
        return set(ALL_ROLES)
    if principal.user_id is None:
        return set()
    if principal.course_scope_id is not None and principal.course_scope_id != course.id:
        return set()
    roles = {
        row.role
        for row in db.query(CourseMembership)
        .filter(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == principal.user_id,
            CourseMembership.is_active.is_(True),
        )
        .all()
    }
    if course.organization_id is not None:
        org_role = organization_roles(db, principal).get(course.organization_id)
        if org_role == "administrator":
            roles.add("administrator")
    return roles


def sorted_roles(roles: set[str]) -> list[str]:
    return sorted(roles, key=lambda item: ROLE_ORDER.get(item, 99))


def actions_for_roles(roles: set[str]) -> list[str]:
    actions = {"open_course"}
    if roles & STAFF_READ_ROLES:
        actions.update({"inspect_evidence", "view_quality"})
    if roles & REVIEW_ROLES:
        actions.update({"run_audit", "review_findings"})
    if roles & MANAGE_ROLES:
        actions.update({"manage_content", "prepare_changes"})
    if roles & TUTOR_ROLES:
        actions.add("ask_tutor")
    if "student" in roles:
        actions.add("student_home")
    if "program_designer" in roles:
        actions.add("program_context")
    if "administrator" in roles:
        actions.add("manage_memberships")
    return sorted(actions)


def accessible_courses(db: Session, principal: Principal) -> list[Course]:
    query = db.query(Course).order_by(Course.updated_at.desc(), Course.id.desc())
    if principal.bypass:
        return query.all()
    if principal.user_id is None:
        return []
    course_ids = {
        row.course_id
        for row in db.query(CourseMembership)
        .filter(
            CourseMembership.user_id == principal.user_id,
            CourseMembership.is_active.is_(True),
        )
        .all()
    }
    admin_org_ids = {
        organization_id
        for organization_id, role in organization_roles(db, principal).items()
        if role == "administrator"
    }
    if not course_ids and not admin_org_ids:
        return []
    courses = [
        course
        for course in query.all()
        if course.id in course_ids or course.organization_id in admin_org_ids
    ]
    if principal.course_scope_id is not None:
        courses = [
            course for course in courses if course.id == principal.course_scope_id
        ]
    return courses


def default_manageable_organization(db: Session, principal: Principal) -> int:
    if principal.bypass:
        raise HTTPException(422, "organization_id is required in compatibility mode")
    if principal.course_scope_id is not None:
        raise HTTPException(404, "resource not found")
    candidates = [
        organization_id
        for organization_id, role in organization_roles(db, principal).items()
        if role in MANAGE_ROLES
    ]
    if not candidates:
        raise HTTPException(403, "no organization allows course management")
    if len(candidates) > 1:
        raise HTTPException(422, "organization_id is required for this user")
    return candidates[0]


def require_organization_role(
    db: Session,
    principal: Principal,
    organization_id: int,
    allowed_roles: frozenset[str],
) -> str:
    if principal.bypass:
        return "administrator"
    if principal.course_scope_id is not None:
        raise HTTPException(404, "resource not found")
    role = organization_roles(db, principal).get(organization_id)
    if role not in allowed_roles:
        raise HTTPException(404, "resource not found")
    return role


def _resolve_course(db: Session, request: Request) -> Course | None:
    params = request.path_params
    if "course_id" in params:
        return db.get(Course, int(params["course_id"]))
    lookups = (
        ("audit_run_id", AuditRun),
        ("finding_id", CourseFinding),
        ("answer_id", CourseQuestionAnswer),
        ("suggestion_id", CourseCopilotSuggestion),
        ("protocol_id", CourseEvaluationProtocol),
    )
    for key, model in lookups:
        if key in params:
            resource = db.get(model, int(params[key]))
            if resource is None:
                return None
            return db.get(Course, resource.course_id)
    return None


def _allowed_roles_for_route(request: Request) -> frozenset[str]:
    route = request.scope.get("route")
    route_name = getattr(route, "name", "")
    if request.method == "GET":
        if route_name == "get_course":
            return ALL_ROLES
        if route_name in {
            "evidence_pack_preview",
            "download_evidence_pack",
            "course_ml_feedback_summary",
            "download_course_ml_feedback",
        }:
            return REVIEW_ROLES
        if route_name in {"course_qa_history", "course_answer_feedback_history"}:
            return TUTOR_ROLES
        if route_name in {"get_tutor_policy", "get_course_tutor_data_policy"}:
            return TUTOR_ROLES
        if route_name == "teacher_workspace_summary":
            return REVIEW_ROLES
        return STAFF_READ_ROLES
    if route_name in {
        "start_audit",
        "review_finding",
        "suggest_remediation",
        "review_suggestion",
        "create_evaluation_protocol",
    }:
        return REVIEW_ROLES
    if route_name in {
        "ask_course",
        "review_course_answer",
        "delete_own_tutor_history",
    }:
        return TUTOR_ROLES
    if route_name == "update_tutor_policy_route":
        return MANAGE_ROLES
    return MANAGE_ROLES


def require_course_route_access(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    if principal.bypass:
        return principal
    course = _resolve_course(db, request)
    route = request.scope.get("route")
    route_name = getattr(route, "name", "")
    if course is None:
        if any(
            key in request.path_params
            for key in (
                "course_id",
                "audit_run_id",
                "finding_id",
                "answer_id",
                "suggestion_id",
                "protocol_id",
            )
        ):
            raise HTTPException(404, "resource not found")
        if route_name == "list_courses":
            return principal
        roles = organization_roles(db, principal).values()
        if not any(role in MANAGE_ROLES for role in roles):
            raise HTTPException(403, "no organization allows this action")
        return principal
    roles = course_roles(db, principal, course)
    if not roles.intersection(_allowed_roles_for_route(request)):
        raise HTTPException(404, "resource not found")
    return principal
