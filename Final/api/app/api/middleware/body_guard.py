"""Reject oversized bodies (413) and wrong content types (415) before routing.

JSON everywhere, except the CV upload, which is multipart and may be up to 5 MB
(Contract.md §1, §2.2).
"""

from __future__ import annotations

import re

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware.problem_asgi import send_problem
from app.core.errors import ErrorCode

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MULTIPART_PATHS = frozenset({"/api/cv"})
# Room for the multipart boundaries and part headers around the file itself.
_MULTIPART_OVERHEAD = 64 * 1024
_JSON_ESCAPE = re.compile(rb"\\(?:u([0-9a-fA-F]{4})|.)", re.DOTALL)


class _UnstorableText(Exception):
    """Raised from `receive`, and handled the same way as `_BodyTooLarge`."""


class _BodyTooLarge(Exception):
    """Raised from `receive`. FastAPI may turn it into a 400 while parsing the body, so
    the middleware also remembers the overflow and replaces whatever response follows."""


def _has_unstorable_text(body: bytes) -> bool:
    """NUL or half a surrogate pair in a JSON string: valid JSON that the database refuses."""
    if b"\\u" not in body:
        return False
    high_ended_at: int | None = None
    for found in _JSON_ESCAPE.finditer(body):
        code = int(found[1], 16) if found[1] else None
        is_low = code is not None and 0xDC00 <= code <= 0xDFFF
        if high_ended_at is not None:
            if found.start() != high_ended_at or not is_low:
                return True
            high_ended_at = None
        elif code == 0 or is_low:
            return True
        elif code is not None and 0xD800 <= code <= 0xDBFF:
            high_ended_at = found.end()
    return high_ended_at is not None


def _url_has_nul(scope: Scope) -> bool:
    return "\x00" in scope.get("path", "") or b"%00" in scope.get("query_string", b"")


def _media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _is_json(media_type: str) -> bool:
    return media_type == "application/json" or (
        media_type.startswith("application/") and media_type.endswith("+json")
    )


class BodyGuardMiddleware:
    def __init__(
        self, app: ASGIApp, *, max_json_bytes: int, max_upload_bytes: int, type_base_url: str
    ) -> None:
        self.app = app
        self.max_json_bytes = max_json_bytes
        self.max_upload_bytes = max_upload_bytes + _MULTIPART_OVERHEAD
        self.type_base_url = type_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _url_has_nul(scope):
            await send_problem(send, ErrorCode.VALIDATION_ERROR, self.type_base_url)
            return
        if scope["type"] != "http" or scope["method"] not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        is_upload = scope.get("path", "") in MULTIPART_PATHS
        limit = self.max_upload_bytes if is_upload else self.max_json_bytes
        too_large = ErrorCode.CV_TOO_LARGE if is_upload else ErrorCode.PAYLOAD_TOO_LARGE

        declared = headers.get("content-length")
        if declared is not None:
            if not (declared.isascii() and declared.isdigit()):  # "²".isdigit() is True
                await send_problem(send, ErrorCode.VALIDATION_ERROR, self.type_base_url)
                return
            if int(declared) > limit:
                await send_problem(send, too_large, self.type_base_url)
                return
        has_body = (declared is not None and int(declared) > 0) or "transfer-encoding" in headers
        media_type = _media_type(headers.get("content-type", ""))
        allowed = media_type == "multipart/form-data" if is_upload else _is_json(media_type)
        if has_body and not allowed:
            await send_problem(send, ErrorCode.UNSUPPORTED_MEDIA_TYPE, self.type_base_url)
            return

        # Content-Length can be absent (chunked) or wrong, so also count what arrives.
        received = 0
        body = bytearray()
        refused: ErrorCode | None = None
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    refused = too_large
                    raise _BodyTooLarge
                if not is_upload:
                    body.extend(message.get("body", b""))
                    if not message.get("more_body") and _has_unstorable_text(bytes(body)):
                        refused = ErrorCode.VALIDATION_ERROR
                        raise _UnstorableText
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if refused is not None:
                # The app answered after the refusal (e.g. a 400 from body parsing):
                # send our problem instead and drop the app's messages.
                if not response_started:
                    response_started = True
                    await send_problem(send, refused, self.type_base_url)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except (_BodyTooLarge, _UnstorableText):
            if not response_started and refused is not None:
                await send_problem(send, refused, self.type_base_url)
