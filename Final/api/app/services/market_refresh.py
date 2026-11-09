"""Refreshes the shared job cache once a day for roles past their age limit (Design.md §4.4).

Every run costs credit, so a run is limited by `REFRESH_DAILY_CAP` and the weekly budget (FR-22c),
counted from `refresh_log` so a restart does not reset them. A role that was never seeded is left
to the seed: an empty database must not start spending by itself.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import to_bangkok, utcnow
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain import market
from app.domain.matching.roles import load_catalogue
from app.domain.matching.skills import load_taxonomy
from app.infra.models import RefreshLog, RoleCache
from app.providers.apify_jobthai import ApifyJobThaiProvider
from app.providers.base import JobDataProvider
from app.services import market_service

log = get_logger(__name__)

_EVERY_S = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class RefreshSummary:
    due: int
    ran: int
    failed: int


async def _runs_left(db: AsyncSession, settings: Settings, now: datetime) -> int:
    today = to_bangkok(now).date()
    monday = today - timedelta(days=today.weekday())
    runs = select(func.count()).select_from(RefreshLog)
    today_runs = await db.scalar(runs.where(RefreshLog.day == today)) or 0
    week_runs = await db.scalar(runs.where(RefreshLog.day >= monday)) or 0
    return max(
        0, min(settings.refresh_daily_cap - today_runs, settings.apify_weekly_budget - week_runs)
    )


async def refresh_due_roles(
    db: AsyncSession, provider: JobDataProvider, settings: Settings, now: datetime
) -> RefreshSummary:
    """Healthy roles go first, oldest first, so one that keeps failing cannot use up the budget."""
    catalogue = {role.role_id: role for role in load_catalogue(settings.data_dir)}
    caches = await db.scalars(
        select(RoleCache)
        .where(RoleCache.fetched_at.is_not(None))
        .execution_options(populate_existing=True)
    )
    due = sorted(
        (
            cache
            for cache in caches
            if cache.role_id in catalogue and not market_service.is_fresh(cache, settings, now)
        ),
        key=lambda cache: (cache.last_error is not None, to_bangkok(cache.fetched_at)),
    )
    role_ids = [cache.role_id for cache in due]
    to_run = role_ids[: await _runs_left(db, settings, now)]
    searches = market.load_role_search(settings.data_dir)
    taxonomy = load_taxonomy(settings.data_dir)
    failed = 0
    for role_id in to_run:
        try:
            result = await market_service.refresh_role(
                db, provider, catalogue[role_id], searches=searches, taxonomy=taxonomy
            )
        except Exception as error:
            await db.rollback()
            failed += 1
            log.warning("market_refresh_role_failed", role_id=role_id, error=type(error).__name__)
            continue
        if not result.ok:
            failed += 1
            log.warning("market_refresh_role_failed", role_id=role_id, error=result.error)
    return RefreshSummary(due=len(role_ids), ran=len(to_run), failed=failed)


async def _clear_refreshing(sessions: async_sessionmaker[AsyncSession]) -> None:
    """A flag still set at start-up was left by an api that stopped during a fetch (FR-22d)."""
    async with sessions() as db:
        await db.execute(
            update(RoleCache).where(RoleCache.refreshing.is_(True)).values(refreshing=False)
        )
        await db.commit()


async def run_daily(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    provider: JobDataProvider | None = None,
) -> None:
    """Runs until cancelled. A failed run only waits for the next one. No token: nothing to do."""
    try:
        await _clear_refreshing(sessions)
    except Exception as error:
        log.warning("market_refresh_failed", error=type(error).__name__)
    if not settings.apify_token:
        log.info("market_refresh_off", reason="no_token")
        return
    provider = provider or ApifyJobThaiProvider(settings.apify_token, settings.apify_jobthai_actor)
    while True:
        try:
            async with sessions() as db:
                summary = await refresh_due_roles(db, provider, settings, utcnow())
            log.info(
                "market_refresh_finished",
                due=summary.due,
                ran=summary.ran,
                failed=summary.failed,
            )
        except Exception as error:
            log.warning("market_refresh_failed", error=type(error).__name__)
        await asyncio.sleep(_EVERY_S)
