from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import get_db
from ..models.models import Dataset, Document, Chunk, Job, JobType, JobStatus
from ..tasks.queue import enqueue_or_mark
from ..schemas.schemas import DatasetIn, DatasetOut
import uuid

router = APIRouter(prefix="/datasets", tags=["datasets"])

@router.post("", response_model=DatasetOut)
def create_dataset(data: DatasetIn, db: Session = Depends(get_db)):
    ds = Dataset(name=data.name)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.post("/{dataset_id}/documents")
def upload_document(dataset_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds: raise HTTPException(404, "dataset not found")
    doc = Document(dataset_id=dataset_id, title=file.filename, source=f"upload://{uuid.uuid4()}", mime=file.content_type or "application/octet-stream")
    db.add(doc); db.commit(); db.refresh(doc)
    text_bytes = file.file.read()
    try:
        text_str = text_bytes.decode("utf-8")
    except Exception:
        text_str = text_bytes.decode("latin-1", errors="ignore")
    parts = [text_str[i:i+800] for i in range(0, len(text_str), 800)]
    for i, p in enumerate(parts):
        db.add(Chunk(document_id=doc.id, idx=i, text=p, meta={}))
    db.commit()
    return {"document_id": doc.id, "chunks": len(parts)}

@router.post("/{dataset_id}/index")
def start_index(dataset_id: int, db: Session = Depends(get_db)):
    job = Job(type=JobType.index, status=JobStatus.queued, payload={"dataset_id": dataset_id})
    db.add(job); db.commit(); db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}

@router.post("/{dataset_id}/annotate")
def start_annotate(dataset_id: int, level: str = Query(..., pattern="^(remember|understand|apply|analyze|evaluate|create)$"), db: Session = Depends(get_db)):
    job = Job(type=JobType.annotate, status=JobStatus.queued, payload={"dataset_id": dataset_id, "level": level})
    db.add(job); db.commit(); db.refresh(job)
    return {"job_id": job.id}
