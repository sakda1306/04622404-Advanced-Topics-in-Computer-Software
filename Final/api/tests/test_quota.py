"""Quota service and headers (PRD FR-23 – FR-25, Contract.md §1 and §2.8, Design.md §4.7)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.deps import Container
from app.core.errors import AppError, ErrorCode
from app.infra.models import QuotaUsage
from app.services import quota_service
from tests.conftest import ClientFactory, assert_problem, register

# 23:30 Bangkok on 3 Nov 2026 (16:30 UTC): the next reset is 4 Nov 00:00 Bangkok.
NOW = datetime(2026, 11, 3, 16, 30, tzinfo=UTC)
NEXT_DAY = datetime(2026, 11, 3, 17, 30, tzinfo=UTC)  # 00:30 Bangkok on 4 Nov

SMALL = {"quota_daily_requests": 3, "quota_daily_tokens": 1000}


async def _user_id(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/auth/me")
    user_id: str = response.json()["user"]["id"]
    return user_id


async def _reserve(container: Container, user_id: str, **kwargs: Any) -> date:
    async with container.sessions() as db:
        return await quota_service.reserve(db, user_id, container.settings, **kwargs)


async def _status(container: Container, user_id: str, now: datetime = NOW) -> Any:
    async with container.sessions() as db:
        return await quota_service.get_quota(db, user_id, container.settings, now=now)


def test_default_limits_match_design() -> None:
    from tests.conftest import IsolatedSettings

    settings = IsolatedSettings(jwt_secret="s" * 32)
    assert (settings.quota_daily_requests, settings.quota_daily_tokens) == (40, 40_000)


def test_day_and_reset_follow_bangkok() -> None:
    assert quota_service.quota_day(NOW, "Asia/Bangkok") == date(2026, 11, 3)
    assert quota_service.quota_day(NEXT_DAY, "Asia/Bangkok") == date(2026, 11, 4)
    reset = quota_service.reset_at(NOW, "Asia/Bangkok")
    assert reset.isoformat() == "2026-11-04T00:00:00+07:00"


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_new_user_has_full_quota(container: Container, user: httpx.AsyncClient) -> None:
    status = await _status(container, await _user_id(user))
    assert (status.requests_used, status.tokens_used) == (0, 0)
    assert (status.requests_limit, status.tokens_limit) == (3, 1000)
    assert status.exhausted is False


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_reserve_counts_one_request(container: Container, user: httpx.AsyncClient) -> None:
    user_id = await _user_id(user)
    day = await _reserve(container, user_id, now=NOW)
    assert day == date(2026, 11, 3)
    assert (await _status(container, user_id)).requests_used == 1


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_request_limit_blocks_with_reset_time(
    container: Container, user: httpx.AsyncClient
) -> None:
    user_id = await _user_id(user)
    for _ in range(3):
        await _reserve(container, user_id, now=NOW)
    with pytest.raises(AppError) as caught:
        await _reserve(container, user_id, now=NOW)
    assert caught.value.code == ErrorCode.QUOTA_EXCEEDED
    assert caught.value.details == {"reset_at": "2026-11-04T00:00:00+07:00", "reason": "requests"}
    status = await _status(container, user_id)
    assert status.requests_used == 3
    assert status.exhausted is True


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_token_limit_blocks(container: Container, user: httpx.AsyncClient) -> None:
    user_id = await _user_id(user)
    day = await _reserve(container, user_id, now=NOW)
    async with container.sessions() as db:
        await quota_service.add_tokens(db, user_id, day, 900)
    with pytest.raises(AppError) as caught:
        await _reserve(container, user_id, now=NOW, estimated_tokens=200)
    assert caught.value.details is not None
    assert caught.value.details["reason"] == "tokens"
    assert (await _status(container, user_id)).requests_used == 1


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_tokens_add_up(container: Container, user: httpx.AsyncClient) -> None:
    user_id = await _user_id(user)
    day = await _reserve(container, user_id, now=NOW)
    async with container.sessions() as db:
        await quota_service.add_tokens(db, user_id, day, 400)
        await quota_service.add_tokens(db, user_id, day, 250)
    assert (await _status(container, user_id)).tokens_used == 650


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_refund_gives_the_request_back(container: Container, user: httpx.AsyncClient) -> None:
    # Contract §4: LLM_UNAVAILABLE and LLM_TIMEOUT refund the quota.
    user_id = await _user_id(user)
    day = await _reserve(container, user_id, now=NOW)
    async with container.sessions() as db:
        await quota_service.refund(db, user_id, day)
        await quota_service.refund(db, user_id, day)  # never below zero
    assert (await _status(container, user_id)).requests_used == 0


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_new_day_starts_fresh(container: Container, user: httpx.AsyncClient) -> None:
    user_id = await _user_id(user)
    for _ in range(3):
        await _reserve(container, user_id, now=NOW)
    await _reserve(container, user_id, now=NEXT_DAY)
    assert (await _status(container, user_id, now=NEXT_DAY)).requests_used == 1


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_parallel_reserves_cannot_pass_the_limit(
    container: Container, user: httpx.AsyncClient
) -> None:
    user_id = await _user_id(user)
    results = await asyncio.gather(
        *(_reserve(container, user_id, now=NOW) for _ in range(8)), return_exceptions=True
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 3
    assert all(
        isinstance(r, AppError) and r.code == ErrorCode.QUOTA_EXCEEDED
        for r in results
        if isinstance(r, BaseException)
    )
    assert (await _status(container, user_id)).requests_used == 3


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_get_quota_endpoint(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/quota")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "day",
        "requests_used",
        "requests_limit",
        "tokens_used",
        "tokens_limit",
        "reset_at",
        "exhausted",
    }
    assert body["requests_limit"] == 3
    assert body["tokens_limit"] == 1000
    assert body["reset_at"].endswith("T00:00:00+07:00")
    assert body["exhausted"] is False


async def test_get_quota_needs_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/quota"), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("settings_overrides", [SMALL])
async def test_authenticated_responses_carry_quota_headers(
    container: Container, user: httpx.AsyncClient
) -> None:
    await _reserve(container, await _user_id(user))
    response = await user.get("/api/auth/me")
    assert response.headers["x-quota-requests-remaining"] == "2"
    assert response.headers["x-quota-tokens-remaining"] == "1000"
    assert response.headers["x-quota-reset"].endswith("T00:00:00+07:00")


async def test_anonymous_responses_have_no_quota_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert "x-quota-requests-remaining" not in response.headers


async def test_failed_auth_has_no_quota_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert "x-quota-requests-remaining" not in response.headers


async def test_delete_account_removes_quota_rows(
    container: Container, client_factory: ClientFactory
) -> None:
    c = client_factory()
    await register(c, email="gone@example.com")
    await _reserve(container, await _user_id(c))
    response = await c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200
    assert "x-quota-requests-remaining" not in response.headers
    async with container.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(QuotaUsage)) == 0
