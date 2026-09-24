"""Remove a user's live data from Redis when the account is deleted (D-78).

Stored idempotent responses can contain the user's requests, so they go too. Rate-limit
counters hold only timestamps and expire on their own.
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

from app.infrastructure.redis.keys import RedisKeys

_BATCH = 100


class RedisUserData:
    def __init__(self, redis: Redis, keys: RedisKeys) -> None:
        self._redis = redis
        self._keys = keys

    async def forget(self, user_id: UUID, *, principal_hash: str, job_ids: list[UUID]) -> int:
        keys: list[bytes | str] = [self._keys.active_jobs(user_id), self._keys.streams(user_id)]
        for job_id in job_ids:
            keys += [self._keys.job(job_id), self._keys.job_events(job_id)]
        # Collect first: deleting while the SCAN cursor moves can skip keys.
        async for key in self._redis.scan_iter(
            match=self._keys.idempotency_pattern(principal_hash), count=_BATCH
        ):
            keys.append(key)
        removed = 0
        for start in range(0, len(keys), _BATCH):
            removed += int(await self._redis.delete(*keys[start : start + _BATCH]))
        return removed
