import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.models import Job
from ..tasks.celery_app import celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "job not found")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "task_id": job.task_id,
        "payload": job.payload,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "error": job.error
    }

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
