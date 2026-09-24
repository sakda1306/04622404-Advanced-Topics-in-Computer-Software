"""Readiness (E-26) and the public service status (E-23).

Readiness fails only for dependencies every request needs: PostgreSQL and redis-core.
The Agent and redis-cache are reported but do not take the pod out of the load
balancer, because every replica shares them and removing all replicas helps nobody
(D-87). Recommendation calls already answer 503 while the Agent is down.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from app.core.clock import Clock
from app.core.config import ObservabilitySettings
from app.core.logging import get_logger
from app.domain.service_status import (
    CheckState,
    ComponentState,
    ServiceReport,
    StatusSummary,
    is_ready,
    summarize,
)

log = get_logger(__name__)

REQUIRED_CHECKS = frozenset({"database", "redis"})

Check = Callable[[], Awaitable[bool]]


class AgentStatusPort(Protocol):
    async def health(self) -> bool: ...

    async def breaker_state(self) -> str: ...


class ServiceStatusStorePort(Protocol):
    async def recent(self) -> dict[str, ServiceReport]: ...

    async def cached_summary(self) -> dict[str, Any] | None: ...

    async def store_summary(self, data: Mapping[str, Any], *, ttl_seconds: int) -> None: ...

    async def cached_agent_health(self) -> bool | None: ...

    async def store_agent_health(self, healthy: bool, *, ttl_seconds: int) -> None: ...


@dataclass(frozen=True, slots=True)
class Readiness:
    ready: bool
    checks: dict[str, str]


def _summary_to_dict(summary: StatusSummary) -> dict[str, Any]:
    return {
        "status": summary.status.value,
        "components": {name: state.value for name, state in summary.components.items()},
        "updated_at": summary.updated_at.isoformat(),
    }


def _summary_from_dict(data: Mapping[str, Any]) -> StatusSummary | None:
    try:
        return StatusSummary(
            status=ComponentState(data["status"]),
            components={k: ComponentState(v) for k, v in data["components"].items()},
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class OpsService:
    def __init__(
        self,
        *,
        checks: Mapping[str, Check],
        agent: AgentStatusPort | None,
        store: ServiceStatusStorePort | None,
        settings: ObservabilitySettings,
        clock: Clock,
    ) -> None:
        self._checks = checks
        self._agent = agent
        self._store = store
        self._settings = settings
        self._clock = clock

    @property
    def cache_seconds(self) -> int:
        return self._settings.service_status_cache_seconds

    async def _run_check(self, name: str, check: Check) -> CheckState:
        try:
            async with asyncio.timeout(self._settings.ready_timeout_seconds):
                return CheckState.OK if await check() else CheckState.UNAVAILABLE
        except Exception as exc:  # any failure means "not usable"; the type is logged
            log.warning("ready_check_failed", check=name, error_type=type(exc).__name__)
            return CheckState.UNAVAILABLE

    async def readiness(self) -> Readiness:
        names = list(self._checks)
        results = await asyncio.gather(
            *(self._run_check(name, self._checks[name]) for name in names)
        )
        checks: dict[str, CheckState] = dict(zip(names, results, strict=True))
        agent = await self.agent_state()
        if agent is not ComponentState.UNKNOWN:
            checks["agent"] = (
                CheckState.UNAVAILABLE if agent is ComponentState.UNAVAILABLE else CheckState.OK
            )
        return Readiness(
            ready=is_ready(checks, REQUIRED_CHECKS),
            checks={name: state.value for name, state in checks.items()},
        )

    async def agent_state(self) -> ComponentState:
        if self._agent is None:
            return ComponentState.UNKNOWN
        try:
            breaker = await self._agent.breaker_state()
        except Exception as exc:
            log.warning("agent_breaker_state_failed", error_type=type(exc).__name__)
            breaker = "closed"
        if breaker == "open":
            return ComponentState.UNAVAILABLE
        healthy = await self._agent_health()
        if not healthy:
            return ComponentState.UNAVAILABLE
        return ComponentState.DEGRADED if breaker == "half_open" else ComponentState.OK

    async def _agent_health(self) -> bool:
        assert self._agent is not None
        if self._store is not None:
            try:
                cached = await self._store.cached_agent_health()
            except Exception as exc:
                log.warning("status_cache_unavailable", error_type=type(exc).__name__)
                cached = None
            if cached is not None:
                return cached
        try:
            async with asyncio.timeout(self._settings.ready_timeout_seconds):
                healthy = await self._agent.health()
        except Exception as exc:
            log.warning("agent_health_failed", error_type=type(exc).__name__)
            healthy = False
        if self._store is not None:
            try:
                await self._store.store_agent_health(
                    healthy, ttl_seconds=self._settings.ready_agent_cache_seconds
                )
            except Exception as exc:
                log.warning("status_cache_unavailable", error_type=type(exc).__name__)
        return healthy

    async def service_status(self) -> StatusSummary:
        if self._store is not None:
            try:
                cached = await self._store.cached_summary()
            except Exception as exc:
                log.warning("status_cache_unavailable", error_type=type(exc).__name__)
                cached = None
            summary = _summary_from_dict(cached) if cached is not None else None
            if summary is not None:
                return summary

        reports: dict[str, ServiceReport] = {}
        if self._store is not None:
            try:
                reports = await self._store.recent()
            except Exception as exc:
                # No reports means every data service shows as unknown, never as ok.
                log.warning("status_cache_unavailable", error_type=type(exc).__name__)
        summary = summarize(
            reports,
            agent=await self.agent_state(),
            now=self._clock.now(),
            window=timedelta(minutes=self._settings.service_status_window_minutes),
        )
        if self._store is not None:
            try:
                await self._store.store_summary(
                    _summary_to_dict(summary),
                    ttl_seconds=self._settings.service_status_cache_seconds,
                )
            except Exception as exc:
                log.warning("status_cache_unavailable", error_type=type(exc).__name__)
        return summary
