from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Rubric
from ..schemas.schemas import RubricIn, RubricListOut, RubricOut

router = APIRouter(prefix="/rubrics", tags=["rubrics"])


@router.get("", response_model=RubricListOut)
def list_rubrics(
    level: str | None = Query(None, pattern="^(remember|understand|apply|analyze|evaluate|create)$"),
    is_active: bool | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Rubric)
    if level:
        query = query.filter(Rubric.level == level)
    if is_active is not None:
        query = query.filter(Rubric.is_active == is_active)
    total = query.count()
    items = query.order_by(Rubric.id.asc()).all()
    return {"total": total, "items": items}


@router.get("/{rubric_id}", response_model=RubricOut)
def get_rubric(rubric_id: int, db: Session = Depends(get_db)):
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(404, "rubric not found")
    return rubric


@router.get("/levels/{level}", response_model=RubricListOut)
def get_rubrics_for_level(
    level: str, db: Session = Depends(get_db)
):
    items = (
        db.query(Rubric)
        .filter(Rubric.level == level, Rubric.is_active == True)  # noqa: E712
        .order_by(Rubric.id.asc())
        .all()
    )
    return {"total": len(items), "items": items}


@router.post("", response_model=RubricOut)
def create_rubric(payload: RubricIn, db: Session = Depends(get_db)):
    rubric = Rubric(
        level=payload.level,
        name=payload.name,
        description=payload.description,
        criteria=payload.criteria or {},
        version=payload.version or 1,
        is_active=True if payload.is_active is None else payload.is_active,
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)
    return rubric


@router.put("/{rubric_id}", response_model=RubricOut)
def update_rubric(rubric_id: int, payload: RubricIn, db: Session = Depends(get_db)):
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(404, "rubric not found")

    rubric.level = payload.level or rubric.level
    rubric.name = payload.name or rubric.name
    rubric.description = payload.description or rubric.description
    if payload.criteria is not None:
        rubric.criteria = payload.criteria
    if payload.version is not None:
        rubric.version = payload.version
    if payload.is_active is not None:
        rubric.is_active = payload.is_active

    db.commit()
    db.refresh(rubric)
    return rubric


@router.delete("/{rubric_id}")
def delete_rubric(rubric_id: int, db: Session = Depends(get_db)):
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(404, "rubric not found")
    rubric.is_active = False
    db.commit()
    return {"ok": True}

