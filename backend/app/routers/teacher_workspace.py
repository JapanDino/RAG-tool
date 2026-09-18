from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course
from ..schemas.teacher_workspace import TeacherWorkspaceOut
from ..services.authorization import require_course_route_access
from ..services.teacher_workspace import build_teacher_workspace

router = APIRouter(
    tags=["teacher-workspace"],
    dependencies=[Depends(require_course_route_access)],
)


@router.get(
    "/courses/{course_id}/teacher-workspace",
    response_model=TeacherWorkspaceOut,
)
def teacher_workspace_summary(course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "resource not found")
    return build_teacher_workspace(db, course)
