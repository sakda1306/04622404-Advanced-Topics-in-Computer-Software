"""Service status data on redis-cache (docs/03_data_design.md section 5.2).

- `status:reports`  HASH  service -> "state|reported_at_ms", written by workers
- `status:service`  STRING  the computed E-23 summary (P-65)
- `ready:agent`     STRING  the last Agent health probe (P-66)

Everything here may disappear at any time (allkeys-lru); readers treat a missing key
as "no information", never as "working".
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.domain.enums import ServiceState
from app.domain.service_status import DATA_SERVICES, ServiceReport
from app.infrastructure.redis.keys import RedisKeys


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class RedisServiceStatusStore:
    def __init__(self, redis: Redis, keys: RedisKeys) -> None:
        self._redis = redis
        self._keys = keys

    async def record(
        self, states: Mapping[str, ServiceState], *, at: datetime, ttl_seconds: int
    ) -> None:
        # `not_used` would hide the last real state of a service this run did not need.
        fields = {
            name: f"{state.value}|{int(at.timestamp() * 1000)}"
            for name, state in states.items()
            if name in DATA_SERVICES and state is not ServiceState.NOT_USED
        }
        if not fields:
            return
        key = self._keys.service_reports()
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.hset(key, mapping=fields)
            pipe.expire(key, ttl_seconds)
            await pipe.execute()

    async def recent(self) -> dict[str, ServiceReport]:
        raw: dict[Any, Any] = await self._redis.hgetall(  # type: ignore[misc]
            self._keys.service_reports()
        )
        reports: dict[str, ServiceReport] = {}
        for name, value in raw.items():
            try:
                state, millis = _text(value).split("|", 1)
                reports[_text(name)] = ServiceReport(
                    ServiceState(state), datetime.fromtimestamp(int(millis) / 1000, UTC)
                )
            except ValueError:
                continue  # a malformed entry is simply not a report
        return reports

    async def cached_summary(self) -> dict[str, Any] | None:
        raw = await self._redis.get(self._keys.service_status())
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def store_summary(self, data: Mapping[str, Any], *, ttl_seconds: int) -> None:
        await self._redis.set(self._keys.service_status(), json.dumps(data), ex=ttl_seconds)

    async def cached_agent_health(self) -> bool | None:
        raw = await self._redis.get(self._keys.ready_agent())
        return None if raw is None else _text(raw) == "ok"

    async def store_agent_health(self, healthy: bool, *, ttl_seconds: int) -> None:
        await self._redis.set(
            self._keys.ready_agent(), "ok" if healthy else "unavailable", ex=ttl_seconds
        )
