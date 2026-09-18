from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    Course,
    CourseMembership,
    LtiProductSession,
    MembershipAuditEvent,
    Organization,
    OrganizationMembership,
    User,
)
from ..schemas.identity import (
    CourseAccessOut,
    CourseMembershipOut,
    CourseMembershipUpsertIn,
    CurrentUserOut,
    DevelopmentBootstrapIn,
    DevelopmentBootstrapOut,
    DevelopmentIdentityOut,
    OrganizationAccessOut,
    OrganizationOut,
    ProductSessionCourseOut,
    ProductSessionOut,
    UserOut,
)
from ..services.authorization import (
    Principal,
    accessible_courses,
    actions_for_roles,
    course_roles,
    get_current_principal,
    organization_roles,
    require_development_auth,
    require_organization_role,
    sorted_roles,
)
from ..services.product_session import (
    clear_product_session_cookie,
    csrf_token_for_session,
    revoke_product_session,
    session_cookie_policy,
)

router = APIRouter(prefix="/identity", tags=["identity"])

DEV_IDENTITIES = (
    ("student@local.test", "Алина Соколова", "student"),
    ("instructor@local.test", "Михаил Орлов", "instructor"),
    ("methodologist@local.test", "Елена Воронова", "methodologist"),
    ("designer@local.test", "Даниил Лебедев", "program_designer"),
    ("admin@local.test", "Ольга Белова", "administrator"),
)


@router.get("/session", response_model=ProductSessionOut)
def product_session_context(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if (
        principal.auth_mode != "lti_session"
        or principal.session_id is None
        or principal.course_scope_id is None
        or principal.user_id is None
    ):
        raise HTTPException(401, "product session is unavailable")
    session = db.get(LtiProductSession, principal.session_id)
    user = db.get(User, principal.user_id)
    course = db.get(Course, principal.course_scope_id)
    raw_token = request.cookies.get(session_cookie_policy().name)
    if session is None or user is None or course is None or raw_token is None:
        raise HTTPException(401, "product session is unavailable")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return ProductSessionOut(
        user=UserOut.model_validate(user),
        course=ProductSessionCourseOut(
            id=course.id,
            organization_id=int(course.organization_id),
            title=course.title,
        ),
        role=session.role,
        expires_at=session.expires_at,
        csrf_token=csrf_token_for_session(raw_token),
    )


@router.post("/session/logout", status_code=204)
def logout_product_session(
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.auth_mode != "lti_session" or principal.session_id is None:
        raise HTTPException(401, "product session is unavailable")
    revoke_product_session(db, principal.session_id)
    clear_product_session_cookie(response)
    response.status_code = 204


def _identity_rows() -> list[DevelopmentIdentityOut]:
    return [
        DevelopmentIdentityOut(
            email=email,
            display_name=display_name,
            primary_role=role,
        )
        for email, display_name, role in DEV_IDENTITIES
    ]


@router.get("/development/users", response_model=list[DevelopmentIdentityOut])
def development_users(db: Session = Depends(get_db)):
    require_development_auth()
    existing = {
        email
        for (email,) in db.query(User.email)
        .filter(User.email.in_([item[0] for item in DEV_IDENTITIES]))
        .all()
    }
    return [item for item in _identity_rows() if item.email in existing]


@router.post(
    "/development/bootstrap",
    response_model=DevelopmentBootstrapOut,
    status_code=201,
)
def bootstrap_development(
    payload: DevelopmentBootstrapIn,
    db: Session = Depends(get_db),
):
    require_development_auth()
    organization = (
        db.query(Organization)
        .filter(Organization.slug == payload.organization_slug)
        .first()
    )
    if organization is None:
        organization = Organization(
            slug=payload.organization_slug,
            name=payload.organization_name,
            is_active=True,
        )
        db.add(organization)
        db.flush()

    users: list[tuple[User, str]] = []
    for email, display_name, role in DEV_IDENTITIES:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, display_name=display_name, is_active=True)
            db.add(user)
            db.flush()
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
            .first()
        )
        if membership is None:
            membership = OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
            db.add(membership)
            db.add(
                MembershipAuditEvent(
                    organization_id=organization.id,
                    actor_user_id=None,
                    target_user_id=user.id,
                    event_type="organization_membership_created",
                    new_role=role,
                    event_metadata={"source": "development_bootstrap"},
                )
            )
        else:
            membership.role = role
            membership.is_active = True
        users.append((user, role))

    courses_linked = 0
    if payload.include_existing_courses:
        courses = (
            db.query(Course)
            .filter(
                (Course.organization_id == organization.id)
                | (Course.organization_id.is_(None))
            )
            .all()
        )
        for course in courses:
            if course.organization_id is None:
                course.organization_id = organization.id
                courses_linked += 1
            for user, role in users:
                membership = (
                    db.query(CourseMembership)
                    .filter(
                        CourseMembership.course_id == course.id,
                        CourseMembership.user_id == user.id,
                    )
                    .first()
                )
                if membership is None:
                    db.add(
                        CourseMembership(
                            organization_id=organization.id,
                            course_id=course.id,
                            user_id=user.id,
                            role=role,
                            is_active=True,
                        )
                    )
                    db.add(
                        MembershipAuditEvent(
                            organization_id=organization.id,
                            course_id=course.id,
                            actor_user_id=None,
                            target_user_id=user.id,
                            event_type="course_membership_created",
                            new_role=role,
                            event_metadata={"source": "development_bootstrap"},
                        )
                    )
                else:
                    membership.organization_id = organization.id
                    membership.role = role
                    membership.is_active = True
    db.commit()
    db.refresh(organization)
    return DevelopmentBootstrapOut(
        organization=OrganizationOut.model_validate(organization),
        identities=_identity_rows(),
        courses_linked=courses_linked,
    )


@router.get("/me", response_model=CurrentUserOut)
def current_user(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.bypass or principal.user_id is None:
        raise HTTPException(
            409, "identity context is unavailable in compatibility mode"
        )
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(401, "identity is unavailable")
    organizations_by_id = {
        item.id: item
        for item in db.query(Organization)
        .filter(Organization.is_active.is_(True))
        .all()
    }
    organizations = [
        OrganizationAccessOut(
            **OrganizationOut.model_validate(
                organizations_by_id[organization_id]
            ).model_dump(),
            role=role,
        )
        for organization_id, role in organization_roles(db, principal).items()
        if organization_id in organizations_by_id
    ]
    courses = []
    for course in accessible_courses(db, principal):
        if course.organization_id is None:
            continue
        roles = course_roles(db, principal, course)
        courses.append(
            CourseAccessOut(
                id=course.id,
                organization_id=course.organization_id,
                title=course.title,
                description=course.description,
                source_type=course.source_type,
                roles=sorted_roles(roles),
                actions=actions_for_roles(roles),
                updated_at=course.updated_at,
            )
        )
    return CurrentUserOut(
        user=UserOut.model_validate(user),
        organizations=organizations,
        courses=courses,
        auth_mode=principal.auth_mode,
    )


@router.get(
    "/organizations/{organization_id}/members",
    response_model=list[UserOut],
)
def organization_members(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    user_ids = [
        user_id
        for (user_id,) in db.query(OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
        )
        .all()
    ]
    if not user_ids:
        return []
    return (
        db.query(User).filter(User.id.in_(user_ids)).order_by(User.display_name).all()
    )


@router.put(
    "/organizations/{organization_id}/courses/{course_id}/members/{user_id}",
    response_model=CourseMembershipOut,
)
def upsert_course_membership(
    organization_id: int,
    course_id: int,
    user_id: int,
    payload: CourseMembershipUpsertIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    course = db.get(Course, course_id)
    target = db.get(User, user_id)
    if course is None or course.organization_id != organization_id or target is None:
        raise HTTPException(404, "resource not found")
    organization_member = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
        .first()
    )
    if organization_member is None:
        raise HTTPException(409, "user is not an active organization member")
    membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == user_id,
        )
        .first()
    )
    previous_role = membership.role if membership is not None else None
    if membership is None:
        membership = CourseMembership(
            organization_id=organization_id,
            course_id=course_id,
            user_id=user_id,
            role=payload.role,
            is_active=payload.is_active,
        )
        db.add(membership)
        event_type = "course_membership_created"
    else:
        membership.role = payload.role
        membership.is_active = payload.is_active
        event_type = "course_membership_updated"
    db.add(
        MembershipAuditEvent(
            organization_id=organization_id,
            course_id=course_id,
            actor_user_id=principal.user_id,
            target_user_id=user_id,
            event_type=event_type,
            previous_role=previous_role,
            new_role=payload.role if payload.is_active else None,
            event_metadata={"active": payload.is_active},
        )
    )
    db.commit()
    db.refresh(membership)
    return membership
