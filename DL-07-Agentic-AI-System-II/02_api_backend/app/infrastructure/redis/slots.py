"""Limit concurrent things per user: active jobs (P-33) and open streams (P-34).

A ZSET per user holds one member per job or connection with its expiry time as the
score, so a crashed worker or a dropped connection frees its slot on its own (D-39).
Redis TIME is the clock, shared by every process.
"""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

# KEYS: zset. ARGV: member, limit, ttl_ms, mode ('acquire' | 'refresh')
_SLOT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local ttl = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local present = redis.call('ZSCORE', KEYS[1], ARGV[1])
if ARGV[4] == 'refresh' and not present then return 0 end
if ARGV[4] == 'acquire' and not present
   and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  return 0
end
redis.call('ZADD', KEYS[1], now + ttl, ARGV[1])
if redis.call('PTTL', KEYS[1]) < ttl then redis.call('PEXPIRE', KEYS[1], ttl) end
return 1
"""


class SlotLimiter(Protocol):
    async def acquire(self, key: str, member: str, *, limit: int, ttl_seconds: int) -> bool: ...

    async def refresh(self, key: str, member: str, *, ttl_seconds: int) -> None: ...

    async def release(self, key: str, member: str) -> None: ...


class RedisSlotLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_SLOT)

    async def acquire(self, key: str, member: str, *, limit: int, ttl_seconds: int) -> bool:
        allowed = await self._script(
            keys=[key], args=[member, limit, ttl_seconds * 1000, "acquire"]
        )
        return bool(allowed)

    async def refresh(self, key: str, member: str, *, ttl_seconds: int) -> None:
        await self._script(keys=[key], args=[member, 0, ttl_seconds * 1000, "refresh"])

    async def release(self, key: str, member: str) -> None:
        await self._redis.zrem(key, member)
