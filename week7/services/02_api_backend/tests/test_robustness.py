"""Failures found by running the api in docker compose (Postgres + Redis + stubs)."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from redis.exceptions import RedisError

from app.api.deps import Container
from app.core.errors import AppError, ErrorCode
from app.infra.store import MemoryStore, RedisStore
from app.response_log.cursor import decode_cursor
from tests.conftest import DEMO_PASSWORD, ClientFactory, assert_problem, make_settings
from tests.test_chat import ask

# ------------------------------------------------------------ 1. NUL bytes
# Postgres text columns cannot hold U+0000; SQLite can, so these are checked as input.


async def test_chat_message_with_nul_is_422(demo: httpx.AsyncClient) -> None:
    response = await demo.post("/api/chat", json={"session_id": None, "message": "ปืน\u0000ใหญ่"})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_login_username_with_nul_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": "demo\u00001", "password": DEMO_PASSWORD}
    )
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_feedback_comment_with_nul_is_422(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    response = await demo.post(
        "/api/feedback",
        json={"message_id": body["message_id"], "rating": -1, "comment": "ผิด\u0000"},
    )
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_admin_user_search_with_nul_is_422(admin: httpx.AsyncClient) -> None:
    response = await admin.get("/api/admin/users", params={"q": "demo\u0000"})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_report_patch_with_nul_is_422(admin: httpx.AsyncClient) -> None:
    await admin.post("/api/admin/reports/generate", json={"season": "2026", "matchweek": 5})
    response = await admin.patch("/api/admin/reports/2026/5", json={"title": "แก้\u0000"})
    assert_problem(response, 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ 2. concurrent feedback


async def test_concurrent_feedback_on_one_answer_never_fails(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    await asyncio.sleep(0.1)  # let the background write finish
    responses = await asyncio.gather(
        *[
            demo.post("/api/feedback", json={"message_id": body["message_id"], "rating": r})
            for r in (1, -1, 1, -1, 1, -1)
        ]
    )
    assert [r.status_code for r in responses] == [200] * 6
    history = (await demo.get(f"/api/history/{body['session_id']}")).json()["messages"]
    assert history[1]["rating"] in (1, -1)


# ------------------------------------------------------------ 3. login rate limit


@pytest.mark.parametrize("settings_overrides", [{"login_rate_limit_per_minute": 2}])
async def test_successful_logins_are_not_rate_limited(client: httpx.AsyncClient) -> None:
    # Every user reaches the api through the web proxy, so they share one client IP.
    for username in ("demo1", "demo2", "demo3", "demo1", "demo2"):
        response = await client.post(
            "/api/auth/login", json={"username": username, "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("settings_overrides", [{"login_rate_limit_per_minute": 2}])
async def test_failed_logins_lock_only_that_username(client: httpx.AsyncClient) -> None:
    for _ in range(2):
        wrong = await client.post("/api/auth/login", json={"username": "demo1", "password": "x"})
        assert_problem(wrong, 401, "UNAUTHENTICATED")
    locked = await client.post(
        "/api/auth/login", json={"username": "demo1", "password": DEMO_PASSWORD}
    )
    assert_problem(locked, 429, "RATE_LIMITED")
    assert locked.headers["retry-after"].isdigit()
    other = await client.post(
        "/api/auth/login", json={"username": "demo2", "password": DEMO_PASSWORD}
    )
    assert other.status_code == 200, other.text


# ------------------------------------------------------------ 4. favorite_team_id range


async def test_favorite_team_id_beyond_int32_is_422(demo: httpx.AsyncClient) -> None:
    response = await demo.patch("/api/me/preferences", json={"favorite_team_id": 2**31})
    assert_problem(response, 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ 5. cursor out of range


def _cursor(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def test_cursor_time_out_of_range_is_validation_error() -> None:
    cursor = _cursor({"t": "0001-01-01T00:00:00+14:00", "id": str(uuid.uuid4())})
    with pytest.raises(AppError) as err:
        decode_cursor(cursor)
    assert err.value.code is ErrorCode.VALIDATION_ERROR


def test_cursor_without_offset_is_read_as_utc() -> None:
    decoded_at, _ = decode_cursor(_cursor({"t": "2026-09-25T00:00:00", "id": "x"}))
    assert decoded_at.utcoffset() is not None


# ------------------------------------------------------------ 6. Redis down


class FailingRedis:
    """Stands in for redis.asyncio.Redis when the server is unreachable."""

    def __init__(self) -> None:
        self.calls = 0

    async def get(self, _key: str) -> Any:
        self.calls += 1
        raise RedisError("connection refused")

    async def set(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        raise RedisError("connection refused")


async def test_redis_store_stops_calling_redis_after_a_failure() -> None:
    redis = FailingRedis()
    store = RedisStore(redis)  # type: ignore[arg-type]
    assert await store.get_json("a") is None
    assert await store.get_json("b") is None
    await store.set_json("c", 1, 60)
    assert redis.calls == 1
    assert store.available is False


async def test_redis_store_tries_again_after_the_pause() -> None:
    redis = FailingRedis()
    now = [100.0]
    store = RedisStore(redis, down_seconds=5, clock=lambda: now[0])  # type: ignore[arg-type]
    await store.get_json("a")
    now[0] += 6
    assert store.available is True
    await store.get_json("a")
    assert redis.calls == 2


class UnavailableStore(MemoryStore):
    """A store that has lost what it held (Redis down): reads miss."""

    available = False

    async def get_json(self, key: str) -> Any | None:
        return None


async def test_feedback_waits_when_store_is_down(
    demo: httpx.AsyncClient, container: Container
) -> None:
    # Without the pending marker, "not written yet" cannot be told from "does not exist";
    # answer 409 so the web retries instead of dropping the rating.
    container.store = UnavailableStore()
    response = await demo.post("/api/feedback", json={"message_id": str(uuid.uuid4()), "rating": 1})
    assert_problem(response, 409, "MESSAGE_NOT_READY")


# ------------------------------------------------------------ 7. football-data down


class CountingDownTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        raise httpx.ConnectError("connection refused", request=request)


class TestFootballDataDown:
    @pytest.fixture
    def football_transport(self) -> httpx.AsyncBaseTransport:
        return CountingDownTransport()

    async def test_chat_does_not_retry_football_status_on_every_call(
        self, client_factory: ClientFactory, football_transport: CountingDownTransport
    ) -> None:
        demo = client_factory()
        await demo.post("/api/auth/login", json={"username": "demo1", "password": DEMO_PASSWORD})
        await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
        await ask(demo, "ตารางคะแนน")
        assert football_transport.calls == 1


# ------------------------------------------------------------ 8. tests ignore the environment


def test_settings_in_tests_ignore_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_SHA", "from-env")
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "1")
    settings = make_settings(tmp_path)
    assert settings.version == "0.1.0"
    assert settings.chat_rate_limit_per_minute == 20
