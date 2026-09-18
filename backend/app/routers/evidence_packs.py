from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course
from ..schemas.evidence_pack import EvidencePackPreviewOut
from ..services.authorization import require_course_route_access
from ..services.evidence_pack import build_evidence_pack, build_evidence_pack_preview

router = APIRouter(
    tags=["evidence-packs"],
    dependencies=[Depends(require_course_route_access)],
)


@router.get("/courses/{course_id}/evidence-pack", response_model=EvidencePackPreviewOut)
def evidence_pack_preview(course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    return build_evidence_pack_preview(db, course)


@router.get("/courses/{course_id}/evidence-pack/download")
def download_evidence_pack(course_id: int, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    try:
        content, _ = build_evidence_pack(db, course)
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="course-evidence-pack-{course_id}.zip"'
        },
    )
