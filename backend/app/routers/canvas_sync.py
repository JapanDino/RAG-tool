from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..schemas.canvas_sync import CanvasSyncPreviewOut
from ..services.authorization import Principal, require_course_route_access
from ..services.canvas_sync import (
    CanvasConnectionProvider,
    build_canvas_sync_preview,
    get_canvas_connection_provider,
)

router = APIRouter(tags=["canvas-sync"])


@router.get(
    "/courses/{course_id}/canvas-sync-preview",
    response_model=CanvasSyncPreviewOut,
)
def canvas_sync_preview(
    course_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_course_route_access),
    provider: CanvasConnectionProvider = Depends(get_canvas_connection_provider),
):
    response.headers["Cache-Control"] = "no-store"
    return build_canvas_sync_preview(
        db,
        course_id=course_id,
        principal=principal,
        provider=provider,
    )
