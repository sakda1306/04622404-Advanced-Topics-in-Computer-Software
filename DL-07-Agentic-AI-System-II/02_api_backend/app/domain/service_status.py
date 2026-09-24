"""Public service status (E-23) and readiness rules. Pure functions, no I/O.

The backend never calls weather or disaster providers (D-03), so the state of those
services comes from what the Agent reported in its recent answers. A component with no
recent report is `unknown`: the page must not claim that a service works when nobody
has seen it work (D-88).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.enums import ServiceState

# Services the Agent reports, in display order (the same set as D-47).
DATA_SERVICES = ("weather", "transport", "disaster", "risk_model", "rag", "llm")


class ComponentState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class CheckState(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ServiceReport:
    """The latest state the Agent reported for one service."""

    state: ServiceState
    reported_at: datetime


@dataclass(frozen=True, slots=True)
class StatusSummary:
    status: ComponentState
    components: dict[str, ComponentState]
    updated_at: datetime


_FROM_REPORT = {
    ServiceState.OK: ComponentState.OK,
    ServiceState.DEGRADED: ComponentState.DEGRADED,
    ServiceState.UNAVAILABLE: ComponentState.UNAVAILABLE,
}
_TROUBLED = frozenset({ComponentState.DEGRADED, ComponentState.UNAVAILABLE})


def _component(report: ServiceReport | None, *, now: datetime, window: timedelta) -> ComponentState:
    if report is None or now - report.reported_at > window:
        return ComponentState.UNKNOWN
    # `not_used` says nothing about the service's health.
    return _FROM_REPORT.get(report.state, ComponentState.UNKNOWN)


def summarize(
    reports: Mapping[str, ServiceReport],
    *,
    agent: ComponentState,
    now: datetime,
    window: timedelta,
) -> StatusSummary:
    """Combine the Agent's reachability with the recent reports of each data service."""
    components = {"api": ComponentState.OK, "agent": agent}
    for name in DATA_SERVICES:
        components[name] = _component(reports.get(name), now=now, window=window)

    states = set(components.values())
    if agent is ComponentState.UNAVAILABLE:
        overall = ComponentState.UNAVAILABLE
    elif states & _TROUBLED:
        overall = ComponentState.DEGRADED
    elif ComponentState.UNKNOWN in states:
        overall = ComponentState.UNKNOWN
    else:
        overall = ComponentState.OK
    return StatusSummary(status=overall, components=components, updated_at=now)


_MESSAGES = {
    ComponentState.OK: {
        "th": "ระบบทำงานปกติ",
        "en": "All services are working normally.",
    },
    ComponentState.DEGRADED: {
        "th": "บางบริการทำงานไม่เต็มที่ คำแนะนำอาจมีข้อมูลไม่ครบ",
        "en": "Some services are degraded; advice may be based on incomplete data.",
    },
    ComponentState.UNAVAILABLE: {
        "th": "ระบบวิเคราะห์การเดินทางใช้งานไม่ได้ชั่วคราว",
        "en": "Travel analysis is temporarily unavailable.",
    },
    ComponentState.UNKNOWN: {
        "th": "ยังไม่มีข้อมูลล่าสุดของบางบริการ",
        "en": "There is no recent information for some services.",
    },
}


def status_message(status: ComponentState, language: str) -> str:
    return _MESSAGES[status]["th" if language == "th" else "en"]


def is_ready(checks: Mapping[str, CheckState], required: frozenset[str]) -> bool:
    """Ready only when every required dependency answers (missing counts as down)."""
    return all(checks.get(name) is CheckState.OK for name in required)
