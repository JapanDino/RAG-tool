import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("rag_bloom", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.beat_schedule = {
    "expire-lti-binding-candidates-hourly": {
        "task": "expire_lti_binding_candidates",
        "schedule": crontab(minute=12),
    },
    "purge-expired-tutor-history-daily": {
        "task": "purge_expired_tutor_history",
        "schedule": crontab(hour=2, minute=15),
    },
}
celery_app.conf.timezone = "UTC"

# Ensure tasks are registered in the worker process.
celery_app.autodiscover_tasks(["app.tasks"])
