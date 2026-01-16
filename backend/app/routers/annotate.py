from statistics import mean, pstdev

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.models import BloomAnnotation, Chunk, Dataset, Document, Job, JobType, JobStatus
from ..schemas.schemas import AnnotationListOut, AnnotationOut, AnnotationUpdateIn, AnnotationWithChunkOut
from ..services.validation import validate_annotation
from ..tasks.queue import enqueue_or_mark
from ..utils.quality import (
    calculate_coverage_metrics,
    calculate_level_distribution,
    calculate_score_distribution,
)

router = APIRouter(prefix="/annotate", tags=["annotate"])


@router.post("/datasets/{dataset_id}")
def start_annotate(
    dataset_id: int,
    level: str = Query(..., pattern="^(remember|understand|apply|analyze|evaluate|create)$"),
    db: Session = Depends(get_db),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    job = Job(
        type=JobType.annotate,
        status=JobStatus.queued,
        payload={"dataset_id": dataset_id, "level": level},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}


@router.get("/datasets/{dataset_id}/stats")
def get_stats(
    dataset_id: int,
    level: str | None = Query(None, pattern="^(remember|understand|apply|analyze|evaluate|create)$"),
    min_score: float | None = None,
    db: Session = Depends(get_db),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    query = (
        db.query(BloomAnnotation)
        .join(Chunk, BloomAnnotation.chunk_id == Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.dataset_id == dataset_id)
    )
    if level:
        query = query.filter(BloomAnnotation.level == level)
    if min_score is not None:
        query = query.filter(BloomAnnotation.score >= min_score)

    annotations = query.all()
    consistency = {}
    if annotations:
        by_chunk: dict[int, list[float]] = {}
        for ann in annotations:
            by_chunk.setdefault(ann.chunk_id, []).append(ann.score)
        stdevs = []
        for vals in by_chunk.values():
            if len(vals) > 1:
                stdevs.append(pstdev(vals))
        consistency = {
            "chunks_with_multiple": len(stdevs),
            "avg_score_stdev": mean(stdevs) if stdevs else None,
        }

    return {
        "total": len(annotations),
        "level_distribution": calculate_level_distribution(annotations),
        "score_distribution": calculate_score_distribution(annotations),
        "coverage": calculate_coverage_metrics(dataset_id, db),
        "consistency": consistency,
    }


@router.get("/chunks/{chunk_id}", response_model=list[AnnotationWithChunkOut])
def get_chunk_annotations(chunk_id: int, db: Session = Depends(get_db)):
    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(404, "chunk not found")
    annotations = (
        db.query(BloomAnnotation)
        .join(Chunk, BloomAnnotation.chunk_id == Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .filter(BloomAnnotation.chunk_id == chunk_id)
        .all()
    )
    return [
        AnnotationWithChunkOut(
            id=a.id,
            chunk_id=a.chunk_id,
            level=a.level,
            label=a.label,
            rationale=a.rationale,
            score=a.score,
            version=a.version,
            chunk_text=chunk.text,
            chunk_idx=chunk.idx,
            document_id=chunk.document_id,
            document_title=chunk.document.title if chunk.document else "",
        )
        for a in annotations
    ]


@router.get("/chunks/{chunk_id}/levels/{level}", response_model=AnnotationOut)
def get_chunk_annotation(chunk_id: int, level: str, db: Session = Depends(get_db)):
    annotation = (
        db.query(BloomAnnotation)
        .filter(BloomAnnotation.chunk_id == chunk_id, BloomAnnotation.level == level)
        .first()
    )
    if not annotation:
        raise HTTPException(404, "annotation not found")
    return annotation


@router.put("/chunks/{chunk_id}/levels/{level}", response_model=AnnotationOut)
def update_chunk_annotation(
    chunk_id: int,
    level: str,
    payload: AnnotationUpdateIn,
    db: Session = Depends(get_db),
):
    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(404, "chunk not found")

    annotation = (
        db.query(BloomAnnotation)
        .filter(BloomAnnotation.chunk_id == chunk_id, BloomAnnotation.level == level)
        .first()
    )
    if annotation:
        label = payload.label if payload.label is not None else annotation.label
        rationale = payload.rationale if payload.rationale is not None else annotation.rationale
        score = payload.score if payload.score is not None else annotation.score
    else:
        if payload.label is None or payload.rationale is None or payload.score is None:
            raise HTTPException(400, "label, rationale, score required for new annotation")
        label = payload.label
        rationale = payload.rationale
        score = payload.score

    ok, err = validate_annotation(
        {"level": level, "label": label, "rationale": rationale, "score": score}
    )
    if not ok:
        raise HTTPException(400, f"invalid annotation: {err}")

    if annotation:
        annotation.label = label
        annotation.rationale = rationale
        annotation.score = score
        annotation.version = (annotation.version or 1) + 1
    else:
        annotation = BloomAnnotation(
            chunk_id=chunk_id,
            level=level,
            label=label,
            rationale=rationale,
            score=score,
        )
        db.add(annotation)

    db.commit()
    db.refresh(annotation)
    return annotation


@router.delete("/chunks/{chunk_id}/levels/{level}")
def delete_chunk_annotation(chunk_id: int, level: str, db: Session = Depends(get_db)):
    annotation = (
        db.query(BloomAnnotation)
        .filter(BloomAnnotation.chunk_id == chunk_id, BloomAnnotation.level == level)
        .first()
    )
    if not annotation:
        raise HTTPException(404, "annotation not found")
    db.delete(annotation)
    db.commit()
    return {"ok": True}


@router.get("/datasets/{dataset_id}/annotations", response_model=AnnotationListOut)
def list_dataset_annotations(
    dataset_id: int,
    level: str | None = Query(None, pattern="^(remember|understand|apply|analyze|evaluate|create)$"),
    min_score: float | None = None,
    max_score: float | None = None,
    chunk_id: int | None = None,
    document_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    query = (
        db.query(BloomAnnotation, Chunk, Document)
        .join(Chunk, BloomAnnotation.chunk_id == Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.dataset_id == dataset_id)
    )
    if level:
        query = query.filter(BloomAnnotation.level == level)
    if min_score is not None:
        query = query.filter(BloomAnnotation.score >= min_score)
    if max_score is not None:
        query = query.filter(BloomAnnotation.score <= max_score)
    if chunk_id is not None:
        query = query.filter(BloomAnnotation.chunk_id == chunk_id)
    if document_id is not None:
        query = query.filter(Document.id == document_id)

    total = query.count()
    rows = query.order_by(BloomAnnotation.id.asc()).offset(offset).limit(limit).all()
    items = [
        AnnotationWithChunkOut(
            id=ann.id,
            chunk_id=ann.chunk_id,
            level=ann.level,
            label=ann.label,
            rationale=ann.rationale,
            score=ann.score,
            version=ann.version,
            chunk_text=chunk.text,
            chunk_idx=chunk.idx,
            document_id=doc.id,
            document_title=doc.title,
        )
        for ann, chunk, doc in rows
    ]
    return {"total": total, "items": items}
