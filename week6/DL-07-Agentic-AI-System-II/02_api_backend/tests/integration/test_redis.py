"""The Lua scripts against a real Redis 7 (fakeredis may differ in edge cases)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.config import RedisSettings
from app.infrastructure.redis.clients import create_redis_clients
from app.infrastructure.redis.idempotency_store import (
    BeginOutcome,
    RedisIdempotencyStore,
    StoredResponse,
)
from app.infrastructure.redis.rate_limiter import RedisRateLimiter
from app.infrastructure.redis.slots import RedisSlotLimiter

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    try:
        from testcontainers.community.redis import RedisContainer

        container = RedisContainer("redis:7-alpine")
        container.start()
    except Exception as exc:
        pytest.skip(f"Redis container unavailable: {type(exc).__name__}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushall()
    try:
        yield client
    finally:
        await client.aclose()


async def test_rate_limit_is_atomic_under_concurrency(redis: Redis) -> None:
    limiter = RedisRateLimiter(redis)

    decisions = await asyncio.gather(
        *(limiter.hit("rl", limit=10, window_seconds=60) for _ in range(50))
    )

    assert sum(d.allowed for d in decisions) == 10
    assert await redis.zcard("rl") == 10


async def test_only_one_concurrent_request_starts(redis: Redis) -> None:
    store = RedisIdempotencyStore(redis)

    results = await asyncio.gather(
        *(store.begin("idem", "hash", lock_seconds=30) for _ in range(20))
    )

    outcomes = [r.outcome for r in results]
    assert outcomes.count(BeginOutcome.STARTED) == 1
    assert outcomes.count(BeginOutcome.IN_PROGRESS) == 19


async def test_binary_body_round_trips(redis: Redis) -> None:
    store = RedisIdempotencyStore(redis)
    response = StoredResponse(201, {"location": "/x"}, "สวัสดี".encode() + bytes(range(256)))
    started = await store.begin("idem", "hash", lock_seconds=30)

    assert await store.complete("idem", started.owner, response, ttl_seconds=60)
    replay = await store.begin("idem", "hash", lock_seconds=30)

    assert replay.response == response


async def test_lock_expires_so_a_crashed_request_does_not_block_forever(redis: Redis) -> None:
    store = RedisIdempotencyStore(redis)
    await store.begin("idem", "hash", lock_seconds=1)

    await asyncio.sleep(1.2)

    assert (await store.begin("idem", "hash", lock_seconds=1)).outcome is BeginOutcome.STARTED


async def test_client_factory_derives_cache_database(redis_url: str) -> None:
    clients = create_redis_clients(RedisSettings(redis_url=SecretStr(redis_url)))
    try:
        assert await clients.core.ping()
        assert await clients.cache.ping()
        assert clients.cache.connection_pool.connection_kwargs["db"] == 1
    finally:
        await clients.aclose()


async def test_slots_are_atomic_under_concurrency(redis: Redis) -> None:
    slots = RedisSlotLimiter(redis)

    results = await asyncio.gather(
        *(slots.acquire("slots", f"job-{n}", limit=3, ttl_seconds=60) for n in range(20))
    )

    assert sum(results) == 3
    assert await redis.zcard("slots") == 3


async def test_expired_slot_is_freed(redis: Redis) -> None:
    slots = RedisSlotLimiter(redis)
    await slots.acquire("slots", "crashed", limit=1, ttl_seconds=1)

    await asyncio.sleep(1.1)

    assert await slots.acquire("slots", "next", limit=1, ttl_seconds=60)
