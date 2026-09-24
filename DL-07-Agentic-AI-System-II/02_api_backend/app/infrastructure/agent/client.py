"""HTTP client for the Travel AI Agent (docs/02_api_spec.md sections 9.1-9.5).

Every call carries a deadline. Temporary failures (connect errors, 429/502/503/504)
are retried with exponential backoff and jitter while the deadline allows; the shared
circuit breaker stops calls when the Agent keeps failing. Error mapping to HTTP
responses follows section 9.5 (`AgentCallError.to_app_error`).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.clock import Clock, SystemClock
from app.core.config import AgentSettings
from app.core.errors import AppError, ErrorCode
from app.core.ids import current_correlation_id, current_request_id
from app.core.logging import get_logger
from app.core.metrics import AGENT_DURATION, AGENT_ERRORS
from app.domain.enums import AgentRunStatus as RunRecordStatus
from app.infrastructure.agent.auth import AgentTokenError, AgentTokenProvider
from app.infrastructure.agent.circuit_breaker import BreakerState, CircuitBreaker
from app.infrastructure.agent.contracts import (
    AgentRunRequest,
    AgentRunResponse,
    ErrorLine,
    ProgressLine,
    ResultLine,
    StreamLine,
    deadline_header,
)

log = get_logger(__name__)

RUNS_PATH = "/v1/agent/runs"
NDJSON = "application/x-ndjson"
_RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})
_STREAM_LINES: TypeAdapter[ProgressLine | ResultLine | ErrorLine] = TypeAdapter(StreamLine)
# Agent error codes that mean it ran out of time or budget.
_TIMEOUT_CODES = frozenset({"TIMEOUT", "DEADLINE_EXCEEDED", "BUDGET_EXCEEDED"})

ProgressCallback = Callable[[ProgressLine], Awaitable[None]]


def _observe(attempt: AttemptRecord) -> None:
    seconds = (attempt.finished_at - attempt.started_at).total_seconds()
    AGENT_DURATION.labels(outcome=attempt.status.value).observe(max(seconds, 0.0))


class AgentFailure(StrEnum):
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    BAD_RESPONSE = "bad_response"
    CLIENT_ERROR = "client_error"
    CIRCUIT_OPEN = "circuit_open"


_RECORD_STATUS = {
    AgentFailure.TIMEOUT: RunRecordStatus.TIMEOUT,
    AgentFailure.UNAVAILABLE: RunRecordStatus.ERROR,
    AgentFailure.BAD_RESPONSE: RunRecordStatus.BAD_RESPONSE,
    AgentFailure.CLIENT_ERROR: RunRecordStatus.ERROR,
    AgentFailure.CIRCUIT_OPEN: RunRecordStatus.CIRCUIT_OPEN,
}


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One call to the Agent; persisted to `agent_runs` by the worker (step 5.6)."""

    attempt: int
    status: RunRecordStatus
    started_at: datetime
    finished_at: datetime
    http_status: int | None = None
    error_code: str | None = None

    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


@dataclass(frozen=True, slots=True)
class AgentCallResult:
    response: AgentRunResponse
    attempts: tuple[AttemptRecord, ...]


class AgentCallError(Exception):
    def __init__(
        self,
        failure: AgentFailure,
        detail: str,
        *,
        http_status: int | None = None,
        retry_after: int | None = None,
        attempts: tuple[AttemptRecord, ...] = (),
    ) -> None:
        super().__init__(f"{failure.value}: {detail}")
        self.failure = failure
        self.detail = detail
        self.http_status = http_status
        self.retry_after = retry_after
        self.attempts = attempts

    def to_app_error(self) -> AppError:
        context = {"agent_failure": self.failure.value, "agent_status": self.http_status}
        match self.failure:
            case AgentFailure.TIMEOUT:
                return AppError(ErrorCode.AGENT_TIMEOUT, log_context=context)
            case AgentFailure.BAD_RESPONSE:
                return AppError(ErrorCode.AGENT_BAD_RESPONSE, log_context=context)
            case AgentFailure.CLIENT_ERROR:
                # The Agent rejected our request: a bug on our side, not the user's.
                return AppError(ErrorCode.INTERNAL_ERROR, log_context=context)
            case AgentFailure.UNAVAILABLE | AgentFailure.CIRCUIT_OPEN:
                return AppError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    retry_after=self.retry_after or 5,
                    log_context=context,
                )


@dataclass
class _AttemptFailed(Exception):
    failure: AgentFailure
    detail: str
    retryable: bool = False
    # Whether this failure says the Agent is unhealthy (feeds the circuit breaker).
    unhealthy: bool = False
    http_status: int | None = None
    retry_after: int | None = None
    error_code: str | None = field(default=None)


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after", "")
    return int(value) if value.isdigit() else None


class AgentClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        settings: AgentSettings,
        tokens: AgentTokenProvider,
        breaker: CircuitBreaker,
        user_agent: str = "tsa-backend",
        clock: Clock | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._http = http
        self._base_url = settings.agent_service_url.rstrip("/")
        self._settings = settings
        self._tokens = tokens
        self._breaker = breaker
        self._user_agent = user_agent
        self._clock = clock or SystemClock()
        self._sleep = sleep
        self._jitter = jitter

    # ------------------------------------------------------------------ public

    async def run(
        self,
        request: AgentRunRequest,
        *,
        deadline: datetime,
        on_progress: ProgressCallback | None = None,
    ) -> AgentCallResult:
        attempts: list[AttemptRecord] = []
        max_attempts = 1 + self._settings.agent_max_retries
        for number in range(1, max_attempts + 1):
            if self._remaining(deadline) <= 0:
                AGENT_ERRORS.labels(code=AgentFailure.TIMEOUT.value).inc()
                raise self._error_from_last(attempts, AgentFailure.TIMEOUT, "deadline passed")

            admission = await self._breaker.acquire()
            if not admission.allowed:
                now = self._clock.now()
                attempts.append(AttemptRecord(number, RunRecordStatus.CIRCUIT_OPEN, now, now))
                AGENT_ERRORS.labels(code=AgentFailure.CIRCUIT_OPEN.value).inc()
                raise AgentCallError(
                    AgentFailure.CIRCUIT_OPEN,
                    "circuit open",
                    retry_after=max(admission.retry_after_seconds, 1),
                    attempts=tuple(attempts),
                )

            started = self._clock.now()
            try:
                response = await self._attempt(request, deadline, on_progress)
            except _AttemptFailed as failed:
                attempts.append(
                    AttemptRecord(
                        number,
                        _RECORD_STATUS[failed.failure],
                        started,
                        self._clock.now(),
                        http_status=failed.http_status,
                        error_code=failed.error_code or failed.failure.value,
                    )
                )
                _observe(attempts[-1])
                if failed.unhealthy:
                    await self._breaker.record_failure()
                elif failed.http_status is not None:
                    # The Agent answered, so it is reachable (this also closes a probe).
                    await self._breaker.record_success()
                error = AgentCallError(
                    failed.failure,
                    failed.detail,
                    http_status=failed.http_status,
                    retry_after=failed.retry_after,
                    attempts=tuple(attempts),
                )
                log.warning(
                    "agent_call_failed",
                    run_id=str(request.run_id),
                    attempt=number,
                    failure=failed.failure.value,
                    agent_status=failed.http_status,
                )
                if not failed.retryable or number == max_attempts:
                    AGENT_ERRORS.labels(code=failed.failure.value).inc()
                    raise error from None
                delay = self._backoff(number, failed.retry_after)
                if delay >= self._remaining(deadline):
                    AGENT_ERRORS.labels(code=failed.failure.value).inc()
                    raise error from None
                await self._sleep(delay)
                continue
            except asyncio.CancelledError:
                attempts.append(
                    AttemptRecord(number, RunRecordStatus.CANCELLED, started, self._clock.now())
                )
                _observe(attempts[-1])
                await self._cancel_after_interrupt(request.run_id)
                raise

            attempts.append(
                AttemptRecord(
                    number,
                    RunRecordStatus.SUCCESS,
                    started,
                    self._clock.now(),
                    http_status=200,
                )
            )
            _observe(attempts[-1])
            await self._breaker.record_success()
            return AgentCallResult(response=response, attempts=tuple(attempts))

        raise AssertionError("unreachable")  # pragma: no cover

    async def cancel(self, run_id: UUID) -> bool:
        """Ask the Agent to stop a run. Returns False if the request did not get through."""
        try:
            response = await self._http.delete(
                f"{self._base_url}{RUNS_PATH}/{run_id}",
                headers=await self._headers(accept="application/json"),
                timeout=self._settings.agent_cancel_timeout_seconds,
            )
        except (httpx.HTTPError, AgentTokenError) as exc:
            log.warning("agent_cancel_failed", run_id=str(run_id), error_type=type(exc).__name__)
            return False
        return response.status_code < 400 or response.status_code == 404

    async def breaker_state(self) -> BreakerState:
        return await self._breaker.state()

    async def health(self) -> bool:
        try:
            response = await self._http.get(
                f"{self._base_url}/health",
                timeout=self._settings.agent_connect_timeout_seconds,
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    # ------------------------------------------------------------------ one attempt

    async def _attempt(
        self,
        request: AgentRunRequest,
        deadline: datetime,
        on_progress: ProgressCallback | None,
    ) -> AgentRunResponse:
        remaining = self._remaining(deadline)
        try:
            headers = await self._headers(
                accept=NDJSON if on_progress else "application/json",
                deadline=deadline,
            )
        except AgentTokenError as exc:
            raise _AttemptFailed(
                AgentFailure.UNAVAILABLE, "agent token unavailable", retryable=True
            ) from exc

        timeout = httpx.Timeout(
            remaining, connect=min(self._settings.agent_connect_timeout_seconds, remaining)
        )
        try:
            # httpx timeouts apply per operation; asyncio.timeout bounds the whole call.
            async with (
                asyncio.timeout(remaining),
                self._http.stream(
                    "POST",
                    f"{self._base_url}{RUNS_PATH}",
                    json=request.model_dump(mode="json"),
                    headers=headers,
                    timeout=timeout,
                ) as response,
            ):
                self._check_status(response)
                if response.headers.get("content-type", "").startswith(NDJSON):
                    result = await self._read_stream(response, on_progress)
                else:
                    result = self._parse(await self._read_body(response))
        except httpx.ConnectTimeout as exc:
            raise _AttemptFailed(
                AgentFailure.UNAVAILABLE, "connect timeout", retryable=True, unhealthy=True
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise _AttemptFailed(AgentFailure.TIMEOUT, "deadline exceeded", unhealthy=True) from exc
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise _AttemptFailed(
                AgentFailure.UNAVAILABLE, type(exc).__name__, retryable=True, unhealthy=True
            ) from exc

        if result.run_id != request.run_id:
            raise _AttemptFailed(AgentFailure.BAD_RESPONSE, "run_id mismatch", http_status=200)
        return result

    def _check_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in _RETRYABLE_STATUS:
            raise _AttemptFailed(
                AgentFailure.UNAVAILABLE,
                f"agent returned {status}",
                retryable=True,
                unhealthy=True,
                http_status=status,
                retry_after=_retry_after(response),
            )
        if status >= 500:
            raise _AttemptFailed(
                AgentFailure.UNAVAILABLE,
                f"agent returned {status}",
                unhealthy=True,
                http_status=status,
            )
        raise _AttemptFailed(
            AgentFailure.CLIENT_ERROR, f"agent rejected request with {status}", http_status=status
        )

    async def _read_body(self, response: httpx.Response) -> bytes:
        limit = self._settings.agent_max_response_bytes
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > limit:
                raise _AttemptFailed(
                    AgentFailure.BAD_RESPONSE, "response too large", http_status=200
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _parse(self, body: bytes) -> AgentRunResponse:
        try:
            return AgentRunResponse.model_validate_json(body)
        except ValidationError as exc:
            # Only the count is logged: the body may contain user data.
            raise _AttemptFailed(
                AgentFailure.BAD_RESPONSE,
                f"schema validation failed ({exc.error_count()} errors)",
                http_status=200,
            ) from None

    async def _read_stream(
        self, response: httpx.Response, on_progress: ProgressCallback | None
    ) -> AgentRunResponse:
        limit = self._settings.agent_max_response_bytes
        size = 0
        async for raw in response.aiter_lines():
            size += len(raw)
            if size > limit:
                raise _AttemptFailed(AgentFailure.BAD_RESPONSE, "stream too large", http_status=200)
            if not raw.strip():
                continue
            try:
                line = _STREAM_LINES.validate_json(raw)
            except ValidationError:
                raise _AttemptFailed(
                    AgentFailure.BAD_RESPONSE, "invalid stream line", http_status=200
                ) from None
            if isinstance(line, ProgressLine):
                await self._notify(on_progress, line)
            elif isinstance(line, ResultLine):
                return AgentRunResponse.model_validate(line.model_dump(by_alias=True))
            else:
                timed_out = line.code.upper() in _TIMEOUT_CODES
                raise _AttemptFailed(
                    AgentFailure.TIMEOUT if timed_out else AgentFailure.UNAVAILABLE,
                    f"agent reported {line.code}",
                    http_status=200,
                    error_code=line.code[:40],
                )
        raise _AttemptFailed(
            AgentFailure.BAD_RESPONSE, "stream ended without a result", http_status=200
        )

    # ------------------------------------------------------------------ helpers

    async def _notify(self, on_progress: ProgressCallback | None, line: ProgressLine) -> None:
        if on_progress is None:
            return
        try:
            await on_progress(line)
        except Exception as exc:
            # Losing a progress update must not fail the run.
            log.warning("agent_progress_callback_failed", error_type=type(exc).__name__)

    async def _headers(self, *, accept: str, deadline: datetime | None = None) -> dict[str, str]:
        headers = {"Accept": accept, "User-Agent": self._user_agent}
        if (request_id := current_request_id()) is not None:
            headers["X-Request-ID"] = request_id
        if (correlation_id := current_correlation_id()) is not None:
            headers["X-Correlation-ID"] = correlation_id
        if deadline is not None:
            headers["X-Deadline"] = deadline_header(deadline)
        if (authorization := await self._tokens.authorization()) is not None:
            headers["Authorization"] = authorization
        return headers

    def _remaining(self, deadline: datetime) -> float:
        return (deadline - self._clock.now()).total_seconds()

    def _backoff(self, attempt: int, retry_after: int | None) -> float:
        base = self._settings.agent_retry_base_seconds
        delay = base * 2.0 ** (attempt - 1) + self._jitter() * base
        return max(delay, float(retry_after or 0))

    def _error_from_last(
        self, attempts: list[AttemptRecord], failure: AgentFailure, detail: str
    ) -> AgentCallError:
        return AgentCallError(failure, detail, attempts=tuple(attempts))

    async def _cancel_after_interrupt(self, run_id: UUID) -> None:
        # Our caller was cancelled (job cancelled or shutdown): tell the Agent to stop.
        with contextlib.suppress(Exception):
            await asyncio.shield(self.cancel(run_id))
