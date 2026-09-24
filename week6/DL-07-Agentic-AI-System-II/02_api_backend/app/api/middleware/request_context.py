"""Request id / correlation id, access log, HTTP metrics and last-resort error handling.

This is the outermost application middleware, so every response (including CORS
preflight and unexpected 500s) carries X-Request-ID and X-Correlation-ID.
"""

from __future__ import annotations

import time

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware.problem_asgi import send_problem
from app.core.errors import ErrorCode
from app.core.ids import accept_client_id, correlation_id_var, new_id, request_id_var
from app.core.logging import get_logger
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.core.telemetry import tag_correlation

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

log = get_logger("app.access")

# Probes are called constantly; logging them only adds noise.
_QUIET_PATHS = frozenset({"/health", "/ready", "/metrics"})
# Label for requests no route matched: raw paths would make unbounded label values.
UNMATCHED_ROUTE = "unmatched"
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def route_label(scope: Scope) -> str:
    """The route template (`/v1/jobs/{job_id}`), never the concrete path.

    FastAPI records the matched route without the prefixes of the routers it was
    included from, so the literal prefix is taken from the front of the real path.
    """
    template = getattr(scope.get("route"), "path", None)
    if not isinstance(template, str):
        return UNMATCHED_ROUTE
    parts = [p for p in str(scope.get("path", "")).split("/") if p]
    template_parts = [p for p in template.split("/") if p]
    if len(template_parts) > len(parts):
        return UNMATCHED_ROUTE
    prefix = parts[: len(parts) - len(template_parts)]
    return "/" + "/".join([*prefix, *template_parts])


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, type_base_url: str) -> None:
        self.app = app
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = accept_client_id(headers.get(REQUEST_ID_HEADER)) or str(new_id())
        correlation_id = accept_client_id(headers.get(CORRELATION_ID_HEADER)) or request_id
        request_id_var.set(request_id)
        correlation_id_var.set(correlation_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, correlation_id=correlation_id)
        tag_correlation(correlation_id)

        path: str = scope.get("path", "")
        method: str = scope.get("method", "WS")
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_ids(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                out = MutableHeaders(scope=message)
                out[REQUEST_ID_HEADER] = request_id
                out[CORRELATION_ID_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_ids)
        except Exception as exc:
            log.exception("unhandled_exception", error_type=type(exc).__name__)
            if scope["type"] != "http" or response_started:
                raise
            await send_problem(
                send,
                ErrorCode.INTERNAL_ERROR,
                path,
                self.type_base_url,
                {REQUEST_ID_HEADER: request_id, CORRELATION_ID_HEADER: correlation_id},
            )
            status_code = 500
        finally:
            elapsed = time.perf_counter() - started
            if scope["type"] == "http":
                route = route_label(scope)
                verb = method if method in _KNOWN_METHODS else "OTHER"
                HTTP_REQUESTS.labels(route=route, method=verb, status=str(status_code)).inc()
                HTTP_DURATION.labels(route=route, method=verb).observe(elapsed)
            if path not in _QUIET_PATHS:
                log.info(
                    "http_request",
                    method=method,
                    path=path,  # query strings are never logged
                    status=status_code,
                    duration_ms=round(elapsed * 1000, 2),
                )
