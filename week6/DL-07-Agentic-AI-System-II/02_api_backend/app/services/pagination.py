"""Keyset pagination with an opaque cursor (docs/02_api_spec.md section 1).

The cursor is base64url of {"t": <timestamp>, "id": <uuid>} of the last item on the
page (a number instead of a uuid for audit log rows). It is not encrypted, so it is
validated strictly when it comes back.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.errors import AppError, ErrorCode, FieldError

MAX_CURSOR_LENGTH = 200


@dataclass(frozen=True, slots=True)
class Cursor:
    at: datetime
    id: UUID | int


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


def _invalid(field: str, message: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        errors=[FieldError(field=field, message=message, code="invalid")],
    )


def encode_cursor(cursor: Cursor) -> str:
    data = json.dumps({"t": cursor.at.isoformat(), "id": str(cursor.id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")


def decode_cursor(raw: str | None, *, numeric_id: bool = False) -> Cursor | None:
    if not raw:
        return None
    if len(raw) > MAX_CURSOR_LENGTH:
        raise _invalid("cursor", "the cursor is not valid")
    try:
        padded = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        at = datetime.fromisoformat(data["t"])
        cursor_id: UUID | int = int(data["id"]) if numeric_id else UUID(data["id"])
    except (binascii.Error, ValueError, TypeError, KeyError, UnicodeDecodeError):
        raise _invalid("cursor", "the cursor is not valid") from None
    if at.tzinfo is None:
        raise _invalid("cursor", "the cursor is not valid")
    return Cursor(at, cursor_id)


def page_limit(limit: int | None, *, maximum: int, default: int = 20) -> int:
    if limit is None:
        return min(default, maximum)
    if not 1 <= limit <= maximum:
        raise _invalid("limit", f"must be between 1 and {maximum}")
    return limit


def build_page[T](rows: list[T], limit: int, key: Callable[[T], Cursor]) -> Page[T]:
    """`rows` holds up to limit + 1 items; the extra one only says another page exists."""
    items = rows[:limit]
    next_cursor = encode_cursor(key(items[-1])) if len(rows) > limit and items else None
    return Page(items, next_cursor)
