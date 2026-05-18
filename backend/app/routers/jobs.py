import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.models import Job, JobType, JobStatus
from ..tasks.celery_app import celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "task_id": job.task_id,
        "payload": job.payload,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "error": job.error,
    }


@router.get("")
def list_jobs(
    dataset_id: int | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Job)
    if dataset_id is not None:
        q = q.filter(Job.payload["dataset_id"].as_integer() == dataset_id)
    if type is not None:
        q = q.filter(Job.type == type)
    if status is not None:
        q = q.filter(Job.status == status)
    total = q.count()
    items = q.order_by(Job.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_job_dict(j) for j in items]}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return _job_dict(job)

@router.get("/{job_id}/state")
def get_job_state(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "job not found")
    if not job.task_id:
        return {"job_id": job.id, "status": job.status, "celery": None}
    if os.getenv("ENABLE_CELERY", "1") in ("0", "false", "False"):
        return {"job_id": job.id, "status": job.status, "celery": {"enabled": False}}
    res = celery_app.AsyncResult(job.task_id)
    info = res.info if isinstance(res.info, dict) else str(res.info) if res.info else None
    return {
        "job_id": job.id,
        "status": job.status,
        "task_id": job.task_id,
        "celery": {
            "state": res.state,
            "ready": res.ready(),
            "successful": res.successful(),
            "info": info,
        },
    }
