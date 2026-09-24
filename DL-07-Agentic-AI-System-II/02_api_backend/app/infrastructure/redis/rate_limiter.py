"""Sliding-window rate limiter on a Redis sorted set (docs/02_api_spec.md section 13)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from redis.asyncio import Redis

# Atomic: trim the window, count, then admit or report when the oldest entry expires.
# Redis TIME is used so every API worker shares one clock.
_SLIDING_WINDOW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[3])
  redis.call('PEXPIRE', KEYS[1], window + 1000)
  return {1, count + 1, window}
end
local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local wait = window - (now - tonumber(oldest[2]))
if wait < 1 then wait = 1 end
return {0, count, wait}
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int

    def headers(self) -> dict[str, str]:
        return {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(self.remaining),
            "RateLimit-Reset": str(self.reset_seconds),
        }


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision: ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_SLIDING_WINDOW)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        allowed, count, wait_ms = await self._script(
            keys=[key], args=[window_seconds * 1000, limit, uuid4().hex]
        )
        return RateLimitDecision(
            allowed=bool(allowed),
            limit=limit,
            remaining=max(limit - int(count), 0),
            reset_seconds=max(math.ceil(int(wait_ms) / 1000), 1),
        )
