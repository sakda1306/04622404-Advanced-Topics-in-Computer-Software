"""Retention periods (docs/03_data_design.md section 6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def expires_at(start: datetime, days: int) -> datetime:
    if days <= 0:
        raise ValueError("retention days must be positive")
    return start + timedelta(days=days)


def month_start(moment: datetime) -> datetime:
    """First instant of the UTC month (audit partitions are monthly, D-85)."""
    utc = moment.astimezone(UTC)
    return datetime(utc.year, utc.month, 1, tzinfo=UTC)


def add_months(start: datetime, months: int) -> datetime:
    index = start.year * 12 + start.month - 1 + months
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=UTC)


def partition_name(start: datetime) -> str:
    return f"audit_logs_y{start.year:04d}m{start.month:02d}"
