from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import (
    AlertChannel,
    JobType,
    RequestSource,
    TravelMode,
    TripStatus,
    job_type_for,
)
from app.domain.errors import InvalidInput
from app.domain.follow_up import PreferenceOverrides
from app.domain.normalization import GeoPoint, NormalizationLimits, TravelPreferences
from app.domain.trips import (
    AlertChanges,
    AlertSettings,
    TripChanges,
    TripDraft,
    apply_trip_changes,
    is_closed,
    route_changed,
    validate_trip,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
CONSENT = datetime(2026, 9, 17, 7, 59, tzinfo=UTC)
LIMITS = NormalizationLimits(max_days_ahead=90)
BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")
AYUTTHAYA = GeoPoint(14.3532, 100.5689, name="Ayutthaya")


def draft(**changes: object) -> TripDraft:
    base = TripDraft(
        name="North trip",
        origin=BANGKOK,
        destination=CHIANG_MAI,
        departure_time=NOW + timedelta(days=3),
        timezone="Asia/Bangkok",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def validate(value: TripDraft, *, window: bool = True) -> TripDraft:
    return validate_trip(value, now=NOW, limits=LIMITS, check_departure_window=window)


def apply(current: TripDraft, changes: TripChanges) -> TripDraft:
    return apply_trip_changes(current, changes, now=NOW, limits=LIMITS)


def issues_of(call: object) -> dict[str, str]:
    assert callable(call)
    with pytest.raises(InvalidInput) as info:
        call()
    return {i.field: i.code for i in info.value.issues}


# ------------------------------------------------------------------ validate


def test_valid_trip_is_normalized() -> None:
    result = validate(draft(name="  North trip\x00 ", origin=GeoPoint(13.75630049, 100.5018)))

    assert result.name == "North trip"
    assert result.origin.lat == 13.7563
    assert result.status is TripStatus.PLANNED
    assert result.alerts == AlertSettings()


def test_name_rules() -> None:
    assert issues_of(lambda: validate(draft(name="  "))) == {"name": "required"}
    assert issues_of(lambda: validate(draft(name="x" * 101))) == {"name": "too_long"}
    assert validate(draft(name="x" * 100)).name == "x" * 100


def test_departure_window_uses_trip_limit() -> None:
    assert issues_of(lambda: validate(draft(departure_time=NOW - timedelta(days=1)))) == {
        "departure_time": "in_past"
    }
    assert issues_of(lambda: validate(draft(departure_time=NOW + timedelta(days=91)))) == {
        "departure_time": "too_far_ahead"
    }
    assert validate(draft(departure_time=NOW + timedelta(days=60))).departure_time


def test_departure_window_can_be_skipped() -> None:
    past = NOW - timedelta(days=1)
    assert validate(draft(departure_time=past), window=False).departure_time == past


def test_route_errors_are_reported() -> None:
    assert issues_of(lambda: validate(draft(destination=BANGKOK, timezone="Mars/Base"))) == {
        "destination": "same_as_origin",
        "timezone": "unknown_timezone",
    }


def test_alert_channels() -> None:
    both = AlertSettings(channels=(AlertChannel.IN_APP, AlertChannel.IN_APP))
    assert issues_of(lambda: validate(draft(alerts=both))) == {"alerts.channels": "duplicate"}
    empty = AlertSettings(channels=())
    assert issues_of(lambda: validate(draft(alerts=empty))) == {"alerts.channels": "required"}


def test_alerts_on_need_consent() -> None:
    on = AlertSettings(enabled=True)
    assert issues_of(lambda: validate(draft(alerts=on))) == {"alerts.consent_at": "required"}


def test_consent_time_is_the_server_time() -> None:
    result = validate(draft(alerts=AlertSettings(enabled=True, consent_at=CONSENT)))
    assert result.alerts.consent_at == NOW


def test_alerts_off_have_no_consent() -> None:
    result = validate(draft(alerts=AlertSettings(enabled=False, consent_at=CONSENT)))
    assert result.alerts.consent_at is None


# ------------------------------------------------------------------ apply


def test_rename_keeps_the_route() -> None:
    current = validate(draft())
    result = apply(current, TripChanges(name="Holiday"))

    assert result.name == "Holiday"
    assert not route_changed(current, result)
    assert result.origin == current.origin


def test_rename_of_a_departed_trip_is_allowed() -> None:
    current = replace(validate(draft()), departure_time=NOW - timedelta(hours=5))
    assert apply(current, TripChanges(name="Holiday")).name == "Holiday"


def test_new_departure_is_checked_and_changes_the_route() -> None:
    current = validate(draft())
    later = NOW + timedelta(days=4)

    result = apply(current, TripChanges(departure_time=later))

    assert result.departure_time == later
    assert route_changed(current, result)
    assert issues_of(
        lambda: apply(current, TripChanges(departure_time=NOW - timedelta(days=2)))
    ) == {"departure_time": "in_past"}


def test_preferences_are_merged_per_key() -> None:
    current = validate(
        draft(preferences=TravelPreferences(travel_modes=(TravelMode.TRAIN,), traveler_count=2))
    )
    result = apply(current, TripChanges(preferences=PreferenceOverrides(traveler_count=3)))

    assert result.preferences.travel_modes == (TravelMode.TRAIN,)
    assert result.preferences.traveler_count == 3
    assert route_changed(current, result)


def test_waypoints_are_replaced_or_cleared() -> None:
    current = validate(draft(waypoints=(AYUTTHAYA,)))

    cleared = apply(current, TripChanges(waypoints=()))

    assert cleared.waypoints == ()
    assert route_changed(current, cleared)


def test_nulls_on_required_fields_are_rejected() -> None:
    current = validate(draft())
    nulls = frozenset({"name", "timezone", "status", "alerts.enabled"})

    assert issues_of(lambda: apply(current, TripChanges(explicit_nulls=nulls))) == {
        "name": "required",
        "timezone": "required",
        "status": "required",
        "alerts.enabled": "required",
    }


def test_nulls_on_optional_fields_clear_them() -> None:
    current = validate(
        draft(
            waypoints=(AYUTTHAYA,),
            preferences=TravelPreferences(max_travel_hours=8, traveler_count=2),
        )
    )
    result = apply(
        current,
        TripChanges(explicit_nulls=frozenset({"waypoints", "preferences.max_travel_hours"})),
    )

    assert result.waypoints == ()
    assert result.preferences.max_travel_hours is None
    assert result.preferences.traveler_count == 2


def test_null_preferences_reset_them() -> None:
    current = validate(draft(preferences=TravelPreferences(traveler_count=2)))
    result = apply(current, TripChanges(explicit_nulls=frozenset({"preferences"})))
    assert result.preferences == TravelPreferences()


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (TripStatus.PLANNED, TripStatus.ACTIVE),
        (TripStatus.PLANNED, TripStatus.COMPLETED),
        (TripStatus.PLANNED, TripStatus.CANCELLED),
        (TripStatus.ACTIVE, TripStatus.COMPLETED),
        (TripStatus.ACTIVE, TripStatus.CANCELLED),
        (TripStatus.ACTIVE, TripStatus.ACTIVE),
    ],
)
def test_allowed_status_moves(start: TripStatus, target: TripStatus) -> None:
    current = validate(draft(status=start))
    assert apply(current, TripChanges(status=target)).status is target


def test_active_cannot_go_back_to_planned() -> None:
    current = validate(draft(status=TripStatus.ACTIVE))
    assert issues_of(lambda: apply(current, TripChanges(status=TripStatus.PLANNED))) == {
        "status": "invalid_transition"
    }


@pytest.mark.parametrize("closed", [TripStatus.COMPLETED, TripStatus.CANCELLED])
def test_closed_trips_cannot_change(closed: TripStatus) -> None:
    current = validate(draft(status=closed))

    assert is_closed(closed)
    assert issues_of(lambda: apply(current, TripChanges(name="Again"))) == {"status": "trip_closed"}
    assert issues_of(lambda: apply(current, TripChanges(status=TripStatus.PLANNED))) == {
        "status": "trip_closed"
    }


def test_open_statuses_are_not_closed() -> None:
    assert not is_closed(TripStatus.PLANNED)
    assert not is_closed(TripStatus.ACTIVE)


def test_turning_alerts_on_records_consent() -> None:
    current = validate(draft())

    assert issues_of(lambda: apply(current, TripChanges(alerts=AlertChanges(enabled=True)))) == {
        "alerts.consent_at": "required"
    }
    result = apply(current, TripChanges(alerts=AlertChanges(enabled=True, consent_at=CONSENT)))
    assert result.alerts.enabled
    assert result.alerts.consent_at == NOW
    assert not route_changed(current, result)


def test_alerts_already_on_keep_their_consent_time() -> None:
    earlier = datetime(2026, 9, 1, tzinfo=UTC)
    current = replace(validate(draft()), alerts=AlertSettings(enabled=True, consent_at=earlier))

    result = apply(current, TripChanges(name="Renamed", alerts=AlertChanges(enabled=True)))

    assert result.alerts.consent_at == earlier


def test_turning_alerts_off_clears_consent() -> None:
    current = replace(validate(draft()), alerts=AlertSettings(enabled=True, consent_at=CONSENT))
    result = apply(current, TripChanges(alerts=AlertChanges(enabled=False)))
    assert result.alerts == AlertSettings()


def test_apply_does_not_change_the_input() -> None:
    current = validate(draft())
    before = replace(current)
    apply(current, TripChanges(name="Other", waypoints=(AYUTTHAYA,)))
    assert current == before


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (RequestSource.RECOMMENDATION, JobType.RECOMMENDATION),
        (RequestSource.MESSAGE, JobType.MESSAGE),
        (RequestSource.TRIP_ASSESSMENT, JobType.TRIP_ASSESSMENT),
        (RequestSource.TRIP_ALERT, JobType.TRIP_ASSESSMENT),
    ],
)
def test_job_type_for_every_source(source: RequestSource, expected: JobType) -> None:
    assert job_type_for(source) is expected


def test_all_problems_are_reported_together() -> None:
    bad = draft(name="", timezone="Mars/Base", alerts=AlertSettings(enabled=True))
    assert issues_of(lambda: validate(bad)) == {
        "name": "required",
        "timezone": "unknown_timezone",
        "alerts.consent_at": "required",
    }
