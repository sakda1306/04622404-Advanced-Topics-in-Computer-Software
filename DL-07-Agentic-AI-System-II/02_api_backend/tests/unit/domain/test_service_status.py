from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import ServiceState
from app.domain.service_status import (
    DATA_SERVICES,
    CheckState,
    ComponentState,
    ServiceReport,
    is_ready,
    status_message,
    summarize,
)

NOW = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)


def all_ok(at: datetime = NOW) -> dict[str, ServiceReport]:
    return {name: ServiceReport(ServiceState.OK, at) for name in DATA_SERVICES}


def test_all_services_reported_ok_is_ok() -> None:
    summary = summarize(all_ok(), agent=ComponentState.OK, now=NOW, window=WINDOW)

    assert summary.status is ComponentState.OK
    assert summary.components["api"] is ComponentState.OK
    assert list(summary.components) == ["api", "agent", *DATA_SERVICES]
    assert summary.updated_at == NOW


def test_missing_report_is_unknown_not_ok() -> None:
    reports = all_ok()
    del reports["disaster"]

    summary = summarize(reports, agent=ComponentState.OK, now=NOW, window=WINDOW)

    assert summary.components["disaster"] is ComponentState.UNKNOWN
    assert summary.status is ComponentState.UNKNOWN


def test_old_report_is_unknown() -> None:
    reports = all_ok()
    reports["weather"] = ServiceReport(ServiceState.OK, NOW - WINDOW - timedelta(seconds=1))

    summary = summarize(reports, agent=ComponentState.OK, now=NOW, window=WINDOW)

    assert summary.components["weather"] is ComponentState.UNKNOWN


def test_not_used_says_nothing_about_health() -> None:
    reports = all_ok()
    reports["rag"] = ServiceReport(ServiceState.NOT_USED, NOW)

    summary = summarize(reports, agent=ComponentState.OK, now=NOW, window=WINDOW)

    assert summary.components["rag"] is ComponentState.UNKNOWN


@pytest.mark.parametrize("state", [ServiceState.DEGRADED, ServiceState.UNAVAILABLE])
def test_a_troubled_service_degrades_the_whole(state: ServiceState) -> None:
    reports = all_ok()
    reports["transport"] = ServiceReport(state, NOW)
    del reports["llm"]

    summary = summarize(reports, agent=ComponentState.OK, now=NOW, window=WINDOW)

    assert summary.components["transport"].value == state.value
    assert summary.status is ComponentState.DEGRADED


def test_unreachable_agent_makes_the_service_unavailable() -> None:
    summary = summarize(all_ok(), agent=ComponentState.UNAVAILABLE, now=NOW, window=WINDOW)

    assert summary.status is ComponentState.UNAVAILABLE


def test_agent_degraded_degrades_the_whole() -> None:
    summary = summarize(all_ok(), agent=ComponentState.DEGRADED, now=NOW, window=WINDOW)

    assert summary.status is ComponentState.DEGRADED


def test_messages_follow_the_language() -> None:
    assert status_message(ComponentState.OK, "th") == "ระบบทำงานปกติ"
    assert status_message(ComponentState.DEGRADED, "ja").startswith("Some services")


def test_ready_needs_every_required_check() -> None:
    required = frozenset({"database", "redis"})

    assert is_ready({"database": CheckState.OK, "redis": CheckState.OK}, required)
    assert is_ready(
        {"database": CheckState.OK, "redis": CheckState.OK, "agent": CheckState.UNAVAILABLE},
        required,
    )
    assert not is_ready({"database": CheckState.OK, "redis": CheckState.UNAVAILABLE}, required)
    assert not is_ready({"database": CheckState.OK}, required)
