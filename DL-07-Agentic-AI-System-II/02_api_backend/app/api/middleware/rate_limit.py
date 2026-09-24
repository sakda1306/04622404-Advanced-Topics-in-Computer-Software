"""Per-IP rate limit (P-31), applied before authentication.

Per-user and per-endpoint limits need the verified caller and live in app/api/auth.py.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.auth import enforce_rate_limit
from app.api.middleware.problem_asgi import send_problem
from app.api.resources import get_resources
from app.core.crypto import keyed_hash
from app.core.errors import AppError

_EXEMPT_PATHS = frozenset({"/health", "/ready", "/metrics"})


class IPRateLimitMiddleware:
    def __init__(self, app: ASGIApp, *, type_base_url: str) -> None:
        self.app = app
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in _EXEMPT_PATHS or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        conn = HTTPConnection(scope)
        resources = get_resources(conn)
        # scope["client"] already reflects X-Forwarded-For from trusted proxies only.
        client_ip = conn.client.host if conn.client else "unknown"
        subject = keyed_hash(resources.settings.secrets.ip_hash_secret, client_ip)
        try:
            await enforce_rate_limit(
                resources, "ip", subject, resources.settings.limits.rate_limit_ip
            )
        except AppError as exc:
            headers = dict(exc.headers)
            if exc.retry_after is not None:
                headers["Retry-After"] = str(exc.retry_after)
            await send_problem(send, exc.code, path, self.type_base_url, headers)
            return
        await self.app(scope, receive, send)
