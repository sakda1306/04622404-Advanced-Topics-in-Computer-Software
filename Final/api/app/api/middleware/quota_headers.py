"""X-Quota-* headers on every response to an authenticated request (Contract.md §1).

`current_user` puts the user id on the request state; this middleware reads today's usage
when the response starts, so the values include any LLM call made by the handler.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.clock import iso
from app.core.logging import get_logger
from app.services.quota_service import get_quota

log = get_logger(__name__)


class QuotaHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_quota(message: Message) -> None:
            if message["type"] == "http.response.start":
                user_id = scope.get("state", {}).get("quota_user_id")
                if user_id:
                    await _add_headers(scope, message, user_id)
            await send(message)

        await self.app(scope, receive, send_with_quota)


async def _add_headers(scope: Scope, message: Message, user_id: str) -> None:
    container = scope["app"].state.container
    try:
        async with container.sessions() as db:
            status = await get_quota(db, user_id, container.settings)
    except Exception:  # headers are a convenience; never fail the response for them
        log.warning("quota_headers_failed", exc_info=True)
        return
    headers = MutableHeaders(scope=message)
    headers["X-Quota-Requests-Remaining"] = str(status.requests_remaining)
    headers["X-Quota-Tokens-Remaining"] = str(status.tokens_remaining)
    headers["X-Quota-Reset"] = iso(status.reset_at)
