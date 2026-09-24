from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.retention import expires_at


def test_expires_after_the_retention_period() -> None:
    start = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)

    assert expires_at(start, 30) == datetime(2026, 10, 17, 8, 0, tzinfo=UTC)


def test_retention_must_be_positive() -> None:
    with pytest.raises(ValueError, match="days"):
        expires_at(datetime(2026, 9, 17, tzinfo=UTC), 0)
