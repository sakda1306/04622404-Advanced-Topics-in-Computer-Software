"""Rate limiter and idempotency store against fakeredis (same Lua as production)."""

from __future__ import annotations

import asyncio

from fakeredis import FakeAsyncRedis

from app.infrastructure.redis.idempotency_store import (
    BeginOutcome,
    RedisIdempotencyStore,
    StoredResponse,
)
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.rate_limiter import RedisRateLimiter

# ------------------------------------------------------------------ keys


def test_keys_are_prefixed_and_hash_user_input() -> None:
    keys = RedisKeys("test")

    rl = keys.rate_limit("user", "abc")
    idem = keys.idempotency("abc", "post", "/v1/items", "my-secret-key")

    assert rl == "tsa:test:rl:user:abc"
    assert idem.startswith("tsa:test:idem:abc:POST:")
    assert "my-secret-key" not in idem
    assert "/v1/items" not in idem


# ------------------------------------------------------------------ rate limiter


async def test_allows_up_to_the_limit_then_blocks(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis)

    decisions = [await limiter.hit("k", limit=3, window_seconds=60) for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert [d.remaining for d in decisions] == [2, 1, 0, 0]
    assert 1 <= decisions[-1].reset_seconds <= 60
    assert decisions[-1].headers() == {
        "RateLimit-Limit": "3",
        "RateLimit-Remaining": "0",
        "RateLimit-Reset": str(decisions[-1].reset_seconds),
    }


async def test_keys_are_counted_separately(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.hit("a", limit=1, window_seconds=60)

    assert (await limiter.hit("b", limit=1, window_seconds=60)).allowed


async def test_window_slides(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.hit("k", limit=1, window_seconds=1)
    assert not (await limiter.hit("k", limit=1, window_seconds=1)).allowed

    await asyncio.sleep(1.1)

    assert (await limiter.hit("k", limit=1, window_seconds=1)).allowed


async def test_rate_limit_key_expires(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.hit("k", limit=5, window_seconds=60)

    ttl = await redis.pttl("k")
    assert 60_000 < ttl <= 61_000


async def test_blocked_hits_do_not_extend_the_window(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.hit("k", limit=1, window_seconds=60)
    for _ in range(5):
        await limiter.hit("k", limit=1, window_seconds=60)

    assert await redis.zcard("k") == 1


# ------------------------------------------------------------------ idempotency


RESPONSE = StoredResponse(201, {"content-type": "application/json"}, b'{"id":"1","n":"\xc3\xa9"}')


async def test_first_request_starts_and_locks(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)

    first = await store.begin("k", "hash-1", lock_seconds=120)
    second = await store.begin("k", "hash-1", lock_seconds=120)

    assert first.outcome is BeginOutcome.STARTED
    assert first.owner
    assert second.outcome is BeginOutcome.IN_PROGRESS
    assert 0 < await redis.ttl("k") <= 120


async def test_different_body_is_a_conflict(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    await store.begin("k", "hash-1", lock_seconds=120)

    assert (await store.begin("k", "hash-2", lock_seconds=120)).outcome is BeginOutcome.CONFLICT


async def test_completed_response_is_replayed(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    started = await store.begin("k", "hash-1", lock_seconds=120)

    assert await store.complete("k", started.owner, RESPONSE, ttl_seconds=86400)
    replay = await store.begin("k", "hash-1", lock_seconds=120)

    assert replay.outcome is BeginOutcome.REPLAY
    assert replay.response == RESPONSE
    assert 86000 < await redis.ttl("k") <= 86400
    assert (await store.begin("k", "hash-2", lock_seconds=120)).outcome is BeginOutcome.CONFLICT


async def test_release_lets_the_client_retry(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    started = await store.begin("k", "hash-1", lock_seconds=120)

    await store.release("k", started.owner)

    assert (await store.begin("k", "hash-2", lock_seconds=120)).outcome is BeginOutcome.STARTED


async def test_only_the_owner_can_release_or_complete(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    await store.begin("k", "hash-1", lock_seconds=120)

    await store.release("k", "someone-else")
    completed = await store.complete("k", "someone-else", RESPONSE, ttl_seconds=60)

    assert not completed
    assert (await store.begin("k", "hash-1", lock_seconds=120)).outcome is BeginOutcome.IN_PROGRESS


async def test_completed_record_cannot_be_released(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    started = await store.begin("k", "hash-1", lock_seconds=120)
    await store.complete("k", started.owner, RESPONSE, ttl_seconds=60)

    await store.release("k", started.owner)

    assert (await store.begin("k", "hash-1", lock_seconds=120)).outcome is BeginOutcome.REPLAY


async def test_complete_after_lock_expired_is_ignored(redis: FakeAsyncRedis) -> None:
    store = RedisIdempotencyStore(redis)
    started = await store.begin("k", "hash-1", lock_seconds=120)
    await redis.delete("k")

    assert not await store.complete("k", started.owner, RESPONSE, ttl_seconds=60)
    assert not await redis.exists("k")
