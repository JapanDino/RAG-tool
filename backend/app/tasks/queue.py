import os
from sqlalchemy.orm import Session
from sqlalchemy import text
from .celery_app import celery_app
from .tasks import index_dataset, annotate_dataset
from ..models.models import Job, JobStatus, JobType

ENABLE_CELERY = os.getenv("ENABLE_CELERY", "1") not in ("0", "false", "False")

def enqueue_or_mark(db: Session, job: Job):
    """
    Если Celery включён — отправляем в очередь и сохраняем task_id.
    Если нет — оставляем queued (или можно вызвать синхронно по желанию).
    """
    try:
        if job.type == JobType.index:
            if ENABLE_CELERY:
                async_result = index_dataset.delay(job.payload["dataset_id"])
                db.execute(
                    text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                    dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
                )
                db.commit()
            else:
                # оставить queued; можно предусмотреть sync-run при необходимости
                pass
        elif job.type == JobType.annotate:
            if ENABLE_CELERY:
                async_result = annotate_dataset.delay(
                    job.payload["dataset_id"], job.payload["level"]
                )
                db.execute(
                    text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                    dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
                )
                db.commit()
            else:
                pass
        elif job.type == JobType.export:
            pass
    except Exception as e:
        db.execute(
            text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
            dict(err=str(e), id=job.id),
        )
        db.commit()
        raise
