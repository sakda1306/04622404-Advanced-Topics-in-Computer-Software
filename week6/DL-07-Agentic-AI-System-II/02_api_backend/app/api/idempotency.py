"""Idempotency-Key handling for POST routes (docs/02_api_spec.md section 11.1).

Use it per router: `APIRouter(route_class=IdempotentRoute)`. Only successful (2xx)
responses are stored, so a client can retry the same key after an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute
from redis.exceptions import RedisError
from starlette.responses import StreamingResponse

from app.api.auth import authenticate, principal_key
from app.api.resources import AppResources, get_resources
from app.core.crypto import sha256_hex
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.infrastructure.redis.idempotency_store import BeginOutcome, StoredResponse

log = get_logger(__name__)

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
_VALID_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_REPLAYABLE_HEADERS = ("content-type", "location")
_METHODS = frozenset({"POST"})

Handler = Callable[[Request], Coroutine[Any, Any, Response]]


def request_fingerprint(method: str, path: str, body: bytes) -> str:
    """Hash of the request; JSON is canonicalized so key order does not matter."""
    try:
        canonical = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode()
    except (ValueError, UnicodeDecodeError):
        canonical = body
    return sha256_hex(method.upper().encode() + b"\n" + path.encode() + b"\n" + canonical)


def _read_key(request: Request) -> str:
    key = request.headers.get(HEADER)
    if key is None:
        raise AppError(ErrorCode.INVALID_REQUEST, detail=f"The {HEADER} header is required.")
    if not _VALID_KEY.fullmatch(key):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            detail=f"The {HEADER} header must be 8-128 letters, digits or . _ : -",
        )
    return key


def _replay(stored: StoredResponse) -> Response:
    headers = dict(stored.headers)
    headers[REPLAYED_HEADER] = "true"
    return Response(content=stored.body, status_code=stored.status_code, headers=headers)


class IdempotentRoute(APIRoute):
    def get_route_handler(self) -> Handler:
        original = super().get_route_handler()
        route_path = self.path

        async def handler(request: Request) -> Response:
            if request.method not in _METHODS:
                return await original(request)
            # Authenticate first: unauthenticated callers learn nothing about the request.
            principal = await authenticate(request)
            key = _read_key(request)
            resources = get_resources(request)
            settings = resources.settings.jobs
            store_key = resources.keys.idempotency(
                principal_key(resources, principal), request.method, route_path, key
            )
            fingerprint = request_fingerprint(
                request.method, request.url.path, await request.body()
            )
            try:
                begin = await resources.idempotency.begin(
                    store_key, fingerprint, lock_seconds=settings.idempotency_lock_seconds
                )
            except (RedisError, OSError) as exc:
                # Without the store a retry could run the operation twice: fail closed.
                log.warning("idempotency_unavailable", error_type=type(exc).__name__)
                raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=5) from exc

            if begin.outcome is BeginOutcome.CONFLICT:
                raise AppError(ErrorCode.IDEMPOTENCY_CONFLICT)
            if begin.outcome is BeginOutcome.IN_PROGRESS:
                raise AppError(ErrorCode.IDEMPOTENCY_IN_PROGRESS, retry_after=2)
            if begin.outcome is BeginOutcome.REPLAY:
                assert begin.response is not None
                return _replay(begin.response)

            try:
                response = await original(request)
            except BaseException:
                await _release(resources, store_key, begin.owner)
                raise

            if 200 <= response.status_code < 300 and not isinstance(response, StreamingResponse):
                stored = StoredResponse(
                    status_code=response.status_code,
                    headers={
                        name: value
                        for name in _REPLAYABLE_HEADERS
                        if (value := response.headers.get(name)) is not None
                    },
                    body=bytes(response.body),
                )
                try:
                    await resources.idempotency.complete(
                        store_key, begin.owner, stored, ttl_seconds=settings.idempotency_ttl_seconds
                    )
                except (RedisError, OSError) as exc:
                    # The work is done; the client still gets its response.
                    log.warning("idempotency_store_failed", error_type=type(exc).__name__)
            else:
                await _release(resources, store_key, begin.owner)
            return response

        return handler


async def _release(resources: AppResources, store_key: str, owner: str) -> None:
    try:
        await resources.idempotency.release(store_key, owner)
    except (RedisError, OSError) as exc:
        log.warning("idempotency_release_failed", error_type=type(exc).__name__)
