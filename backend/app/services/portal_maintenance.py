"""Expiry of quality records also runs when nobody opens the teacher console."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from ..db.session import SessionLocal

logger = logging.getLogger(__name__)


def purge_expired():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM portal_quality WHERE day <= CURRENT_DATE-30"))
        db.commit()


async def maintain():
    while True:
        try:
            await run_in_threadpool(purge_expired)
        except Exception:  # noqa: BLE001 - Keep API available; do not log personal content.
            logger.warning("Portal quality retention cleanup failed; retry in one hour")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(maintain()) if os.getenv("APP_MODE") == "lti" else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
