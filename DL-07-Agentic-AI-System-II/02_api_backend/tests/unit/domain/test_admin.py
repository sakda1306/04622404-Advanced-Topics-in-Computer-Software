from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.admin import AuditFilter, TimeRange, check_audit_filter, resolve_range
from app.domain.errors import InvalidInput

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def codes(exc: pytest.ExceptionInfo[InvalidInput]) -> list[tuple[str, str]]:
    return [(i.field, i.code) for i in exc.value.issues]


def test_default_range_ends_now() -> None:
    assert resolve_range(None, None, now=NOW, default=DAY, max_days=31) == TimeRange(NOW - DAY, NOW)


def test_missing_start_counts_back_from_the_end() -> None:
    end = NOW - 3 * DAY

    assert resolve_range(None, end, now=NOW, default=DAY, max_days=31).start == end - DAY


def test_start_must_be_before_end() -> None:
    with pytest.raises(InvalidInput) as exc:
        resolve_range(NOW, NOW, now=NOW, default=DAY, max_days=31)

    assert codes(exc) == [("from", "invalid_range")]


def test_range_is_bounded() -> None:
    with pytest.raises(InvalidInput) as exc:
        resolve_range(NOW - 32 * DAY, NOW, now=NOW, default=DAY, max_days=31)

    assert codes(exc) == [("from", "range_too_long")]
    assert resolve_range(NOW - 31 * DAY, NOW, now=NOW, default=DAY, max_days=31)


def test_times_need_a_timezone() -> None:
    naive = datetime(2026, 9, 1)  # no timezone on purpose

    with pytest.raises(InvalidInput) as exc:
        resolve_range(naive, naive, now=NOW, default=DAY, max_days=31)

    assert codes(exc) == [("from", "timezone_required"), ("to", "timezone_required")]


def test_audit_filter_accepts_known_shapes() -> None:
    value = AuditFilter(action="feedback.review", target_type="feedback", target_id="abc")

    assert check_audit_filter(value) is value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (AuditFilter(action="DROP TABLE"), [("action", "invalid")]),
        (AuditFilter(target_type="Feed-back"), [("target_type", "invalid")]),
        (AuditFilter(target_type="feedback", target_id="x" * 129), [("target_id", "invalid")]),
        (AuditFilter(target_id="abc"), [("target_type", "required")]),
    ],
)
def test_audit_filter_rejects_bad_values(
    value: AuditFilter, expected: list[tuple[str, str]]
) -> None:
    with pytest.raises(InvalidInput) as exc:
        check_audit_filter(value)

    assert codes(exc) == expected
