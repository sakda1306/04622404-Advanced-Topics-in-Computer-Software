from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.core.geo import haversine_m
from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import InvalidInput
from app.domain.normalization import (
    GeoPoint,
    NormalizationLimits,
    TravelPreferences,
    TravelRequestInput,
    negotiate_language,
    normalize_travel_request,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
LIMITS = NormalizationLimits()
BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")


def raw(**overrides: Any) -> TravelRequestInput:
    base = TravelRequestInput(
        origin=BANGKOK,
        destination=CHIANG_MAI,
        departure_time=datetime(2026, 9, 20, 1, 0, tzinfo=UTC),
        timezone="Asia/Bangkok",
    )
    return replace(base, **overrides)


def issues(inp: TravelRequestInput) -> dict[str, str]:
    with pytest.raises(InvalidInput) as info:
        normalize_travel_request(inp, now=NOW, limits=LIMITS)
    return {i.field: i.code for i in info.value.issues}


def test_haversine_bangkok_to_chiang_mai() -> None:
    assert haversine_m(13.7563, 100.5018, 18.7883, 98.9853) == pytest.approx(583_000, rel=0.01)
    assert haversine_m(1.0, 1.0, 1.0, 1.0) == 0.0


def test_valid_request_is_normalized() -> None:
    bangkok_time = datetime(2026, 9, 20, 8, 0, tzinfo=timezone(timedelta(hours=7)))

    result = normalize_travel_request(
        raw(
            origin=GeoPoint(13.75630049, 100.50180049, name="  Bangkok\x00 "),
            departure_time=bangkok_time,
            language="TH-th",
            question="  ปลอดภัยไหม​ ",
        ),
        now=NOW,
        limits=LIMITS,
    )

    assert result.origin == GeoPoint(13.7563, 100.5018, name="Bangkok")
    assert result.departure_time == datetime(2026, 9, 20, 1, 0, tzinfo=UTC)
    assert result.departure_time.tzinfo is UTC
    assert result.timezone == "Asia/Bangkok"
    assert result.language == "th"
    assert result.question == "ปลอดภัยไหม"


def test_blank_question_becomes_none() -> None:
    result = normalize_travel_request(raw(question="   "), now=NOW, limits=LIMITS)

    assert result.question is None


@pytest.mark.parametrize(
    ("point", "field"),
    [
        (GeoPoint(90.0001, 100.0), "origin.lat"),
        (GeoPoint(-91.0, 100.0), "origin.lat"),
        (GeoPoint(13.0, 180.5), "origin.lon"),
        (GeoPoint(float("nan"), 100.0), "origin.lat"),
    ],
)
def test_out_of_range_coordinates(point: GeoPoint, field: str) -> None:
    assert issues(raw(origin=point)) == {field: "out_of_range"}


def test_overlong_place_id_is_rejected() -> None:
    point = GeoPoint(13.7563, 100.5018, place_id="p" * 201)

    assert issues(raw(origin=point)) == {"origin.place_id": "too_long"}


def test_overlong_name_is_shortened() -> None:
    point = GeoPoint(13.7563, 100.5018, name="n" * 250, place_id="p" * 200)

    result = normalize_travel_request(raw(origin=point), now=NOW, limits=LIMITS)

    assert result.origin.name == "n" * 200
    assert result.origin.place_id == "p" * 200


def test_origin_and_destination_must_differ() -> None:
    near_bangkok = GeoPoint(13.7564, 100.5018)  # about 11 m away

    assert issues(raw(destination=near_bangkok)) == {"destination": "same_as_origin"}


def test_naive_departure_time_is_rejected() -> None:
    assert issues(raw(departure_time=datetime(2026, 9, 20, 1, 0))) == {
        "departure_time": "timezone_required"
    }


@pytest.mark.parametrize(
    ("when", "code"),
    [
        (NOW - timedelta(hours=1, minutes=1), "in_past"),
        (NOW + timedelta(days=14, minutes=1), "too_far_ahead"),
    ],
)
def test_departure_time_window(when: datetime, code: str) -> None:
    assert issues(raw(departure_time=when)) == {"departure_time": code}


@pytest.mark.parametrize("when", [NOW - timedelta(minutes=59), NOW + timedelta(days=14)])
def test_departure_time_window_edges_are_accepted(when: datetime) -> None:
    assert normalize_travel_request(raw(departure_time=when), now=NOW, limits=LIMITS)


# Windows ignores trailing spaces/dots in file names, so a file-based lookup would accept
# these; the check must behave the same on every OS.
@pytest.mark.parametrize(
    "name", ["Mars/Olympus", "../etc/passwd", "", "Asia/Bangkok ", "Asia/Bangkok.", "asia/bangkok"]
)
def test_unknown_timezone(name: str) -> None:
    assert issues(raw(timezone=name)) == {"timezone": "unknown_timezone"}


def test_question_length_limit() -> None:
    assert normalize_travel_request(raw(question="ก" * 1000), now=NOW, limits=LIMITS)
    assert issues(raw(question="ก" * 1001)) == {"question": "too_long"}


def test_too_many_waypoints() -> None:
    points = tuple(GeoPoint(14.0 + i, 100.0) for i in range(6))

    assert issues(raw(waypoints=points)) == {"waypoints": "too_many"}


def test_consecutive_duplicate_waypoints_are_merged() -> None:
    a = GeoPoint(15.0, 100.0)
    a_again = GeoPoint(15.00001, 100.0)
    b = GeoPoint(16.0, 100.0)

    result = normalize_travel_request(raw(waypoints=(a, a_again, b, a)), now=NOW, limits=LIMITS)

    assert result.waypoints == (a, b, a)


def test_invalid_waypoint_is_reported_with_its_index() -> None:
    points = (GeoPoint(15.0, 100.0), GeoPoint(15.0, 200.0))

    assert issues(raw(waypoints=points)) == {"waypoints.1.lon": "out_of_range"}


def test_preferences_are_deduplicated_and_sorted() -> None:
    prefs = TravelPreferences(
        travel_modes=(TravelMode.TRAIN, TravelMode.BUS, TravelMode.TRAIN),
        avoid=(AvoidOption.TOLLS, AvoidOption.FERRIES),
        mobility_needs=(MobilityNeed.WHEELCHAIR, MobilityNeed.WHEELCHAIR),
        max_travel_hours=12,
        traveler_count=2,
    )

    result = normalize_travel_request(raw(preferences=prefs), now=NOW, limits=LIMITS)

    assert result.preferences == TravelPreferences(
        travel_modes=(TravelMode.BUS, TravelMode.TRAIN),
        avoid=(AvoidOption.FERRIES, AvoidOption.TOLLS),
        mobility_needs=(MobilityNeed.WHEELCHAIR,),
        max_travel_hours=12,
        traveler_count=2,
    )


@pytest.mark.parametrize(
    ("prefs", "field"),
    [
        (TravelPreferences(max_travel_hours=0), "preferences.max_travel_hours"),
        (TravelPreferences(max_travel_hours=49), "preferences.max_travel_hours"),
        (TravelPreferences(traveler_count=0), "preferences.traveler_count"),
        (TravelPreferences(traveler_count=21), "preferences.traveler_count"),
    ],
)
def test_preference_ranges(prefs: TravelPreferences, field: str) -> None:
    assert issues(raw(preferences=prefs)) == {field: "out_of_range"}


def test_all_issues_are_reported_together() -> None:
    found = issues(
        raw(
            origin=GeoPoint(100.0, 0.0),
            timezone="Nowhere/City",
            question="x" * 1001,
            departure_time=datetime(2026, 9, 20),
        )
    )

    assert found == {
        "origin.lat": "out_of_range",
        "timezone": "unknown_timezone",
        "question": "too_long",
        "departure_time": "timezone_required",
    }


@pytest.mark.parametrize(
    ("explicit", "header", "expected"),
    [
        ("en", "th", "en"),
        ("EN-us", None, "en"),
        ("ja", "en-US,en;q=0.9", "en"),
        (None, "ja,en-US;q=0.8,th;q=0.9", "th"),
        (None, "en;q=0, th;q=0.1", "th"),
        (None, "fr, en;q=0", "th"),  # q=0 means "not acceptable"
        (None, "en;q=abc", "th"),
        (None, "fr, de", "th"),
        (None, "en;q=abc, th;q=0.2", "th"),
        (None, None, "th"),
        ("", "", "th"),
    ],
)
def test_negotiate_language(explicit: str | None, header: str | None, expected: str) -> None:
    assert negotiate_language(explicit, header) == expected


def test_language_falls_back_to_accept_language() -> None:
    result = normalize_travel_request(
        raw(language=None, accept_language="en-GB,en;q=0.8"), now=NOW, limits=LIMITS
    )

    assert result.language == "en"


def test_departure_window_can_be_skipped() -> None:
    past = raw(departure_time=NOW - timedelta(days=3))
    result = normalize_travel_request(past, now=NOW, limits=LIMITS, check_departure_window=False)
    assert result.departure_time == NOW - timedelta(days=3)


def test_skipped_window_still_needs_an_offset() -> None:
    naive = raw(departure_time=datetime(2026, 9, 20, 1, 0))
    with pytest.raises(InvalidInput) as info:
        normalize_travel_request(naive, now=NOW, limits=LIMITS, check_departure_window=False)
    assert info.value.issues[0].code == "timezone_required"
