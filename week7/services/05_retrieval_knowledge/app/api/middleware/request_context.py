"""X-Request-ID on every request and response, access log, last-resort 500.

This is the outermost middleware, so every response (CORS preflight and unexpected
errors included) carries X-Request-ID.
"""

from __future__ import annotations

import time

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware.problem_asgi import send_problem
from app.core.errors import ErrorCode
from app.core.ids import accept_client_id, new_id, request_id_var
from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

log = get_logger("app.access")

_QUIET_PATHS = frozenset({"/health", "/ready"})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, type_base_url: str) -> None:
        self.app = app
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = accept_client_id(headers.get(REQUEST_ID_HEADER)) or str(new_id())
        request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            log.exception("unhandled_exception", error_type=type(exc).__name__)
            if response_started:
                raise
            await send_problem(
                send, ErrorCode.INTERNAL_ERROR, self.type_base_url, {REQUEST_ID_HEADER: request_id}
            )
            status_code = 500
        finally:
            if path not in _QUIET_PATHS:
                log.info(
                    "http_request",
                    method=method,
                    path=path,  # query strings are never logged
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            structlog.contextvars.unbind_contextvars("request_id", "user_id")
