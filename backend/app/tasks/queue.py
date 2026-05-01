import logging
import os
from sqlalchemy.orm import Session
from sqlalchemy import text
from .celery_app import celery_app
from .tasks import index_dataset, annotate_dataset, rebuild_graph_edges, parse_document, reindex_dataset_nodes
from ..models.models import Job, JobStatus, JobType

logger = logging.getLogger(__name__)

ENABLE_CELERY = os.getenv("ENABLE_CELERY", "1") not in ("0", "false", "False")


def _run_sync(db: Session, job: Job):
    """Run a job synchronously (used when ENABLE_CELERY=0)."""
    db.execute(text("UPDATE jobs SET status='running' WHERE id=:id"), {"id": job.id})
    db.commit()
    try:
        if job.type == JobType.index:
            index_dataset(job.payload["dataset_id"], job.id)
        elif job.type == JobType.annotate:
            annotate_dataset(job.payload["dataset_id"], job.payload["level"], job.id)
        elif job.type == JobType.parse:
            parse_document(
                job.payload["document_id"],
                job.payload["file_path"],
                job.payload["filename"],
                job.payload["content_type"],
                job.id,
            )
        elif job.type == JobType.graph:
            if job.payload.get("action") == "reindex":
                reindex_dataset_nodes(job.payload["dataset_id"], job.id)
            else:
                rebuild_graph_edges(
                    job.payload["dataset_id"],
                    job.id,
                    job.payload.get("embedding_model"),
                    job.payload.get("top_k", 5),
                    job.payload.get("min_score", 0.2),
                    job.payload.get("max_edges", 200),
                    job.payload.get("include_cooccurrence", True),
                    job.payload.get("limit_nodes", 500),
                    job.payload.get("co_window", 2),
                )
        else:
            db.execute(text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"), {"id": job.id})
            db.commit()
    except Exception as e:
        logger.exception("Sync job %d (%s) failed: %s", job.id, job.type, e)
        raise


def enqueue_or_mark(db: Session, job: Job):
    """
    Если Celery включён — отправляем в очередь и сохраняем task_id.
    Если нет — запускаем синхронно (блокирует HTTP-запрос, но задача выполняется).
    """
    if not ENABLE_CELERY:
        _run_sync(db, job)
        return

    try:
        if job.type == JobType.index:
            async_result = index_dataset.delay(job.payload["dataset_id"], job.id)
            db.execute(
                text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
            )
            db.commit()
        elif job.type == JobType.annotate:
            async_result = annotate_dataset.delay(
                job.payload["dataset_id"], job.payload["level"], job.id
            )
            db.execute(
                text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
            )
            db.commit()
        elif job.type == JobType.parse:
            async_result = parse_document.delay(
                job.payload["document_id"],
                job.payload["file_path"],
                job.payload["filename"],
                job.payload["content_type"],
                job.id,
            )
            db.execute(
                text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
            )
            db.commit()
        elif job.type == JobType.export:
            pass
        elif job.type == JobType.graph:
            if job.payload.get("action") == "reindex":
                async_result = reindex_dataset_nodes.delay(job.payload["dataset_id"], job.id)
            else:
                async_result = rebuild_graph_edges.delay(
                    job.payload["dataset_id"],
                    job.id,
                    job.payload.get("embedding_model"),
                    job.payload.get("top_k", 5),
                    job.payload.get("min_score", 0.2),
                    job.payload.get("max_edges", 200),
                    job.payload.get("include_cooccurrence", True),
                    job.payload.get("limit_nodes", 500),
                    job.payload.get("co_window", 2),
                )
            db.execute(
                text("UPDATE jobs SET status=:st, task_id=:tid WHERE id=:id"),
                dict(st=JobStatus.queued.value, tid=async_result.id, id=job.id),
            )
            db.commit()
    except Exception as e:
        db.execute(
            text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
            dict(err=str(e), id=job.id),
        )
        db.commit()
        raise
