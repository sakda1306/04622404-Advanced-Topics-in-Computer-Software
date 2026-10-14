"""Times in Asia/Bangkok (+07:00) as CONTRACT.md §0 requires."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")


def utcnow() -> datetime:
    return datetime.now(UTC)


def bangkok_now() -> datetime:
    return datetime.now(BANGKOK)


def to_bangkok(value: datetime | None) -> datetime | None:
    """SQLite drops the offset, so naive values from the database are read as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BANGKOK)


def iso(value: datetime | None) -> str | None:
    converted = to_bangkok(value)
    return converted.isoformat(timespec="seconds") if converted else None


def season_for(moment: datetime) -> str:
    """Premier League seasons start in August and are named by their starting year."""
    return str(moment.year if moment.month >= 8 else moment.year - 1)
