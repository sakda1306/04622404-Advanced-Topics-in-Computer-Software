"""Times in Asia/Bangkok (+07:00) as CONTRACT §0 requires."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")


def bangkok_now() -> datetime:
    return datetime.now(BANGKOK)


def version_stamp(moment: datetime) -> str:
    """`index_version`: ISO-8601 in +07:00, to the millisecond so two quick updates differ."""
    return moment.astimezone(BANGKOK).isoformat(timespec="milliseconds")
