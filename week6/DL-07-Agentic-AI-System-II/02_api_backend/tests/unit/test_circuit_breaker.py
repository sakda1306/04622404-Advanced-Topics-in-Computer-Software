from __future__ import annotations

from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.infrastructure.agent.circuit_breaker import BreakerState, Permit, RedisCircuitBreaker
from tests.support.clock import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def breaker(redis: FakeAsyncRedis, clock: FakeClock) -> RedisCircuitBreaker:
    return RedisCircuitBreaker(
        redis,
        name="tsa:test:cb:agent",
        failure_threshold=3,
        window_seconds=30,
        reset_seconds=30,
        clock=clock,
    )


async def _fail(breaker: RedisCircuitBreaker, times: int) -> None:
    for _ in range(times):
        await breaker.record_failure()


async def test_closed_breaker_allows_calls(breaker: RedisCircuitBreaker) -> None:
    admission = await breaker.acquire()

    assert admission.permit is Permit.ALLOW
    assert admission.allowed


async def test_opens_after_threshold_failures_in_window(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 2)
    assert (await breaker.acquire()).allowed

    await _fail(breaker, 1)
    admission = await breaker.acquire()

    assert admission.permit is Permit.REJECT
    assert admission.retry_after_seconds == 30
    clock.advance(10)
    assert (await breaker.acquire()).retry_after_seconds == 20


async def test_old_failures_leave_the_window(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 2)
    clock.advance(31)
    await _fail(breaker, 2)

    assert (await breaker.acquire()).allowed


async def test_half_open_allows_a_single_probe(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 3)
    clock.advance(30)

    first = await breaker.acquire()
    second = await breaker.acquire()

    assert first.permit is Permit.PROBE
    assert second.permit is Permit.REJECT


async def test_successful_probe_closes_the_circuit(
    breaker: RedisCircuitBreaker, clock: FakeClock, redis: FakeAsyncRedis
) -> None:
    await _fail(breaker, 3)
    clock.advance(30)
    await breaker.acquire()

    await breaker.record_success()

    assert (await breaker.acquire()).permit is Permit.ALLOW
    assert await redis.exists("tsa:test:cb:agent") == 0
    # The failure count starts again from zero.
    await _fail(breaker, 2)
    assert (await breaker.acquire()).allowed


async def test_failed_probe_reopens_for_a_full_period(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 3)
    clock.advance(30)
    await breaker.acquire()

    await breaker.record_failure()

    admission = await breaker.acquire()
    assert admission.permit is Permit.REJECT
    assert admission.retry_after_seconds == 30


async def test_lost_probe_is_retried_after_the_reset_period(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 3)
    clock.advance(30)
    await breaker.acquire()  # the probe never reports back

    clock.advance(30)

    assert (await breaker.acquire()).permit is Permit.PROBE


async def test_late_failures_do_not_extend_an_open_circuit(
    breaker: RedisCircuitBreaker, clock: FakeClock
) -> None:
    await _fail(breaker, 3)
    clock.advance(20)
    await _fail(breaker, 5)
    clock.advance(10)

    assert (await breaker.acquire()).permit is Permit.PROBE


async def test_success_while_closed_keeps_failure_history(
    breaker: RedisCircuitBreaker,
) -> None:
    await _fail(breaker, 2)
    await breaker.record_success()
    await _fail(breaker, 1)

    assert not (await breaker.acquire()).allowed


class _DownRedis:
    def register_script(self, script: str) -> Any:
        async def call(*args: Any, **kwargs: Any) -> Any:
            raise RedisConnectionError("down")

        return call


async def test_redis_outage_allows_calls(clock: FakeClock) -> None:
    breaker = RedisCircuitBreaker(
        _DownRedis(),  # type: ignore[arg-type]
        name="cb",
        failure_threshold=1,
        window_seconds=1,
        reset_seconds=1,
        clock=clock,
    )

    await breaker.record_failure()
    await breaker.record_success()

    assert (await breaker.acquire()).allowed


async def test_state_follows_the_breaker(breaker: RedisCircuitBreaker, clock: FakeClock) -> None:
    assert await breaker.state() is BreakerState.CLOSED

    await _fail(breaker, 3)
    assert await breaker.state() is BreakerState.OPEN

    clock.advance(30)
    assert await breaker.state() is BreakerState.HALF_OPEN  # a probe would be let through

    await breaker.acquire()
    await breaker.record_success()
    assert await breaker.state() is BreakerState.CLOSED


async def test_state_reads_closed_when_redis_is_down(clock: FakeClock) -> None:
    class Down(FakeAsyncRedis):
        async def hmget(self, *args: Any, **kwargs: Any) -> Any:
            raise RedisConnectionError("down")

    breaker = RedisCircuitBreaker(
        Down(),
        name="tsa:test:cb:agent",
        failure_threshold=3,
        window_seconds=30,
        reset_seconds=30,
        clock=clock,
    )

    assert await breaker.state() is BreakerState.CLOSED
