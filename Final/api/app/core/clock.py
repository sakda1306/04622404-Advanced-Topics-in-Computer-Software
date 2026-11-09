"""Times in Asia/Bangkok (+07:00) as Contract.md §1 requires."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_bangkok(value: datetime) -> datetime:
    """SQLite drops the offset, so naive values from the database are read as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BANGKOK)


def iso(value: datetime) -> str:
    return to_bangkok(value).isoformat(timespec="seconds")
