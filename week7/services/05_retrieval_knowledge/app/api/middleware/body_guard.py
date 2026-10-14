"""Reject oversized bodies (413) and non-JSON bodies (415) before routing.

`/search` is limited to 64 KB; `/index/upsert` carries whole documents from 07 and gets 5 MB.
"""

from __future__ import annotations

from collections.abc import Mapping

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware.problem_asgi import send_problem
from app.core.errors import ErrorCode

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class _BodyTooLarge(HTTPException):
    # FastAPI re-raises HTTPException from body reading; the handlers map it to 413.
    def __init__(self) -> None:
        super().__init__(status_code=413)


def _is_json(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or (
        media_type.startswith("application/") and media_type.endswith("+json")
    )


class BodyGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        large_paths: Mapping[str, int],
        type_base_url: str,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.large_paths = dict(large_paths)
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        limit = self.large_paths.get(scope.get("path", ""), self.max_body_bytes)
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None:
            if not declared.isdigit():
                await send_problem(send, ErrorCode.INVALID_REQUEST, self.type_base_url)
                return
            if int(declared) > limit:
                await send_problem(send, ErrorCode.PAYLOAD_TOO_LARGE, self.type_base_url)
                return
        has_body = (declared is not None and int(declared) > 0) or "transfer-encoding" in headers
        if has_body and not _is_json(headers.get("content-type", "")):
            await send_problem(send, ErrorCode.UNSUPPORTED_MEDIA_TYPE, self.type_base_url)
            return

        # Content-Length can be absent (chunked) or wrong, so also count what arrives.
        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await send_problem(send, ErrorCode.PAYLOAD_TOO_LARGE, self.type_base_url)
