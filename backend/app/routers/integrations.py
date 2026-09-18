import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course, CourseMembership
from ..schemas.course_audit import CanvasImportIn, CanvasImportOut
from ..services.authorization import (
    Principal,
    default_manageable_organization,
    get_current_principal,
    require_course_route_access,
)
from ..services.canvas_import import CanvasClient, persist_canvas_course

router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_course_route_access)],
)


@router.post("/canvas/import", response_model=CanvasImportOut, status_code=201)
def import_canvas_course(
    payload: CanvasImportIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        organization_id = (
            None if principal.bypass else default_manageable_organization(db, principal)
        )
        client = CanvasClient(
            str(payload.base_url), payload.access_token.get_secret_value()
        )
        exported = client.export_course(payload.canvas_course_id)
        result = persist_canvas_course(
            db,
            exported,
            client.base_url,
            organization_id=organization_id,
        )
        course = db.get(Course, result.course_id)
        if (
            course is not None
            and not principal.bypass
            and principal.user_id is not None
        ):
            assert organization_id is not None
            membership = (
                db.query(CourseMembership)
                .filter(
                    CourseMembership.course_id == course.id,
                    CourseMembership.user_id == principal.user_id,
                )
                .first()
            )
            if membership is None:
                db.add(
                    CourseMembership(
                        organization_id=organization_id,
                        course_id=course.id,
                        user_id=principal.user_id,
                        role="instructor",
                        is_active=True,
                    )
                )
            else:
                membership.organization_id = organization_id
                membership.is_active = True
            db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, "Canvas API request failed") from exc
