"""Request id carried through every hop (CONTRACT §0)."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def accept_client_id(value: str | None) -> str | None:
    """Return a client-supplied id only when it is short and log-safe."""
    if value and _SAFE_ID.fullmatch(value):
        return value
    return None


def current_request_id() -> str:
    """The id of the request being served, or a fresh one outside a request (scripts)."""
    return request_id_var.get() or str(new_id())
