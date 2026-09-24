"""Removing a user's live data from Redis (D-78), against fakeredis."""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from app.core.ids import new_id
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.user_data import RedisUserData

KEYS = RedisKeys("test")


async def test_forget_removes_only_the_users_keys(redis: FakeAsyncRedis) -> None:
    user, other = new_id(), new_id()
    job, other_job = new_id(), new_id()
    mine = [
        KEYS.active_jobs(user),
        KEYS.streams(user),
        KEYS.job(job),
        KEYS.job_events(job),
        KEYS.idempotency("hash-user", "POST", "/v1/x", "key-1"),
        *[KEYS.idempotency("hash-user", "POST", "/v1/y", f"key-{n}") for n in range(250)],
    ]
    theirs = [
        KEYS.active_jobs(other),
        KEYS.job(other_job),
        KEYS.idempotency("hash-other", "POST", "/v1/x", "key-1"),
    ]
    for key in mine + theirs:
        await redis.set(key, "1")

    removed = await RedisUserData(redis, KEYS).forget(
        user, principal_hash="hash-user", job_ids=[job]
    )

    assert removed == len(mine)
    for key in mine:
        assert not await redis.exists(key)
    for key in theirs:
        assert await redis.exists(key)
