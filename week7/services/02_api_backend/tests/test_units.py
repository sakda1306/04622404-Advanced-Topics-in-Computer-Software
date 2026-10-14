"""Pure pieces: circuit breaker, router client retries, beat timetable, helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import httpx
import pytest

from app.clients.circuit_breaker import BreakerState, CircuitBreaker
from app.clients.router_client import RouterClient
from app.core.clock import BANGKOK, season_for
from app.core.errors import AppError, ErrorCode
from app.response_log.admin_queries import percentile
from app.response_log.cursor import decode_cursor, encode_cursor
from app.schemas.chat import RouteContext, RouteRequest, RouteUser
from app.schemas.common import Source
from app.services.chat_service import data_as_of
from app.workers.schedule import beat_schedule


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, window_seconds=60, reset_seconds=30, clock=clock)


def test_breaker_opens_after_threshold_and_half_opens() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        assert breaker.allow()
        breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert not breaker.allow()
    assert breaker.retry_after() == 30

    clock.now += 30
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.allow()  # the single probe
    assert not breaker.allow()
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED


def test_breaker_failed_probe_reopens() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        breaker.record_failure()
    clock.now += 31
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN


def test_breaker_forgets_old_failures() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.now += 61
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED


def route_request() -> RouteRequest:
    return RouteRequest(
        request_id="r1",
        session_id=uuid.uuid4(),
        user=RouteUser(id=uuid.uuid4(), favorite_team_id=None, language="th"),
        query="q",
        history=[],
        context=RouteContext(season="2026", current_matchweek=5, now="2026-09-22T10:00:00+07:00"),
    )


OK_BODY = {"answer": "a", "route": "general_ai", "sources": [], "engines_used": []}


async def no_sleep(_seconds: float) -> None:
    return None


def router_client(handler: object, breaker: CircuitBreaker | None = None) -> RouterClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return RouterClient(
        http,
        base_url="http://router:8000",
        timeout_seconds=5,
        max_retries=1,
        breaker=breaker or make_breaker(FakeClock()),
        sleep=no_sleep,
    )


async def test_router_client_retries_once_on_503() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["request_id"])
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=OK_BODY)

    result = await router_client(handler).route(route_request())
    assert result.answer == "a"
    assert calls == ["r1", "r1"]


async def test_router_client_does_not_retry_500() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    with pytest.raises(AppError) as err:
        await router_client(handler).route(route_request())
    assert err.value.code is ErrorCode.ROUTER_UNAVAILABLE
    assert len(calls) == 1


async def test_router_client_bad_body_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "a", "route": "not-a-route"})

    with pytest.raises(AppError) as err:
        await router_client(handler).route(route_request())
    assert err.value.code is ErrorCode.ROUTER_UNAVAILABLE


async def test_router_client_stops_calling_when_circuit_is_open() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    client = router_client(handler)
    for _ in range(3):
        with pytest.raises(AppError):
            await client.route(route_request())
    with pytest.raises(AppError) as err:
        await client.route(route_request())
    assert err.value.code is ErrorCode.ROUTER_UNAVAILABLE
    assert err.value.retry_after == 30
    assert len(calls) == 3


def _fires(schedule: object, moment: datetime) -> bool:
    cron = schedule  # celery crontab
    return (
        moment.minute in cron.minute  # type: ignore[attr-defined]
        and moment.hour in cron.hour  # type: ignore[attr-defined]
        and moment.isoweekday() % 7 in cron.day_of_week  # type: ignore[attr-defined]
    )


def _fixture_runs(moment: datetime) -> int:
    return sum(
        _fires(entry["schedule"], moment)
        for entry in beat_schedule().values()
        if entry["kwargs"].get("scope") == "fixtures"
    )


@pytest.mark.parametrize(
    ("moment", "runs"),
    [
        (datetime(2026, 9, 25, 18, 0, tzinfo=BANGKOK), 1),  # Fri 18:00, window opens
        (datetime(2026, 9, 25, 17, 30, tzinfo=BANGKOK), 0),  # Fri 17:30, not yet
        (datetime(2026, 9, 26, 3, 30, tzinfo=BANGKOK), 1),  # Sat night
        (datetime(2026, 9, 28, 22, 30, tzinfo=BANGKOK), 1),  # Mon night
        (datetime(2026, 9, 29, 6, 0, tzinfo=BANGKOK), 1),  # Tue 06:00, window closes
        (datetime(2026, 9, 29, 6, 30, tzinfo=BANGKOK), 0),
        (datetime(2026, 9, 29, 12, 0, tzinfo=BANGKOK), 1),  # Tue every 6 h
        (datetime(2026, 9, 30, 6, 0, tzinfo=BANGKOK), 1),  # Wed every 6 h
        (datetime(2026, 9, 30, 9, 0, tzinfo=BANGKOK), 0),
        (datetime(2026, 10, 2, 12, 0, tzinfo=BANGKOK), 1),  # Fri noon
        (datetime(2026, 10, 2, 18, 0, tzinfo=BANGKOK), 1),  # counted once, not twice
    ],
)
def test_fixture_ingest_timetable(moment: datetime, runs: int) -> None:
    assert _fixture_runs(moment) == runs


def test_weekly_report_runs_monday_and_tuesday_morning() -> None:
    report = beat_schedule()["weekly-report"]["schedule"]
    assert _fires(report, datetime(2026, 9, 28, 9, 0, tzinfo=BANGKOK))
    assert _fires(report, datetime(2026, 9, 29, 9, 0, tzinfo=BANGKOK))
    assert not _fires(report, datetime(2026, 9, 30, 9, 0, tzinfo=BANGKOK))


def _source(origin: str, fetched_at: str | None) -> Source:
    return Source(ref=1, doc_id="d", origin=origin, fetched_at=fetched_at)


def test_data_as_of_is_oldest_live_source() -> None:
    sources = [
        _source("kb", None),
        _source("football-data.org", "2026-09-21T09:00:00+07:00"),
        _source("api-football", "2026-09-20T23:00:00+07:00"),
    ]
    assert data_as_of(sources) == "2026-09-20T23:00:00+07:00"
    assert data_as_of([_source("kb", None)]) is None


def test_percentile() -> None:
    assert percentile([], 50) == 0
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile(list(range(1, 101)), 95) == 95


def test_cursor_round_trip() -> None:
    moment = datetime(2026, 9, 24, 10, 0, tzinfo=BANGKOK)
    item = uuid.uuid4()
    decoded_at, decoded_id = decode_cursor(encode_cursor(moment, item))
    assert decoded_at == moment
    assert decoded_id == str(item)


def test_season_for() -> None:
    assert season_for(datetime(2026, 9, 1)) == "2026"
    assert season_for(datetime(2027, 3, 1)) == "2026"
