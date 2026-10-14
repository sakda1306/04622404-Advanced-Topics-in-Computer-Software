"""Id helpers and the request id carried through every hop (CONTRACT.md §0)."""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from contextvars import ContextVar

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


_lock = threading.Lock()
_last_ms = 0
_seq = 0


def new_id() -> uuid.UUID:
    """UUIDv7 (RFC 9562): sorts by creation time, also within one millisecond.

    Keyset pages order by (created_at, id); time-ordered ids keep rows written in the
    same instant in the order they were written.
    """
    global _last_ms, _seq
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:
            ms = _last_ms
            _seq += 1
            if _seq > 0xFFF:  # 4096 ids in one millisecond: borrow the next one
                ms += 1
                _seq = 0
        else:
            _seq = 0
        _last_ms = ms
        seq = _seq
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms << 80) | (0x7 << 76) | (seq << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def accept_client_id(value: str | None) -> str | None:
    """Return a client-supplied id only when it is short and log-safe."""
    if value and _SAFE_ID.fullmatch(value):
        return value
    return None


def current_request_id() -> str:
    """The id of the request being served, or a fresh one outside a request (workers)."""
    return request_id_var.get() or str(new_id())
