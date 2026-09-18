from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Program
from ..schemas.program_intelligence import (
    CompetencyCreateIn,
    CompetencyOut,
    CourseContributionOut,
    CourseContributionUpsertIn,
    PrerequisiteRelationDeleteIn,
    PrerequisiteRelationMutationOut,
    PrerequisiteRelationUpsertIn,
    ProgramAdministrationOverviewOut,
    ProgramAuditPreviewOut,
    ProgramAuthoringContextOut,
    ProgramCourseOrderIn,
    ProgramCourseOrderOut,
    ProgramCreateIn,
    ProgramDemoOut,
    ProgramEvidenceOptionsOut,
    ProgramMapOut,
    ProgramReviewNoteOut,
    ProgramReviewNoteSaveIn,
    ProgramSummaryOut,
)
from ..services.agent_run import resolve_agent_context
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_organization_role,
)
from ..services.program_agent import ProgramReviewNoteConflict, save_program_review_note
from ..services.program_intelligence import (
    PROGRAM_ADMIN_ROLES,
    PROGRAM_READ_ROLES,
    PROGRAM_WRITE_ROLES,
    ProgramCourseOrderConflict,
    ProgramCourseRemovalDenied,
    ProgramDuplicate,
    ProgramPrerequisiteConflict,
    ProgramScopeDenied,
    ProgramVersionConflict,
    add_competency,
    create_demo_program,
    create_program,
    delete_prerequisite_relation,
    get_program_administration_overview,
    get_program_audit_preview,
    get_program_authoring_context,
    get_program_evidence_options,
    get_program_map,
    list_programs,
    set_program_course_order,
    upsert_course_contribution,
    upsert_prerequisite_relation,
)

router = APIRouter(tags=["program-intelligence"])


def _program_or_404(db: Session, program_id: int) -> Program:
    program = db.get(Program, program_id)
    if program is None or not program.is_active:
        raise HTTPException(404, "resource not found")
    return program


def _scope_denied(db: Session, exc: ProgramScopeDenied) -> None:
    db.rollback()
    raise HTTPException(404, "resource not found") from exc


def _version_conflict(db: Session, exc: ProgramVersionConflict) -> None:
    db.rollback()
    raise HTTPException(
        409,
        {
            "code": "program_version_conflict",
            "message": "Program map changed. Reload and try again.",
        },
    ) from exc


def _duplicate(db: Session, exc: ProgramDuplicate) -> None:
    db.rollback()
    raise HTTPException(
        409,
        {
            "code": "program_duplicate",
            "message": "A program or competency with this code already exists.",
        },
    ) from exc


def _course_order_conflict(db: Session, exc: ProgramCourseOrderConflict) -> None:
    db.rollback()
    raise HTTPException(
        409,
        {
            "code": "program_course_position_conflict",
            "message": "Course position conflicts with the current program route.",
        },
    ) from exc


def _course_removal_denied(db: Session, exc: ProgramCourseRemovalDenied) -> None:
    db.rollback()
    raise HTTPException(
        409,
        {
            "code": "program_course_removal_denied",
            "message": "Existing program courses cannot be omitted from this route.",
        },
    ) from exc


def _prerequisite_conflict(db: Session, exc: ProgramPrerequisiteConflict) -> None:
    db.rollback()
    details = {
        "self_link": (
            "prerequisite_self_link",
            "A competency cannot be its own prerequisite.",
        ),
        "cycle": (
            "prerequisite_cycle",
            "This relation would create a prerequisite cycle.",
        ),
        "limit": (
            "prerequisite_limit",
            "The bounded prerequisite relation limit has been reached.",
        ),
    }
    code, message = details.get(
        exc.reason,
        ("prerequisite_conflict", "The prerequisite relation conflicts with the map."),
    )
    raise HTTPException(409, {"code": code, "message": message}) from exc


def _review_note_conflict(db: Session, exc: ProgramReviewNoteConflict) -> None:
    db.rollback()
    if exc.reason == "version":
        detail = {
            "code": "program_review_note_version_conflict",
            "message": "The review note changed. Reload it and keep your edits.",
        }
    else:
        detail = {
            "code": "program_review_note_source_changed",
            "message": "The program evidence changed. Prepare the note again.",
        }
    raise HTTPException(409, detail) from exc


@router.get(
    "/organizations/{organization_id}/programs",
    response_model=list[ProgramSummaryOut],
)
def organization_programs(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(db, principal, organization_id, PROGRAM_READ_ROLES)
    try:
        return list_programs(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.get(
    "/organizations/{organization_id}/program-administration-overview",
    response_model=ProgramAdministrationOverviewOut,
)
def organization_program_administration_overview(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(db, principal, organization_id, PROGRAM_ADMIN_ROLES)
    try:
        return get_program_administration_overview(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.post(
    "/organizations/{organization_id}/programs",
    response_model=ProgramSummaryOut,
    status_code=201,
)
def create_organization_program(
    organization_id: int,
    payload: ProgramCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(db, principal, organization_id, PROGRAM_WRITE_ROLES)
    try:
        result = create_program(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramDuplicate as exc:
        _duplicate(db, exc)
    db.commit()
    return result


@router.post(
    "/organizations/{organization_id}/programs/demo",
    response_model=ProgramDemoOut,
    status_code=201,
)
def create_organization_program_demo(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(db, principal, organization_id, PROGRAM_WRITE_ROLES)
    try:
        result = create_demo_program(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    db.commit()
    return result


@router.get("/programs/{program_id}/map", response_model=ProgramMapOut)
def program_map(
    program_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_READ_ROLES
    )
    try:
        return get_program_map(
            db,
            program_id=program_id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.get(
    "/programs/{program_id}/audit-preview",
    response_model=ProgramAuditPreviewOut,
)
def program_audit_preview(
    program_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_READ_ROLES
    )
    try:
        return get_program_audit_preview(
            db,
            program_id=program.id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.get(
    "/programs/{program_id}/authoring-context",
    response_model=ProgramAuthoringContextOut,
)
def program_authoring_context(
    program_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        return get_program_authoring_context(
            db,
            program_id=program.id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.get(
    "/programs/{program_id}/courses/{course_id}/evidence-options",
    response_model=ProgramEvidenceOptionsOut,
)
def program_course_evidence_options(
    program_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        return get_program_evidence_options(
            db,
            program_id=program.id,
            course_id=course_id,
            actor_user_id=principal.user_id,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)


@router.put(
    "/programs/{program_id}/courses",
    response_model=ProgramCourseOrderOut,
)
def put_program_courses(
    program_id: int,
    payload: ProgramCourseOrderIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        result = set_program_course_order(
            db,
            program_id=program.id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramVersionConflict as exc:
        _version_conflict(db, exc)
    except ProgramCourseRemovalDenied as exc:
        _course_removal_denied(db, exc)
    db.commit()
    return result


@router.post(
    "/programs/{program_id}/competencies",
    response_model=CompetencyOut,
    status_code=201,
)
def create_program_competency(
    program_id: int,
    payload: CompetencyCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        result = add_competency(
            db,
            program_id=program_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramVersionConflict as exc:
        _version_conflict(db, exc)
    except ProgramDuplicate as exc:
        _duplicate(db, exc)
    db.commit()
    return result


@router.put(
    "/programs/{program_id}/contributions",
    response_model=CourseContributionOut,
)
def put_program_course_contribution(
    program_id: int,
    payload: CourseContributionUpsertIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        result = upsert_course_contribution(
            db,
            program_id=program_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramVersionConflict as exc:
        _version_conflict(db, exc)
    except ProgramCourseOrderConflict as exc:
        _course_order_conflict(db, exc)
    db.commit()
    return result


@router.put(
    "/programs/{program_id}/prerequisites",
    response_model=PrerequisiteRelationMutationOut,
)
def put_program_prerequisite_relation(
    program_id: int,
    payload: PrerequisiteRelationUpsertIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        result = upsert_prerequisite_relation(
            db,
            program_id=program_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramVersionConflict as exc:
        _version_conflict(db, exc)
    except ProgramPrerequisiteConflict as exc:
        _prerequisite_conflict(db, exc)
    db.commit()
    return result


@router.delete(
    "/programs/{program_id}/prerequisites/{relation_id}",
    response_model=PrerequisiteRelationMutationOut,
)
def remove_program_prerequisite_relation(
    program_id: int,
    relation_id: int,
    payload: PrerequisiteRelationDeleteIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db, principal, program.organization_id, PROGRAM_WRITE_ROLES
    )
    try:
        result = delete_prerequisite_relation(
            db,
            program_id=program_id,
            relation_id=relation_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except ProgramScopeDenied as exc:
        _scope_denied(db, exc)
    except ProgramVersionConflict as exc:
        _version_conflict(db, exc)
    db.commit()
    return result


@router.put(
    "/programs/{program_id}/review-note",
    response_model=ProgramReviewNoteOut,
)
async def put_program_review_note(
    program_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    program = _program_or_404(db, program_id)
    require_organization_role(
        db,
        principal,
        program.organization_id,
        frozenset({"program_designer", "administrator"}),
    )
    context = resolve_agent_context(
        db,
        principal,
        organization_id=program.organization_id,
    )
    try:
        raw_payload = await request.json()
        payload = ProgramReviewNoteSaveIn.model_validate(raw_payload)
    except (ValueError, TypeError, ValidationError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else []
        raise RequestValidationError(errors, body=None) from exc
    try:
        result = save_program_review_note(
            db,
            context=context,
            program_id=program.id,
            payload=payload,
        )
    except ProgramReviewNoteConflict as exc:
        _review_note_conflict(db, exc)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result
