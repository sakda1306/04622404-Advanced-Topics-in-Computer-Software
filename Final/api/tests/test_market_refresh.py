"""The scheduled refresh of the shared job cache (PRD FR-22b, FR-22c, Design.md §4.4)."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container
from app.core.clock import to_bangkok, utcnow
from app.core.config import Settings
from app.domain import market
from app.domain.matching.roles import load_catalogue
from app.infra.models import RefreshLog, RoleCache
from app.main import create_app
from app.providers.base import Posting, ProviderError
from app.services import market_refresh

DATA_DIR = "../data"
SEARCHES = market.load_role_search(DATA_DIR)
FIRST, SECOND, THIRD = (role.role_id for role in load_catalogue(DATA_DIR)[:3])


def _posting() -> Posting:
    return Posting(
        source="jobthai",
        title="Data Analyst",
        company="บริษัท ตัวอย่าง จำกัด",
        location="เขตจตุจักร กรุงเทพมหานคร",
        province="กรุงเทพมหานคร",
        salary_text="30,000 - 40,000 บาท",
        posted_text="31 ต.ค. 69",
        url="https://www.jobthai.com/th/job/1",
        text="ใช้ SQL และ Python",
    )


class FakeProvider:
    name = "fake"

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.roles: list[str] = []

    async def fetch_postings(self, keyword: str, limit: int) -> list[Posting]:
        role_id = next(key for key, search in SEARCHES.items() if search.keyword == keyword)
        self.roles.append(role_id)
        if role_id in self.failures:
            raise self.failures[role_id]
        return [_posting()]


def _settings(container: Container, **overrides: Any) -> Settings:
    return container.settings.model_copy(update=overrides)


async def _cache(db: AsyncSession, role_id: str, age_days: float | None, **fields: Any) -> None:
    fetched_at = None if age_days is None else utcnow() - timedelta(days=age_days)
    db.add(RoleCache(role_id=role_id, fetched_at=fetched_at, **fields))
    await db.commit()


async def _runs(db: AsyncSession, now: datetime, count: int) -> None:
    day = to_bangkok(now).date()
    db.add_all(RefreshLog(day=day, role_id=FIRST, status="ok") for _ in range(count))
    await db.commit()


# --- which roles run


async def test_only_a_role_older_than_the_limit_is_fetched(container: Container) -> None:
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await _cache(db, SECOND, 6)
        await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == [FIRST]


async def test_a_role_at_exactly_the_limit_is_due(container: Container) -> None:
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, container.settings.cache_max_age_days)
        await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == [FIRST]


async def test_a_role_that_was_never_seeded_is_not_fetched(container: Container) -> None:
    """An empty database must not spend credit by itself: filling it is the seed's job."""
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, None)
        result = await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == []
    assert result.due == 0


async def test_the_oldest_role_goes_first(container: Container) -> None:
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await _cache(db, SECOND, 20)
        await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == [SECOND, FIRST]


async def test_a_refreshed_role_is_not_fetched_again(container: Container) -> None:
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
        await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == [FIRST]


# --- the budgets


async def test_the_daily_cap_leaves_the_rest_for_the_next_day(container: Container) -> None:
    settings = _settings(container, refresh_daily_cap=2)
    provider = FakeProvider()
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 30)
        await _cache(db, SECOND, 20)
        await _cache(db, THIRD, 10)
        first = await market_refresh.refresh_due_roles(db, provider, settings, now)
        assert provider.roles == [FIRST, SECOND]
        assert (first.due, first.ran) == (3, 2)

        same_day = await market_refresh.refresh_due_roles(db, provider, settings, now)
        assert provider.roles == [FIRST, SECOND]
        assert (same_day.due, same_day.ran) == (1, 0)

        await market_refresh.refresh_due_roles(db, provider, settings, now + timedelta(days=1))
    assert provider.roles == [FIRST, SECOND, THIRD]


async def test_runs_already_made_today_count_toward_the_cap(container: Container) -> None:
    settings = _settings(container, refresh_daily_cap=2)
    provider = FakeProvider()
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await _runs(db, now, 2)
        await market_refresh.refresh_due_roles(db, provider, settings, now)
    assert provider.roles == []


async def test_the_weekly_budget_stops_the_run(container: Container) -> None:
    settings = _settings(container, apify_weekly_budget=3, refresh_daily_cap=20)
    provider = FakeProvider()
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 30)
        await _cache(db, SECOND, 20)
        await _runs(db, now, 2)
        await market_refresh.refresh_due_roles(db, provider, settings, now)
    assert provider.roles == [FIRST]


async def test_runs_of_last_week_do_not_count(container: Container) -> None:
    settings = _settings(container, apify_weekly_budget=2)
    provider = FakeProvider()
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await _runs(db, now - timedelta(days=7), 2)
        await market_refresh.refresh_due_roles(db, provider, settings, now)
    assert provider.roles == [FIRST]


async def test_being_over_budget_fetches_nothing(container: Container) -> None:
    """52 runs were made on 3 Nov against a budget of 26, so the count can already be over."""
    settings = _settings(container, apify_weekly_budget=26, refresh_daily_cap=100)
    provider = FakeProvider()
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        await _cache(db, SECOND, 9)
        await _runs(db, now, 27)
        result = await market_refresh.refresh_due_roles(db, provider, settings, now)
    assert provider.roles == []
    assert result.ran == 0


# --- failures


async def test_a_failed_role_is_retried_at_the_next_run(container: Container) -> None:
    provider = FakeProvider({FIRST: ProviderError("http_500")})
    now = utcnow()
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
        result = await market_refresh.refresh_due_roles(db, provider, container.settings, now)
        assert result.failed == 1
        provider.failures = {}
        await market_refresh.refresh_due_roles(db, provider, container.settings, now)
        cache = await db.get(RoleCache, FIRST, populate_existing=True)
    assert provider.roles == [FIRST, FIRST]
    assert cache is not None
    assert cache.last_error is None


async def test_a_role_that_keeps_failing_runs_after_the_healthy_ones(
    container: Container,
) -> None:
    """It is the oldest and would go first every day, using up the budget of the others."""
    settings = _settings(container, refresh_daily_cap=1)
    provider = FakeProvider()
    async with container.sessions() as db:
        await _cache(db, FIRST, 30, last_error="no_results")
        await _cache(db, SECOND, 8)
        await market_refresh.refresh_due_roles(db, provider, settings, utcnow())
    assert provider.roles == [SECOND]


async def test_an_unexpected_error_does_not_stop_the_other_roles(container: Container) -> None:
    provider = FakeProvider({FIRST: ValueError("broken")})
    async with container.sessions() as db:
        await _cache(db, FIRST, 30)
        await _cache(db, SECOND, 8)
        result = await market_refresh.refresh_due_roles(db, provider, container.settings, utcnow())
    assert provider.roles == [FIRST, SECOND]
    assert (result.ran, result.failed) == (2, 1)


# --- the loop


async def test_no_token_makes_no_call_and_marks_no_error(container: Container) -> None:
    """Without this every role would get `no_token` and show as failed."""
    async with container.sessions() as db:
        await _cache(db, FIRST, 8)
    await asyncio.wait_for(
        market_refresh.run_daily(container.sessions, _settings(container, apify_token="")),
        timeout=5,
    )
    async with container.sessions() as db:
        cache = await db.get(RoleCache, FIRST)
        runs = await db.scalar(select(func.count()).select_from(RefreshLog))
    assert cache is not None
    assert cache.last_error is None
    assert runs == 0


@pytest.mark.parametrize("token", ["", "secret-token"])
async def test_starting_clears_a_refreshing_flag_left_by_a_stopped_api(
    container: Container, monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    """Otherwise the web keeps polling a role nobody is fetching (FR-22d)."""

    async def stop(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(market_refresh.asyncio, "sleep", stop)
    async with container.sessions() as db:
        await _cache(db, FIRST, 1, refreshing=True)
    settings = _settings(container, apify_token=token)
    with pytest.raises(asyncio.CancelledError) if token else nullcontext():
        await market_refresh.run_daily(container.sessions, settings, FakeProvider())
    async with container.sessions() as db:
        cache = await db.get(RoleCache, FIRST)
    assert cache is not None
    assert cache.refreshing is False


async def test_a_failed_run_waits_a_day_and_runs_again(
    container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []
    calls = 0

    async def broken(*_args: object) -> market_refresh.RefreshSummary:
        nonlocal calls
        calls += 1
        raise RuntimeError("database is down")

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(market_refresh, "refresh_due_roles", broken)
    monkeypatch.setattr(market_refresh.asyncio, "sleep", sleep)
    settings = _settings(container, apify_token="secret-token")
    with pytest.raises(asyncio.CancelledError):
        await market_refresh.run_daily(container.sessions, settings, FakeProvider())
    assert calls == 2
    assert waits == [24 * 60 * 60, 24 * 60 * 60]


async def test_the_app_starts_the_job_and_stops_it(
    container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def job(*_args: object) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            stopped.set()
            raise

    monkeypatch.setattr(market_refresh, "run_daily", job)
    monkeypatch.setattr(container.knowledge, "load", lambda _settings: None)
    app: FastAPI = create_app(container.settings, container)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=5)
        assert not stopped.is_set()
    assert stopped.is_set()
