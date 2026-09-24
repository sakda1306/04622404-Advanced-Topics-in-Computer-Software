"""Idempotency-Key records (docs/02_api_spec.md section 11.1).

Each key is a Redis HASH. It is first locked ("in_progress") with a short TTL so a
crashed worker cannot block the key forever; the finished response then replaces the
lock and keeps the full TTL. All state changes run in Lua so they are atomic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from redis.asyncio import Redis

_BEGIN = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('HSET', KEYS[1], 'state', 'in_progress', 'owner', ARGV[1],
             'body_hash', ARGV[2], 'created_at', ARGV[4])
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
  return {'started'}
end
local rec = redis.call('HMGET', KEYS[1], 'state', 'body_hash', 'status_code', 'headers', 'body')
if rec[2] ~= ARGV[2] then return {'conflict'} end
if rec[1] == 'in_progress' then return {'in_progress'} end
return {'replay', rec[3], rec[4], rec[5]}
"""

_COMPLETE = """
if redis.call('HGET', KEYS[1], 'state') ~= 'in_progress'
   or redis.call('HGET', KEYS[1], 'owner') ~= ARGV[1] then
  return 0
end
redis.call('HSET', KEYS[1], 'state', 'completed', 'status_code', ARGV[2],
           'headers', ARGV[3], 'body', ARGV[4])
redis.call('HDEL', KEYS[1], 'owner')
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
return 1
"""

_RELEASE = """
if redis.call('HGET', KEYS[1], 'state') == 'in_progress'
   and redis.call('HGET', KEYS[1], 'owner') == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class BeginOutcome(StrEnum):
    STARTED = "started"
    REPLAY = "replay"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class BeginResult:
    outcome: BeginOutcome
    owner: str = ""
    response: StoredResponse | None = None


class IdempotencyStore(Protocol):
    async def begin(self, key: str, body_hash: str, *, lock_seconds: int) -> BeginResult: ...

    async def complete(
        self, key: str, owner: str, response: StoredResponse, *, ttl_seconds: int
    ) -> bool: ...

    async def release(self, key: str, owner: str) -> None: ...


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class RedisIdempotencyStore:
    def __init__(self, redis: Redis) -> None:
        self._begin = redis.register_script(_BEGIN)
        self._complete = redis.register_script(_COMPLETE)
        self._release = redis.register_script(_RELEASE)

    async def begin(self, key: str, body_hash: str, *, lock_seconds: int) -> BeginResult:
        owner = uuid4().hex
        result = await self._begin(
            keys=[key], args=[owner, body_hash, lock_seconds, f"{time.time():.3f}"]
        )
        outcome = BeginOutcome(_text(result[0]))
        if outcome is BeginOutcome.STARTED:
            return BeginResult(outcome, owner=owner)
        if outcome is not BeginOutcome.REPLAY:
            return BeginResult(outcome)
        status_code, headers, body = result[1], result[2], result[3]
        return BeginResult(
            outcome,
            response=StoredResponse(
                status_code=int(_text(status_code)),
                headers=json.loads(_text(headers)),
                body=body if isinstance(body, bytes) else body.encode(),
            ),
        )

    async def complete(
        self, key: str, owner: str, response: StoredResponse, *, ttl_seconds: int
    ) -> bool:
        stored = await self._complete(
            keys=[key],
            args=[
                owner,
                response.status_code,
                json.dumps(response.headers),
                response.body,
                ttl_seconds,
            ],
        )
        return bool(stored)

    async def release(self, key: str, owner: str) -> None:
        await self._release(keys=[key], args=[owner])
