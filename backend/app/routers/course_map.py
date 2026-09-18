from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course, LtiProductSession
from ..schemas.course_map import CourseMapOut
from ..services.authorization import Principal, get_current_principal
from ..services.course_map import build_course_map

router = APIRouter(prefix="/course-map", tags=["course-map"])


@router.get("", response_model=CourseMapOut)
def current_course_map(
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
    course = db.get(Course, principal.course_scope_id)
    if (
        session is None
        or session.role != "student"
        or session.user_id != principal.user_id
        or session.course_id != principal.course_scope_id
        or course is None
    ):
        raise HTTPException(404, "resource not found")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return build_course_map(db, course)
