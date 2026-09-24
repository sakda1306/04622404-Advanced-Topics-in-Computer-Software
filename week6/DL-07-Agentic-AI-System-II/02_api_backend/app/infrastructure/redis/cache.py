"""Shared recommendation cache on redis-cache (docs/02_api_spec.md section 11.2).

The cache is an optimisation: an outage or a bad entry is a miss, never an error.
Entries hold only the payload without personal identifiers.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.infrastructure.redis.keys import RedisKeys

log = get_logger(__name__)


class RedisRecommendationCache:
    def __init__(self, redis: Redis, keys: RedisKeys) -> None:
        self._redis = redis
        self._keys = keys

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        try:
            raw = await self._redis.get(self._keys.recommendation_cache(cache_key))
        except (RedisError, OSError) as exc:
            log.warning("cache_unavailable", error_type=type(exc).__name__)
            return None
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            log.warning("cache_entry_invalid")
            return None
        return value if isinstance(value, dict) else None

    async def put(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            await self._redis.set(
                self._keys.recommendation_cache(cache_key),
                json.dumps(payload, ensure_ascii=False),
                ex=ttl_seconds,
            )
        except (RedisError, OSError) as exc:
            log.warning("cache_unavailable", error_type=type(exc).__name__)
