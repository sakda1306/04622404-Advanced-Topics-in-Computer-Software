from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.cache_policy import (
    cache_key,
    cache_ttl_seconds,
    departure_bucket,
    request_is_cacheable,
    result_is_cacheable,
)
from app.domain.enums import RecommendationStatus, RiskLevel, TravelMode
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


def request(**changes: Any) -> NormalizedTravelRequest:
    base = NormalizedTravelRequest(
        origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
        destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
        waypoints=(),
        departure_time=datetime(2026, 9, 20, 1, 7, tzinfo=UTC),
        timezone="Asia/Bangkok",
        language="th",
        preferences=TravelPreferences(travel_modes=(TravelMode.TRAIN,)),
        question=None,
    )
    return replace(base, **changes)


def test_departure_bucket_rounds_down() -> None:
    assert departure_bucket(datetime(2026, 9, 20, 1, 29, 59, tzinfo=UTC), 15) == datetime(
        2026, 9, 20, 1, 15, tzinfo=UTC
    )


def test_key_ignores_details_inside_the_same_cell_and_bucket() -> None:
    near = request(
        origin=GeoPoint(13.75631, 100.50181, name="Other name"),
        departure_time=datetime(2026, 9, 20, 1, 14, tzinfo=UTC),
    )

    assert cache_key(near, bucket_minutes=15) == cache_key(request(), bucket_minutes=15)
    assert len(cache_key(request(), bucket_minutes=15)) == 64


@pytest.mark.parametrize(
    "changes",
    [
        {"language": "en"},
        {"departure_time": datetime(2026, 9, 20, 1, 16, tzinfo=UTC)},
        {"destination": GeoPoint(18.9, 98.9853)},
        {"waypoints": (GeoPoint(16.0, 99.5),)},
        {"preferences": TravelPreferences(travel_modes=(TravelMode.BUS,))},
        {"preferences": TravelPreferences(travel_modes=(TravelMode.TRAIN,), traveler_count=4)},
    ],
)
def test_key_changes_with_inputs_that_change_the_advice(changes: dict[str, Any]) -> None:
    assert cache_key(request(**changes), bucket_minutes=15) != cache_key(
        request(), bucket_minutes=15
    )


def test_personal_context_is_never_cached() -> None:
    assert request_is_cacheable(request(), has_conversation=False)
    assert not request_is_cacheable(request(question="ปลอดภัยไหม"), has_conversation=False)
    assert not request_is_cacheable(request(), has_conversation=True)


@pytest.mark.parametrize(
    ("status", "risk", "stale", "expected"),
    [
        (RecommendationStatus.COMPLETED, RiskLevel.LOW, False, True),
        (RecommendationStatus.COMPLETED, RiskLevel.MEDIUM, False, True),
        (RecommendationStatus.COMPLETED, RiskLevel.HIGH, False, False),
        (RecommendationStatus.PARTIAL_RESULT, RiskLevel.LOW, False, False),
        (RecommendationStatus.COMPLETED, RiskLevel.LOW, True, False),
    ],
)
def test_result_is_cacheable(
    status: RecommendationStatus, risk: RiskLevel, stale: bool, expected: bool
) -> None:
    assert result_is_cacheable(status=status, risk_level=risk, overall_is_stale=stale) is expected


@pytest.mark.parametrize(
    ("valid_until", "expected"),
    [
        (NOW + timedelta(hours=1), 300),
        (NOW + timedelta(seconds=90), 90),
        (NOW - timedelta(seconds=1), 0),
        (None, 0),
    ],
)
def test_cache_ttl(valid_until: datetime | None, expected: int) -> None:
    assert cache_ttl_seconds(now=NOW, valid_until=valid_until, max_seconds=300) == expected
