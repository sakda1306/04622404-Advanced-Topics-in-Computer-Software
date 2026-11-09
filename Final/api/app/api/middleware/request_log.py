"""One `request_log` row per API request, for the admin dashboard (Design.md §2, §4.8).

Stores the path template, never the real path, query string or body. Runs just inside
RequestContextMiddleware, so it also sees requests rejected before routing.
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.problem import PROBLEM_MEDIA_TYPE
from app.core.ids import request_id_var
from app.core.logging import get_logger
from app.infra.models import RequestLog

log = get_logger(__name__)

UNMATCHED_ROUTE = "(unmatched)"
_SKIPPED_PATHS = frozenset({"/api/health"})  # the compose healthcheck would flood the dashboard


def _problem_code(body: bytes) -> str | None:
    try:
        code = json.loads(body).get("code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) else None


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not path.startswith("/api/")
            or path in _SKIPPED_PATHS
            or scope.get("method") == "OPTIONS"
        ):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        is_problem = False
        problem_body = b""

        async def recording_send(message: Message) -> None:
            nonlocal status, is_problem, problem_body
            if message["type"] == "http.response.start":
                status = message["status"]
                content_type = Headers(raw=message["headers"]).get("content-type", "")
                is_problem = content_type.startswith(PROBLEM_MEDIA_TYPE)
            elif message["type"] == "http.response.body" and is_problem:
                problem_body += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:
            route = scope.get("route")
            await _write(
                scope,
                method=scope.get("method", ""),
                route=getattr(route, "path", UNMATCHED_ROUTE),
                status=status,
                code=_problem_code(problem_body) if is_problem else None,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )


async def _write(scope: Scope, **fields: Any) -> None:
    sessions = scope["app"].state.container.sessions
    user_id = scope.get("state", {}).get("quota_user_id")
    request_id = request_id_var.get() or ""
    try:
        try:
            async with sessions() as db:
                db.add(RequestLog(request_id=request_id, user_id=user_id, **fields))
                await db.commit()
        except IntegrityError:
            # DELETE /api/me: the user is gone by now, so keep the row without the link.
            async with sessions() as db:
                db.add(RequestLog(request_id=request_id, user_id=None, **fields))
                await db.commit()
    except Exception as problem:  # the dashboard must never cost the user their response
        log.warning("request_log_failed", error_type=type(problem).__name__)
