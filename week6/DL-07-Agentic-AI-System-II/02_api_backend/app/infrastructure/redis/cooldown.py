"""Time-limited claims in Redis: one data export per P-63, one purge run at a time."""

from __future__ import annotations

from redis.asyncio import Redis

from app.infrastructure.redis.keys import RedisKeys


class RedisCooldown:
    def __init__(self, redis: Redis, keys: RedisKeys) -> None:
        self._redis = redis
        self._keys = keys

    async def claim(self, key: str, *, seconds: int) -> int | None:
        name = self._keys.cooldown(key)
        if await self._redis.set(name, "1", nx=True, ex=seconds):
            return None
        remaining = int(await self._redis.ttl(name))
        return max(remaining, 1)

    async def release(self, key: str) -> None:
        await self._redis.delete(self._keys.cooldown(key))
