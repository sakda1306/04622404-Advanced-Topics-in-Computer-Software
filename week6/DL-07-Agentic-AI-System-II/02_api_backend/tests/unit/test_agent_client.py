"""AgentClient behaviour and the error mapping of docs/02_api_spec.md section 9.5."""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from app.core.clock import SystemClock
from app.core.config import AgentSettings
from app.core.errors import ErrorCode
from app.core.ids import correlation_id_var, request_id_var
from app.domain.enums import AgentRunStatus
from app.infrastructure.agent.auth import AgentTokenError, NoAuth, StaticToken
from app.infrastructure.agent.circuit_breaker import RedisCircuitBreaker
from app.infrastructure.agent.client import (
    AgentCallError,
    AgentClient,
    AgentFailure,
)
from app.infrastructure.agent.contracts import ProgressLine
from tests.support.agent import run_request, run_response

BASE = "http://agent.test"
# Building an SSL context per client costs ~0.25 s; share one across the tests.
SSL_CONTEXT = ssl.create_default_context()
RUNS = f"{BASE}/v1/agent/runs"


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_settings(**overrides: Any) -> AgentSettings:
    values: dict[str, Any] = {
        "agent_service_url": BASE,
        "agent_max_retries": 2,
        "agent_retry_base_seconds": 0.5,
        "agent_cb_failure_threshold": 5,
    }
    return AgentSettings(**(values | overrides))


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(verify=SSL_CONTEXT) as client:
        yield client


@pytest.fixture
def breaker(redis: FakeAsyncRedis) -> RedisCircuitBreaker:
    return RedisCircuitBreaker(
        redis, name="cb:agent", failure_threshold=3, window_seconds=30, reset_seconds=30
    )


@pytest.fixture
def client(http: httpx.AsyncClient, breaker: RedisCircuitBreaker, sleeps: Sleeps) -> AgentClient:
    return AgentClient(
        http,
        settings=make_settings(),
        tokens=NoAuth(),
        breaker=breaker,
        sleep=sleeps,
        jitter=lambda: 0.0,
    )


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def deadline(seconds: float = 30) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


async def failure_of(client: AgentClient, **kwargs: Any) -> AgentCallError:
    with pytest.raises(AgentCallError) as info:
        await client.run(run_request(), deadline=deadline(), **kwargs)
    return info.value


# ------------------------------------------------------------------ success


async def test_successful_run(client: AgentClient, mock: respx.MockRouter) -> None:
    request = run_request()
    route = mock.post(RUNS).mock(
        return_value=httpx.Response(200, json=run_response(request.run_id))
    )

    result = await client.run(request, deadline=deadline())

    assert result.response.run_id == request.run_id
    assert result.response.recommendation is not None
    assert [a.status for a in result.attempts] == [AgentRunStatus.SUCCESS]
    sent = route.calls.last.request
    assert json.loads(sent.content)["run_id"] == str(request.run_id)
    assert sent.headers["accept"] == "application/json"
    assert sent.headers["user-agent"] == "tsa-backend"


async def test_request_headers_carry_ids_deadline_and_token(
    http: httpx.AsyncClient, breaker: RedisCircuitBreaker, mock: respx.MockRouter
) -> None:
    client = AgentClient(
        http, settings=make_settings(), tokens=StaticToken(SecretStr("svc")), breaker=breaker
    )
    request = run_request()
    route = mock.post(RUNS).mock(
        return_value=httpx.Response(200, json=run_response(request.run_id))
    )
    request_id_var.set("req-1")
    correlation_id_var.set("corr-1")
    when = datetime(2030, 1, 1, 8, 0, tzinfo=UTC)

    try:
        await client.run(request, deadline=when)
    finally:
        request_id_var.set(None)
        correlation_id_var.set(None)

    headers = route.calls.last.request.headers
    assert headers["x-request-id"] == "req-1"
    assert headers["x-correlation-id"] == "corr-1"
    assert headers["x-deadline"] == "2030-01-01T08:00:00Z"
    assert headers["authorization"] == "Bearer svc"


async def test_diagnostics_are_parsed_and_unknown_fields_ignored(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    request = run_request()
    body = run_response(request.run_id, future_field={"x": 1})
    mock.post(RUNS).mock(return_value=httpx.Response(200, json=body))

    result = await client.run(request, deadline=deadline())

    assert result.response.diagnostics is not None
    assert result.response.diagnostics.tool_calls == 3


# ------------------------------------------------------------------ NDJSON stream


def ndjson(*lines: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(line).encode() + b"\n" for line in lines)


async def test_stream_reports_progress_then_result(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    request = run_request()
    body = ndjson(
        {"type": "progress", "stage": "fetching_data", "progress": 20},
        {"type": "progress", "stage": "assessing_risk", "progress": 60, "message": "risk"},
        {"type": "result", **run_response(request.run_id)},
    )
    route = mock.post(RUNS).mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "application/x-ndjson"}
        )
    )
    seen: list[ProgressLine] = []

    async def on_progress(line: ProgressLine) -> None:
        seen.append(line)

    result = await client.run(request, deadline=deadline(), on_progress=on_progress)

    assert [(p.stage, p.progress) for p in seen] == [("fetching_data", 20), ("assessing_risk", 60)]
    assert result.response.status == "completed"
    assert route.calls.last.request.headers["accept"] == "application/x-ndjson"


async def test_failing_progress_callback_does_not_fail_the_run(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    request = run_request()
    body = ndjson(
        {"type": "progress", "stage": "fetching_data", "progress": 20},
        {"type": "result", **run_response(request.run_id)},
    )
    mock.post(RUNS).mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "application/x-ndjson"}
        )
    )

    async def broken(line: ProgressLine) -> None:
        raise RuntimeError("redis publish failed")

    result = await client.run(request, deadline=deadline(), on_progress=broken)

    assert result.response.run_id == request.run_id


@pytest.mark.parametrize(
    ("lines", "failure", "status"),
    [
        (
            [{"type": "progress", "stage": "fetching_data", "progress": 20}],
            AgentFailure.BAD_RESPONSE,
            502,
        ),
        ([{"type": "nonsense"}], AgentFailure.BAD_RESPONSE, 502),
        (
            [{"type": "progress", "stage": "fetching_data", "progress": 250}],
            AgentFailure.BAD_RESPONSE,
            502,
        ),
        ([{"type": "error", "code": "BUDGET_EXCEEDED"}], AgentFailure.TIMEOUT, 504),
        ([{"type": "error", "code": "ALL_PROVIDERS_DOWN"}], AgentFailure.UNAVAILABLE, 503),
    ],
)
async def test_stream_failures(
    client: AgentClient,
    mock: respx.MockRouter,
    lines: list[dict[str, Any]],
    failure: AgentFailure,
    status: int,
) -> None:
    mock.post(RUNS).mock(
        return_value=httpx.Response(
            200, content=ndjson(*lines), headers={"content-type": "application/x-ndjson"}
        )
    )

    error = await failure_of(client, on_progress=None)

    assert error.failure is failure
    assert error.to_app_error().status == status
    assert len(error.attempts) == 1


async def test_non_json_stream_line_is_bad_response(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    mock.post(RUNS).mock(
        return_value=httpx.Response(
            200, content=b"not json\n", headers={"content-type": "application/x-ndjson"}
        )
    )

    assert (await failure_of(client)).failure is AgentFailure.BAD_RESPONSE


# ------------------------------------------------------------------ retries


async def test_retries_temporary_errors_with_backoff(
    client: AgentClient, mock: respx.MockRouter, sleeps: Sleeps
) -> None:
    request = run_request()
    mock.post(RUNS).mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("refused"),
            httpx.Response(200, json=run_response(request.run_id)),
        ]
    )

    result = await client.run(request, deadline=deadline())

    assert sleeps.delays == [0.5, 1.0]
    assert [a.status for a in result.attempts] == [
        AgentRunStatus.ERROR,
        AgentRunStatus.ERROR,
        AgentRunStatus.SUCCESS,
    ]
    assert [a.attempt for a in result.attempts] == [1, 2, 3]
    assert result.attempts[0].http_status == 503


async def test_retry_after_header_is_respected(
    client: AgentClient, mock: respx.MockRouter, sleeps: Sleeps
) -> None:
    request = run_request()
    mock.post(RUNS).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json=run_response(request.run_id)),
        ]
    )

    await client.run(request, deadline=deadline())

    assert sleeps.delays == [3.0]


async def test_jitter_is_added_to_backoff(
    http: httpx.AsyncClient, breaker: RedisCircuitBreaker, sleeps: Sleeps, mock: respx.MockRouter
) -> None:
    client = AgentClient(
        http,
        settings=make_settings(),
        tokens=NoAuth(),
        breaker=breaker,
        sleep=sleeps,
        jitter=lambda: 0.5,
    )
    mock.post(RUNS).mock(return_value=httpx.Response(502))

    await failure_of(client)

    assert sleeps.delays == [0.75, 1.25]


@pytest.mark.parametrize("status", [502, 503, 504, 429])
async def test_exhausted_retries_map_to_503(
    client: AgentClient, mock: respx.MockRouter, status: int
) -> None:
    route = mock.post(RUNS).mock(return_value=httpx.Response(status))

    error = await failure_of(client)
    app_error = error.to_app_error()

    assert route.call_count == 3
    assert error.failure is AgentFailure.UNAVAILABLE
    assert app_error.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert app_error.retry_after == 5
    assert len(error.attempts) == 3


async def test_no_retry_when_backoff_would_pass_the_deadline(
    client: AgentClient, mock: respx.MockRouter, sleeps: Sleeps
) -> None:
    route = mock.post(RUNS).mock(return_value=httpx.Response(503, headers={"Retry-After": "60"}))

    with pytest.raises(AgentCallError):
        await client.run(run_request(), deadline=deadline(10))

    assert route.call_count == 1
    assert sleeps.delays == []


@pytest.mark.parametrize(
    ("response", "failure", "code"),
    [
        (httpx.Response(500), AgentFailure.UNAVAILABLE, ErrorCode.DEPENDENCY_UNAVAILABLE),
        (httpx.Response(400), AgentFailure.CLIENT_ERROR, ErrorCode.INTERNAL_ERROR),
        (httpx.Response(401), AgentFailure.CLIENT_ERROR, ErrorCode.INTERNAL_ERROR),
        (httpx.Response(422), AgentFailure.CLIENT_ERROR, ErrorCode.INTERNAL_ERROR),
        (
            httpx.Response(200, json={"status": "done"}),
            AgentFailure.BAD_RESPONSE,
            ErrorCode.AGENT_BAD_RESPONSE,
        ),
        (
            httpx.Response(200, content=b"<html>"),
            AgentFailure.BAD_RESPONSE,
            ErrorCode.AGENT_BAD_RESPONSE,
        ),
    ],
)
async def test_non_retryable_failures(
    client: AgentClient,
    mock: respx.MockRouter,
    response: httpx.Response,
    failure: AgentFailure,
    code: ErrorCode,
) -> None:
    route = mock.post(RUNS).mock(return_value=response)

    error = await failure_of(client)

    assert route.call_count == 1
    assert error.failure is failure
    assert error.to_app_error().code is code


async def test_run_id_mismatch_is_bad_response(client: AgentClient, mock: respx.MockRouter) -> None:
    mock.post(RUNS).mock(return_value=httpx.Response(200, json=run_response(run_request().run_id)))

    error = await failure_of(client)

    assert error.failure is AgentFailure.BAD_RESPONSE
    assert error.attempts[0].status is AgentRunStatus.BAD_RESPONSE


async def test_bad_response_error_hides_the_body(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    mock.post(RUNS).mock(
        return_value=httpx.Response(200, json={"status": "done", "secret": "user question"})
    )

    error = await failure_of(client)

    assert "user question" not in str(error)
    assert "user question" not in str(error.to_app_error().log_context)


async def test_oversized_response_is_bad_response(
    http: httpx.AsyncClient, breaker: RedisCircuitBreaker, mock: respx.MockRouter
) -> None:
    client = AgentClient(
        http,
        settings=make_settings(agent_max_response_bytes=100),
        tokens=NoAuth(),
        breaker=breaker,
    )
    request = run_request()
    mock.post(RUNS).mock(return_value=httpx.Response(200, json=run_response(request.run_id)))

    assert (await failure_of(client)).failure is AgentFailure.BAD_RESPONSE


# ------------------------------------------------------------------ timeouts / deadline


async def test_slow_agent_hits_the_deadline(
    http: httpx.AsyncClient, breaker: RedisCircuitBreaker, mock: respx.MockRouter
) -> None:
    client = AgentClient(
        http, settings=make_settings(), tokens=NoAuth(), breaker=breaker, clock=SystemClock()
    )
    request = run_request()

    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=run_response(request.run_id))

    mock.post(RUNS).mock(side_effect=slow)
    started = asyncio.get_running_loop().time()

    with pytest.raises(AgentCallError) as info:
        await client.run(request, deadline=deadline(0.3))

    elapsed = asyncio.get_running_loop().time() - started
    assert info.value.failure is AgentFailure.TIMEOUT
    assert info.value.to_app_error().code is ErrorCode.AGENT_TIMEOUT
    assert elapsed < 2
    assert info.value.attempts[0].status is AgentRunStatus.TIMEOUT


async def test_read_timeout_is_not_retried(client: AgentClient, mock: respx.MockRouter) -> None:
    route = mock.post(RUNS).mock(side_effect=httpx.ReadTimeout("slow"))

    error = await failure_of(client)

    assert error.failure is AgentFailure.TIMEOUT
    assert route.call_count == 1


async def test_connect_timeout_is_retried(client: AgentClient, mock: respx.MockRouter) -> None:
    route = mock.post(RUNS).mock(side_effect=httpx.ConnectTimeout("no route"))

    error = await failure_of(client)

    assert error.failure is AgentFailure.UNAVAILABLE
    assert route.call_count == 3


async def test_past_deadline_makes_no_call(client: AgentClient, mock: respx.MockRouter) -> None:
    route = mock.post(RUNS)

    with pytest.raises(AgentCallError) as info:
        await client.run(run_request(), deadline=datetime.now(UTC) - timedelta(seconds=1))

    assert info.value.failure is AgentFailure.TIMEOUT
    assert route.call_count == 0


# ------------------------------------------------------------------ circuit breaker


async def test_circuit_opens_after_repeated_failures(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    route = mock.post(RUNS).mock(return_value=httpx.Response(503))

    first = await failure_of(client)  # 3 attempts -> threshold (3) reached
    second = await failure_of(client)

    assert first.failure is AgentFailure.UNAVAILABLE
    assert second.failure is AgentFailure.CIRCUIT_OPEN
    assert route.call_count == 3
    app_error = second.to_app_error()
    assert app_error.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert 1 <= (app_error.retry_after or 0) <= 30
    assert second.attempts[0].status is AgentRunStatus.CIRCUIT_OPEN


async def test_client_errors_do_not_open_the_circuit(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    route = mock.post(RUNS).mock(return_value=httpx.Response(200, json={"bad": True}))

    for _ in range(5):
        assert (await failure_of(client)).failure is AgentFailure.BAD_RESPONSE

    assert route.call_count == 5


# ------------------------------------------------------------------ auth, cancel, health


class _BrokenTokens:
    async def authorization(self) -> str | None:
        raise AgentTokenError("idp down")


async def test_token_failure_is_retried_then_unavailable(
    http: httpx.AsyncClient, breaker: RedisCircuitBreaker, sleeps: Sleeps, mock: respx.MockRouter
) -> None:
    client = AgentClient(
        http, settings=make_settings(), tokens=_BrokenTokens(), breaker=breaker, sleep=sleeps
    )
    route = mock.post(RUNS)

    error = await failure_of(client)

    assert error.failure is AgentFailure.UNAVAILABLE
    assert route.call_count == 0
    assert len(sleeps.delays) == 2


async def test_cancelled_caller_asks_the_agent_to_stop(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    request = run_request()
    started = asyncio.Event()

    async def hang(_: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(10)
        return httpx.Response(200)

    mock.post(RUNS).mock(side_effect=hang)
    cancel = mock.delete(f"{RUNS}/{request.run_id}").mock(return_value=httpx.Response(202))

    task = asyncio.create_task(client.run(request, deadline=deadline()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancel.call_count == 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [(httpx.Response(202), True), (httpx.Response(404), True), (httpx.Response(500), False)],
)
async def test_cancel_result(
    client: AgentClient, mock: respx.MockRouter, response: httpx.Response, expected: bool
) -> None:
    request = run_request()
    mock.delete(f"{RUNS}/{request.run_id}").mock(return_value=response)

    assert await client.cancel(request.run_id) is expected


async def test_cancel_network_error_returns_false(
    client: AgentClient, mock: respx.MockRouter
) -> None:
    request = run_request()
    mock.delete(f"{RUNS}/{request.run_id}").mock(side_effect=httpx.ConnectError("down"))

    assert await client.cancel(request.run_id) is False


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [(httpx.Response(200), True), (httpx.Response(503), False), (httpx.ConnectError("x"), False)],
)
async def test_health(
    client: AgentClient, mock: respx.MockRouter, side_effect: Any, expected: bool
) -> None:
    mock.get(f"{BASE}/health").mock(side_effect=[side_effect])

    assert await client.health() is expected


def test_attempt_duration() -> None:
    from app.infrastructure.agent.client import AttemptRecord

    start = datetime(2026, 1, 1, tzinfo=UTC)
    record = AttemptRecord(1, AgentRunStatus.SUCCESS, start, start + timedelta(milliseconds=1500))

    assert record.duration_ms == 1500
