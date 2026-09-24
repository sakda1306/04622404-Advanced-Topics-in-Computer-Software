"""Rules for admin queries (docs/02_api_spec.md section 8.2). Pure functions, no I/O.

Every admin listing reads one bounded time range, so a query can never scan whole
tables (P-67); training exports have their own, longer limit (P-69).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.errors import FieldIssue, InvalidInput

_ACTION = re.compile(r"^[a-z0-9_.]{1,64}$")
_TARGET_TYPE = re.compile(r"^[a-z0-9_]{1,32}$")
TARGET_ID_MAX = 128


@dataclass(frozen=True, slots=True)
class TimeRange:
    start: datetime
    end: datetime


def resolve_range(
    start: datetime | None,
    end: datetime | None,
    *,
    now: datetime,
    default: timedelta,
    max_days: int,
) -> TimeRange:
    """`[from, to)`; missing ends default to `to = now`, `from = to - default`."""
    issues: list[FieldIssue] = []
    for name, value in (("from", start), ("to", end)):
        if value is not None and value.tzinfo is None:
            issues.append(FieldIssue(name, "timezone_required", "must include a timezone"))
    if issues:
        raise InvalidInput(issues)
    stop = end or now
    begin = start or stop - default
    if begin >= stop:
        raise InvalidInput([FieldIssue("from", "invalid_range", "must be earlier than 'to'")])
    if stop - begin > timedelta(days=max_days):
        raise InvalidInput(
            [FieldIssue("from", "range_too_long", f"the range can be at most {max_days} days")]
        )
    return TimeRange(begin, stop)


@dataclass(frozen=True, slots=True)
class AuditFilter:
    action: str | None = None
    actor_type: str | None = None
    result: str | None = None
    target_type: str | None = None
    target_id: str | None = None


def check_audit_filter(value: AuditFilter) -> AuditFilter:
    issues: list[FieldIssue] = []
    if value.action is not None and not _ACTION.match(value.action):
        issues.append(FieldIssue("action", "invalid", "letters, digits, '.' and '_' only"))
    if value.target_type is not None and not _TARGET_TYPE.match(value.target_type):
        issues.append(FieldIssue("target_type", "invalid", "letters, digits and '_' only"))
    if value.target_id is not None and not 1 <= len(value.target_id) <= TARGET_ID_MAX:
        issues.append(
            FieldIssue("target_id", "invalid", f"must be 1 to {TARGET_ID_MAX} characters")
        )
    if value.target_id is not None and value.target_type is None:
        issues.append(FieldIssue("target_type", "required", "required with 'target_id'"))
    if issues:
        raise InvalidInput(issues)
    return value
