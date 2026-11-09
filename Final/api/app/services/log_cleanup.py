"""Deletes old `request_log` and `llm_calls` rows once a day (Design.md §4.8)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.models import LlmCall, RequestLog

log = get_logger(__name__)

_EVERY_S = 24 * 60 * 60


async def delete_old_logs(db: AsyncSession, settings: Settings, now: datetime) -> None:
    cutoff = now - timedelta(days=settings.log_retention_days)
    await db.execute(delete(RequestLog).where(RequestLog.created_at < cutoff))
    await db.execute(delete(LlmCall).where(LlmCall.created_at < cutoff))
    await db.commit()


async def run_daily(sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Runs until cancelled. A failed run only waits for the next one."""
    while True:
        try:
            async with sessions() as db:
                await delete_old_logs(db, settings, utcnow())
        except Exception as error:
            log.warning("log_cleanup_failed", error=type(error).__name__)
        await asyncio.sleep(_EVERY_S)
