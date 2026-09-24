"""Identifier helpers: UUIDv7 ids and request/correlation id handling."""

from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import UUID

import uuid6

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_id() -> UUID:
    """Time-ordered UUIDv7 (docs/02_api_spec.md section 1)."""
    value: UUID = uuid6.uuid7()
    return value


def accept_client_id(value: str | None) -> str | None:
    """Return a client-supplied id only when it is short and log-safe."""
    if value and _SAFE_ID.fullmatch(value):
        return value
    return None


def current_request_id() -> str | None:
    return request_id_var.get()


def current_correlation_id() -> str | None:
    return correlation_id_var.get()
