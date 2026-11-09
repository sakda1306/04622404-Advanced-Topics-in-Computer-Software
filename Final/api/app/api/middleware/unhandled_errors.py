"""Turn unexpected exceptions into a Problem-JSON 500 inside the middleware stack.

Starlette answers `Exception` handlers from its outermost layer, outside CORS and the
security headers, so the browser could not read the body or X-Request-ID. This
middleware is added first (innermost), so its 500 still passes through CORS, the
security headers and the request id middleware.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware.problem_asgi import send_problem
from app.core.errors import ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp, *, type_base_url: str) -> None:
        self.app = app
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            log.exception("unhandled_exception", error_type=type(exc).__name__)
            if response_started:
                raise
            await send_problem(send, ErrorCode.INTERNAL_ERROR, self.type_base_url)
