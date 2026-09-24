"""Defensive response headers for a JSON API."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The interactive docs load scripts and styles, so the strict CSP is not applied there.
_DOC_PATHS = ("/docs", "/openapi.json")
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope.get("path", "").startswith(_DOC_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
                # Responses carry personal travel data; keep them out of shared caches.
                headers.setdefault("Cache-Control", "no-store")
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", _API_CSP)
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
