from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import InvalidInput
from app.domain.follow_up import PreferenceOverrides, RequestOverrides, merge_overrides
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences

BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")
LAMPANG = GeoPoint(18.29, 99.49, name="Lampang")
T1 = datetime(2026, 9, 20, 1, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)

BASE = NormalizedTravelRequest(
    origin=BANGKOK,
    destination=CHIANG_MAI,
    waypoints=(LAMPANG,),
    departure_time=T1,
    timezone="Asia/Bangkok",
    language="th",
    preferences=TravelPreferences(
        travel_modes=(TravelMode.TRAIN,),
        avoid=(AvoidOption.TOLLS,),
        max_travel_hours=12,
        mobility_needs=(MobilityNeed.ELDERLY,),
        traveler_count=2,
    ),
    question="Is it safe?",
)


def test_only_the_given_field_changes() -> None:
    result = merge_overrides(
        BASE,
        RequestOverrides(departure_time=T2),
        question="What about 3 hours later?",
        accept_language="en",
        default_language="en",
    )

    assert result.departure_time == T2
    assert result.origin == BANGKOK
    assert result.destination == CHIANG_MAI
    assert tuple(result.waypoints) == (LAMPANG,)
    assert result.timezone == "Asia/Bangkok"
    assert result.language == "th"
    assert result.accept_language == "en"
    assert result.preferences == BASE.preferences
    assert result.question == "What about 3 hours later?"
    assert BASE.departure_time == T1


def test_preferences_are_merged_per_key() -> None:
    result = merge_overrides(
        BASE,
        RequestOverrides(preferences=PreferenceOverrides(avoid=(), traveler_count=4)),
        question=None,
        accept_language=None,
        default_language="en",
    )

    assert result.preferences == TravelPreferences(
        travel_modes=(TravelMode.TRAIN,),
        avoid=(),
        max_travel_hours=12,
        mobility_needs=(MobilityNeed.ELDERLY,),
        traveler_count=4,
    )
    assert result.question is None


def test_route_fields_can_be_replaced_or_cleared() -> None:
    result = merge_overrides(
        BASE,
        RequestOverrides(destination=LAMPANG, waypoints=(), language="en", timezone="UTC"),
        question=None,
        accept_language=None,
        default_language="th",
    )

    assert result.destination == LAMPANG
    assert tuple(result.waypoints) == ()
    assert result.language == "en"
    assert result.timezone == "UTC"


def test_first_message_needs_a_complete_trip() -> None:
    complete = RequestOverrides(
        origin=BANGKOK, destination=CHIANG_MAI, departure_time=T1, timezone="Asia/Bangkok"
    )

    result = merge_overrides(
        None, complete, question="Safe?", accept_language="th", default_language="en"
    )

    assert result.origin == BANGKOK
    assert tuple(result.waypoints) == ()
    assert result.language == "en"
    assert result.preferences == TravelPreferences()


def test_first_message_with_partial_trip_is_rejected() -> None:
    with pytest.raises(InvalidInput) as info:
        merge_overrides(
            None,
            RequestOverrides(destination=CHIANG_MAI, departure_time=T1),
            question="Safe?",
            accept_language=None,
            default_language="en",
        )

    issue = info.value.issues[0]
    assert (issue.field, issue.code) == ("overrides", "travel_context_required")
    assert "origin" in issue.message
    assert "timezone" in issue.message
    assert "destination" not in issue.message
