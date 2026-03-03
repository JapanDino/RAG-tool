"""
Compat import path for Celery.

docker-compose and some scripts expect `app.celery_app:celery_app`.
The actual Celery instance lives in `app.tasks.celery_app`.
"""

from .tasks.celery_app import celery_app

__all__ = ["celery_app"]

