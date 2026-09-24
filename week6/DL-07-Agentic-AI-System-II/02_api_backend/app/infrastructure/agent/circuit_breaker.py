"""Circuit breaker for the Agent, shared by all API and worker processes (P-08).

closed    -> calls pass; failures inside the window are counted
open      -> calls are rejected until `reset_seconds` have passed
half_open -> one probe call is let through; success closes, failure re-opens

State lives in Redis (docs/03_data_design.md section 5.2, key `cb:agent`). If Redis is
unavailable the breaker allows calls: it protects the Agent, it must not become an
outage of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.clock import Clock, SystemClock
from app.core.logging import get_logger

log = get_logger(__name__)

# KEYS: state hash, failures zset. ARGV: now_ms, reset_ms
_ACQUIRE = """
local state = redis.call('HGET', KEYS[1], 'state')
local now = tonumber(ARGV[1])
local reset = tonumber(ARGV[2])
if not state or state == 'closed' then return {'allow', 0} end
if state == 'open' then
  local opened = tonumber(redis.call('HGET', KEYS[1], 'opened_at'))
  if now < opened + reset then return {'reject', opened + reset - now} end
end
if state == 'half_open' then
  local probe_until = tonumber(redis.call('HGET', KEYS[1], 'probe_until'))
  if now < probe_until then return {'reject', probe_until - now} end
end
redis.call('HSET', KEYS[1], 'state', 'half_open', 'probe_until', now + reset)
return {'probe', 0}
"""

# ARGV: now_ms, window_ms, threshold, member
_FAILURE = """
local now = tonumber(ARGV[1])
local state = redis.call('HGET', KEYS[1], 'state')
-- Late failures from calls that started before the circuit opened must not extend it.
if state == 'open' then return 'open' end
if state == 'half_open' then
  redis.call('HSET', KEYS[1], 'state', 'open', 'opened_at', now)
  return 'open'
end
redis.call('ZADD', KEYS[2], now, ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now - tonumber(ARGV[2]))
redis.call('PEXPIRE', KEYS[2], tonumber(ARGV[2]) + 1000)
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[3]) then
  redis.call('HSET', KEYS[1], 'state', 'open', 'opened_at', now)
  redis.call('DEL', KEYS[2])
  return 'open'
end
return 'closed'
"""

_SUCCESS = """
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'half_open' or state == 'open' then
  redis.call('DEL', KEYS[1], KEYS[2])
end
return 1
"""


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Permit(StrEnum):
    ALLOW = "allow"
    PROBE = "probe"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class Admission:
    permit: Permit
    retry_after_seconds: int = 0

    @property
    def allowed(self) -> bool:
        return self.permit is not Permit.REJECT


class CircuitBreaker(Protocol):
    async def acquire(self) -> Admission: ...

    async def record_success(self) -> None: ...

    async def record_failure(self) -> None: ...

    async def state(self) -> BreakerState: ...


class RedisCircuitBreaker:
    def __init__(
        self,
        redis: Redis,
        *,
        name: str,
        failure_threshold: int,
        window_seconds: int,
        reset_seconds: int,
        clock: Clock | None = None,
    ) -> None:
        self._redis = redis
        self._keys = [name, f"{name}:failures"]
        self._threshold = failure_threshold
        self._window_ms = window_seconds * 1000
        self._reset_ms = reset_seconds * 1000
        self._clock = clock or SystemClock()
        self._acquire = redis.register_script(_ACQUIRE)
        self._failure = redis.register_script(_FAILURE)
        self._success = redis.register_script(_SUCCESS)
        self._counter = 0

    def _now_ms(self) -> int:
        return int(self._clock.now().timestamp() * 1000)

    async def acquire(self) -> Admission:
        try:
            permit, wait_ms = await self._acquire(
                keys=self._keys, args=[self._now_ms(), self._reset_ms]
            )
        except (RedisError, OSError) as exc:
            log.warning("circuit_breaker_unavailable", error_type=type(exc).__name__)
            return Admission(Permit.ALLOW)
        permit = Permit(permit.decode() if isinstance(permit, bytes) else permit)
        return Admission(permit, retry_after_seconds=max(-(-int(wait_ms) // 1000), 0))

    async def state(self) -> BreakerState:
        """Read-only view for /ready and E-23; an open circuit past its reset is half open."""
        try:
            raw: list[Any] = await self._redis.hmget(  # type: ignore[misc]
                self._keys[0], ["state", "opened_at"]
            )
        except (RedisError, OSError) as exc:
            log.warning("circuit_breaker_unavailable", error_type=type(exc).__name__)
            return BreakerState.CLOSED
        state, opened_at = (v.decode() if isinstance(v, bytes) else v for v in raw)
        if state == BreakerState.OPEN:
            if opened_at is not None and self._now_ms() >= int(opened_at) + self._reset_ms:
                return BreakerState.HALF_OPEN
            return BreakerState.OPEN
        if state == BreakerState.HALF_OPEN:
            return BreakerState.HALF_OPEN
        return BreakerState.CLOSED

    async def record_success(self) -> None:
        try:
            await self._success(keys=self._keys)
        except (RedisError, OSError) as exc:
            log.warning("circuit_breaker_unavailable", error_type=type(exc).__name__)

    async def record_failure(self) -> None:
        self._counter += 1
        member = f"{self._now_ms()}-{id(self)}-{self._counter}"
        try:
            state = await self._failure(
                keys=self._keys,
                args=[self._now_ms(), self._window_ms, self._threshold, member],
            )
        except (RedisError, OSError) as exc:
            log.warning("circuit_breaker_unavailable", error_type=type(exc).__name__)
            return
        if (state.decode() if isinstance(state, bytes) else state) == "open":
            log.warning("circuit_opened", breaker=self._keys[0])
