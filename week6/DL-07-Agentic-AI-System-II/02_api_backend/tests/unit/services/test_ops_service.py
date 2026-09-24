from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis

from app.core.config import ObservabilitySettings
from app.domain.enums import ServiceState
from app.domain.service_status import DATA_SERVICES, ComponentState, ServiceReport
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.service_status import RedisServiceStatusStore
from app.services.ops_service import OpsService
from tests.support.clock import FakeClock


@dataclass
class FakeAgent:
    healthy: bool = True
    breaker: str = "closed"
    probes: int = 0
    slow: bool = False

    async def health(self) -> bool:
        self.probes += 1
        if self.slow:
            await asyncio.sleep(1)
        return self.healthy

    async def breaker_state(self) -> str:
        return self.breaker


class BrokenStore:
    """Every call fails, like redis-cache being down."""

    async def recent(self) -> dict[str, ServiceReport]:
        raise ConnectionError("down")

    async def cached_summary(self) -> dict[str, Any] | None:
        raise ConnectionError("down")

    async def store_summary(self, data: Mapping[str, Any], *, ttl_seconds: int) -> None:
        raise ConnectionError("down")

    async def cached_agent_health(self) -> bool | None:
        raise ConnectionError("down")

    async def store_agent_health(self, healthy: bool, *, ttl_seconds: int) -> None:
        raise ConnectionError("down")


async def ok() -> bool:
    return True


async def boom() -> bool:
    raise OSError("connection refused host=db.internal")


async def hang() -> bool:
    await asyncio.sleep(5)
    return True


@pytest.fixture
def obs() -> ObservabilitySettings:
    return ObservabilitySettings(ready_timeout_seconds=0.05)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(redis: FakeAsyncRedis) -> RedisServiceStatusStore:
    return RedisServiceStatusStore(redis, RedisKeys("test"))


def service(
    obs: ObservabilitySettings,
    clock: FakeClock,
    *,
    checks: Mapping[str, Any] | None = None,
    agent: FakeAgent | None = None,
    store: Any = None,
) -> OpsService:
    return OpsService(
        checks=checks if checks is not None else {"database": ok, "redis": ok},
        agent=agent,
        store=store,
        settings=obs,
        clock=clock,
    )


async def test_ready_when_database_and_redis_answer(
    obs: ObservabilitySettings, clock: FakeClock
) -> None:
    result = await service(obs, clock, agent=FakeAgent()).readiness()

    assert result.ready
    assert result.checks == {"database": "ok", "redis": "ok", "agent": "ok"}


@pytest.mark.parametrize("failing", [boom, hang])
async def test_not_ready_when_a_required_check_fails(
    obs: ObservabilitySettings, clock: FakeClock, failing: Any
) -> None:
    ops = service(obs, clock, checks={"database": failing, "redis": ok})

    result = await ops.readiness()

    assert not result.ready
    assert result.checks["database"] == "unavailable"


async def test_agent_and_cache_do_not_block_readiness(
    obs: ObservabilitySettings, clock: FakeClock
) -> None:
    ops = service(
        obs,
        clock,
        checks={"database": ok, "redis": ok, "redis_cache": boom},
        agent=FakeAgent(healthy=False),
    )

    result = await ops.readiness()

    assert result.ready
    assert result.checks["agent"] == "unavailable"
    assert result.checks["redis_cache"] == "unavailable"


async def test_no_agent_configured_is_not_reported_as_ok(
    obs: ObservabilitySettings, clock: FakeClock
) -> None:
    result = await service(obs, clock).readiness()

    assert "agent" not in result.checks


@pytest.mark.parametrize(
    ("breaker", "healthy", "expected"),
    [
        ("closed", True, ComponentState.OK),
        ("half_open", True, ComponentState.DEGRADED),
        ("open", True, ComponentState.UNAVAILABLE),
        ("closed", False, ComponentState.UNAVAILABLE),
    ],
)
async def test_agent_state(
    obs: ObservabilitySettings,
    clock: FakeClock,
    breaker: str,
    healthy: bool,
    expected: ComponentState,
) -> None:
    agent = FakeAgent(healthy=healthy, breaker=breaker)

    assert await service(obs, clock, agent=agent).agent_state() is expected


async def test_slow_agent_probe_counts_as_unavailable(
    obs: ObservabilitySettings, clock: FakeClock
) -> None:
    agent = FakeAgent(slow=True)

    assert await service(obs, clock, agent=agent).agent_state() is ComponentState.UNAVAILABLE


async def test_agent_probe_is_cached(
    obs: ObservabilitySettings, clock: FakeClock, store: RedisServiceStatusStore
) -> None:
    agent = FakeAgent()
    ops = service(obs, clock, agent=agent, store=store)

    await ops.agent_state()
    await ops.agent_state()

    assert agent.probes == 1


async def test_service_status_uses_recent_reports_and_caches_the_summary(
    obs: ObservabilitySettings,
    clock: FakeClock,
    store: RedisServiceStatusStore,
    redis: FakeAsyncRedis,
) -> None:
    await store.record(
        dict.fromkeys(DATA_SERVICES, ServiceState.OK), at=clock.now(), ttl_seconds=900
    )
    ops = service(obs, clock, agent=FakeAgent(), store=store)

    first = await ops.service_status()
    await store.record({"weather": ServiceState.UNAVAILABLE}, at=clock.now(), ttl_seconds=900)
    second = await ops.service_status()
    await redis.delete(RedisKeys("test").service_status())  # the 30 s cache expired
    third = await ops.service_status()

    assert first.status is ComponentState.OK
    assert second == first
    assert third.components["weather"] is ComponentState.UNAVAILABLE
    assert third.status is ComponentState.DEGRADED


async def test_service_status_without_redis_cache_is_honest(
    obs: ObservabilitySettings, clock: FakeClock
) -> None:
    ops = service(obs, clock, agent=FakeAgent(), store=BrokenStore())

    summary = await ops.service_status()

    assert summary.status is ComponentState.UNKNOWN
    assert summary.components["weather"] is ComponentState.UNKNOWN
    assert summary.components["agent"] is ComponentState.OK


async def test_reports_older_than_the_window_are_unknown(
    obs: ObservabilitySettings, clock: FakeClock, store: RedisServiceStatusStore
) -> None:
    await store.record(
        dict.fromkeys(DATA_SERVICES, ServiceState.OK), at=clock.now(), ttl_seconds=3600
    )
    clock.advance(int(timedelta(minutes=16).total_seconds()))

    summary = await service(obs, clock, agent=FakeAgent(), store=store).service_status()

    assert summary.components["disaster"] is ComponentState.UNKNOWN
