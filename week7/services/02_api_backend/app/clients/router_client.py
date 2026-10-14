"""Client for the AI Router (CONTRACT.md §2), adapted from the Travel Safety AgentClient.

- One deadline for the whole call (45s, CONTRACT §0); retries only spend what is left.
- Retries: connect errors and 502/503 once, with a short backoff. A router timeout is
  not retried: its own budget is 40s, so a second try cannot fit.
- Circuit breaker: repeated failures stop calls for a while (502 ROUTER_UNAVAILABLE).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx
from pydantic import ValidationError

from app.clients.circuit_breaker import CircuitBreaker
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.schemas.chat import RouteRequest, RouteResponse

log = get_logger(__name__)

ROUTE_PATH = "/route"
_RETRYABLE_STATUS = frozenset({502, 503})
_BACKOFF_SECONDS = 0.5


class _Retryable(Exception):
    pass


class RouterClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        breaker: CircuitBreaker,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}{ROUTE_PATH}"
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._breaker = breaker
        self._sleep = sleep

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def route(self, request: RouteRequest) -> RouteResponse:
        deadline = time.monotonic() + self._timeout
        for attempt in range(self._max_retries + 1):
            if not self._breaker.allow():
                raise AppError(
                    ErrorCode.ROUTER_UNAVAILABLE,
                    retry_after=self._breaker.retry_after(),
                    log_context={"router_failure": "circuit_open"},
                )
            try:
                response = await self._call(request, deadline)
            except _Retryable as exc:
                self._breaker.record_failure()
                remaining = deadline - time.monotonic()
                if attempt < self._max_retries and remaining > _BACKOFF_SECONDS + 1:
                    log.info("router_retry", attempt=attempt + 1, reason=str(exc))
                    await self._sleep(_BACKOFF_SECONDS)
                    continue
                raise AppError(
                    ErrorCode.ROUTER_UNAVAILABLE, log_context={"router_failure": str(exc)}
                ) from exc
            except AppError:
                self._breaker.record_failure()
                raise
            self._breaker.record_success()
            return response
        raise AssertionError("unreachable")

    async def _call(self, request: RouteRequest, deadline: float) -> RouteResponse:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AppError(ErrorCode.ROUTER_TIMEOUT)
        try:
            # httpx timeouts are per phase; asyncio.timeout bounds the whole call.
            async with asyncio.timeout(remaining):
                response = await self._http.post(
                    self._url,
                    content=request.model_dump_json(),
                    headers={
                        "Content-Type": "application/json",
                        "X-Request-ID": request.request_id,
                    },
                    timeout=remaining,
                )
        except TimeoutError as exc:
            raise AppError(
                ErrorCode.ROUTER_TIMEOUT, log_context={"router_failure": "timeout"}
            ) from exc
        except httpx.TimeoutException as exc:
            if isinstance(exc, httpx.ConnectTimeout):
                raise _Retryable("connect_timeout") from exc
            raise AppError(
                ErrorCode.ROUTER_TIMEOUT, log_context={"router_failure": "timeout"}
            ) from exc
        except httpx.TransportError as exc:
            raise _Retryable(type(exc).__name__) from exc

        if response.status_code in _RETRYABLE_STATUS:
            raise _Retryable(f"status_{response.status_code}")
        if response.status_code == 504:
            raise AppError(ErrorCode.ROUTER_TIMEOUT, log_context={"router_status": 504})
        if response.status_code != 200:
            raise AppError(
                ErrorCode.ROUTER_UNAVAILABLE, log_context={"router_status": response.status_code}
            )
        try:
            return RouteResponse.model_validate_json(response.content)
        except ValidationError as exc:
            log.warning("router_bad_response", errors=exc.error_count())
            raise AppError(
                ErrorCode.ROUTER_UNAVAILABLE, log_context={"router_failure": "bad_response"}
            ) from exc
