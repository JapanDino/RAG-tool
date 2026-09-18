from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course, CourseEvaluationProtocol
from ..schemas.evaluation_protocol import CourseEvaluationProtocolOut
from ..services.authorization import require_course_route_access
from ..services.evaluation_protocol import (
    evaluation_protocol_markdown,
    run_evaluation_protocol,
)

router = APIRouter(
    tags=["evaluation-protocols"],
    dependencies=[Depends(require_course_route_access)],
)


@router.post(
    "/courses/{course_id}/evaluation-protocols",
    response_model=CourseEvaluationProtocolOut,
    status_code=201,
)
def create_evaluation_protocol(course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    return run_evaluation_protocol(db, course)


@router.get(
    "/courses/{course_id}/evaluation-protocols",
    response_model=list[CourseEvaluationProtocolOut],
)
def list_evaluation_protocols(course_id: int, db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "course not found")
    return (
        db.query(CourseEvaluationProtocol)
        .filter(CourseEvaluationProtocol.course_id == course_id)
        .order_by(CourseEvaluationProtocol.id.desc())
        .limit(50)
        .all()
    )


@router.get(
    "/evaluation-protocols/{protocol_id}",
    response_model=CourseEvaluationProtocolOut,
)
def get_evaluation_protocol(protocol_id: int, db: Session = Depends(get_db)):
    protocol = db.get(CourseEvaluationProtocol, protocol_id)
    if protocol is None:
        raise HTTPException(404, "evaluation protocol not found")
    return protocol


@router.get("/evaluation-protocols/{protocol_id}/download")
def download_evaluation_protocol(
    protocol_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
):
    protocol = db.get(CourseEvaluationProtocol, protocol_id)
    if protocol is None:
        raise HTTPException(404, "evaluation protocol not found")
    course = db.get(Course, protocol.course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    if format == "json":
        payload = CourseEvaluationProtocolOut.model_validate(protocol)
        return Response(
            content=payload.model_dump_json(indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="evaluation-protocol-{protocol.id}.json"'
            },
        )
    return Response(
        content=evaluation_protocol_markdown(protocol, course),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="evaluation-protocol-{protocol.id}.md"'
        },
    )
