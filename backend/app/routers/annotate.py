from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.models import Dataset, Job, JobType, JobStatus
from ..tasks.queue import enqueue_or_mark

router = APIRouter(prefix="/annotate", tags=["annotate"])

@router.post("/datasets/{dataset_id}")
def start_annotate(dataset_id: int, level: str = Query(..., pattern="^(remember|understand|apply|analyze|evaluate|create)$"), db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds: raise HTTPException(404, "dataset not found")
    job = Job(type=JobType.annotate, status=JobStatus.queued, payload={"dataset_id": dataset_id, "level": level})
    db.add(job); db.commit(); db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}
