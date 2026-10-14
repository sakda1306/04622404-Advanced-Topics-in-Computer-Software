"""Small key-value store for rate limits, short caches and in-flight markers.

Redis in docker compose, an in-process dict when REDIS_URL is empty (tests / one
worker). Redis errors never fail a request: limits fail open and caches miss. After an
error Redis is left alone for a few seconds, so a request does not wait on every call.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

log = get_logger(__name__)


class Store(Protocol):
    @property
    def available(self) -> bool:
        """False while the backing store is known to be down (reads then always miss)."""
        ...

    async def get_json(self, key: str) -> Any | None: ...

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Count one hit in a fixed window; returns (count, seconds until reset)."""
        ...

    async def close(self) -> None: ...


class MemoryStore:
    available = True

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}

    def _alive(self, key: str) -> tuple[float, Any] | None:
        entry = self._data.get(key)
        if entry and entry[0] <= time.monotonic():
            del self._data[key]
            return None
        return entry

    async def get_json(self, key: str) -> Any | None:
        entry = self._alive(key)
        return entry[1] if entry else None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, value)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        entry = self._alive(key)
        now = time.monotonic()
        if entry is None:
            entry = (now + window_seconds, 0)
        expires, count = entry
        self._data[key] = (expires, count + 1)
        return count + 1, max(int(expires - now + 0.999), 1)

    async def close(self) -> None:
        self._data.clear()


class RedisStore:
    def __init__(
        self,
        redis: Redis,
        *,
        down_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._redis = redis
        self._down_seconds = down_seconds
        self._clock = clock
        self._down_until = 0.0

    @property
    def available(self) -> bool:
        return self._clock() >= self._down_until

    def _failed(self, exc: Exception) -> None:
        log.warning("store_unavailable", error_type=type(exc).__name__)
        self._down_until = self._clock() + self._down_seconds

    async def get_json(self, key: str) -> Any | None:
        if not self.available:
            return None
        try:
            raw = await self._redis.get(key)
        except (RedisError, OSError) as exc:
            self._failed(exc)
            return None
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if not self.available:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl_seconds)
        except (RedisError, OSError) as exc:
            self._failed(exc)

    async def delete(self, key: str) -> None:
        if not self.available:
            return
        try:
            await self._redis.delete(key)
        except (RedisError, OSError) as exc:
            self._failed(exc)

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        if not self.available:
            return 0, 0
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, window_seconds, nx=True)
                pipe.ttl(key)
                count, _, ttl = await pipe.execute()
        except (RedisError, OSError) as exc:
            self._failed(exc)
            return 0, 0
        return int(count), max(int(ttl), 1)

    async def close(self) -> None:
        await self._redis.aclose()


def create_store(redis_url: str) -> Store:
    if not redis_url:
        return MemoryStore()
    return RedisStore(Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2))
