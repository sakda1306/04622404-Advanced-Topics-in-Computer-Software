"""Opaque keyset cursors: (created_at, id) of the last item on the page."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import AppError, ErrorCode, FieldError


def encode_cursor(created_at: datetime, item_id: Any) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    raw = json.dumps({"t": created_at.astimezone(UTC).isoformat(), "id": str(item_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        created_at = datetime.fromisoformat(data["t"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        # Also rejects times that fall outside the datetime range once moved to UTC.
        return created_at.astimezone(UTC), str(data["id"])
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            errors=[FieldError("cursor", "invalid cursor", "invalid")],
        ) from exc


def before_cursor(
    cursor: str | None,
    created_col: InstrumentedAttribute[Any],
    id_col: InstrumentedAttribute[Any],
    id_type: type = str,
) -> Any:
    """Filter for rows after the cursor when ordering by (created_at desc, id desc)."""
    if not cursor:
        return None
    created_at, raw_id = decode_cursor(cursor)
    try:
        item_id = id_type(raw_id)
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            errors=[FieldError("cursor", "invalid cursor", "invalid")],
        ) from exc
    return or_(created_col < created_at, and_(created_col == created_at, id_col < item_id))
