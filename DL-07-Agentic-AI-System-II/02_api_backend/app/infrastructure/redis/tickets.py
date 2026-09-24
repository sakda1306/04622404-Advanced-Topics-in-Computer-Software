"""Short-lived, single-use tickets for SSE clients that cannot send headers (D-06)."""

from __future__ import annotations

import json
import secrets
from uuid import UUID

from redis.asyncio import Redis

from app.infrastructure.redis.keys import RedisKeys


class RedisTicketStore:
    def __init__(self, redis: Redis, keys: RedisKeys) -> None:
        self._redis = redis
        self._keys = keys

    async def issue(self, user_id: UUID, job_id: UUID, *, ttl_seconds: int) -> str:
        ticket = secrets.token_urlsafe(32)
        value = json.dumps({"user_id": str(user_id), "job_id": str(job_id)})
        await self._redis.set(self._keys.stream_ticket(ticket), value, ex=ttl_seconds)
        return ticket

    async def redeem(self, ticket: str) -> tuple[UUID, UUID] | None:
        raw = await self._redis.getdel(self._keys.stream_ticket(ticket))
        if raw is None:
            return None
        data = json.loads(raw)
        return UUID(data["user_id"]), UUID(data["job_id"])
