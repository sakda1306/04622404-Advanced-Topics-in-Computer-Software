"""Saved trips: validation, JSON Merge Patch changes and status rules (D-59..D-62).

`TripChanges` fields that are `None` keep the current value; `explicit_nulls` names the
fields the client set to `null` (required ones are rejected, optional ones are cleared).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.enums import AlertChannel, TripStatus
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.follow_up import PreferenceOverrides
from app.domain.normalization import (
    GeoPoint,
    NormalizationLimits,
    TravelPreferences,
    TravelRequestInput,
    normalize_travel_request,
)
from app.domain.sanitizer import clean_text

NAME_MAX_CHARS = 100

_CLOSED = frozenset({TripStatus.COMPLETED, TripStatus.CANCELLED})
_MOVES: dict[TripStatus, frozenset[TripStatus]] = {
    TripStatus.PLANNED: frozenset(TripStatus),
    TripStatus.ACTIVE: frozenset({TripStatus.ACTIVE, *_CLOSED}),
}
_REQUIRED = (
    "name",
    "origin",
    "destination",
    "departure_time",
    "timezone",
    "status",
    "alerts.enabled",
    "alerts.channels",
    "preferences.traveler_count",
)


@dataclass(frozen=True, slots=True)
class AlertSettings:
    enabled: bool = False
    consent_at: datetime | None = None
    channels: tuple[AlertChannel, ...] = (AlertChannel.IN_APP,)


@dataclass(frozen=True, slots=True)
class TripDraft:
    name: str
    origin: GeoPoint
    destination: GeoPoint
    departure_time: datetime
    timezone: str
    waypoints: tuple[GeoPoint, ...] = ()
    preferences: TravelPreferences = field(default_factory=TravelPreferences)
    alerts: AlertSettings = field(default_factory=AlertSettings)
    status: TripStatus = TripStatus.PLANNED


@dataclass(frozen=True, slots=True)
class AlertChanges:
    enabled: bool | None = None
    consent_at: datetime | None = None
    channels: tuple[AlertChannel, ...] | None = None


@dataclass(frozen=True, slots=True)
class TripChanges:
    name: str | None = None
    origin: GeoPoint | None = None
    destination: GeoPoint | None = None
    waypoints: tuple[GeoPoint, ...] | None = None
    departure_time: datetime | None = None
    timezone: str | None = None
    preferences: PreferenceOverrides | None = None
    alerts: AlertChanges | None = None
    status: TripStatus | None = None
    explicit_nulls: frozenset[str] = frozenset()

    def is_empty(self) -> bool:
        return self == TripChanges()


def is_closed(status: TripStatus) -> bool:
    return status in _CLOSED


def _coordinates(point: GeoPoint) -> tuple[float, float]:
    return point.lat, point.lon


def route_changed(before: TripDraft, after: TripDraft) -> bool:
    """True when an assessment of `before` no longer describes `after` (D-64)."""
    return (
        _coordinates(before.origin) != _coordinates(after.origin)
        or _coordinates(before.destination) != _coordinates(after.destination)
        or [_coordinates(p) for p in before.waypoints] != [_coordinates(p) for p in after.waypoints]
        or before.departure_time != after.departure_time
        or before.preferences != after.preferences
    )


def _check(
    draft: TripDraft,
    *,
    now: datetime,
    limits: NormalizationLimits,
    window: bool,
    issues: list[FieldIssue],
) -> TripDraft:
    """Validate everything and report all problems at once (with the caller's `issues`)."""
    name = clean_text(draft.name)
    if name is None:
        issues.append(FieldIssue("name", "required", "a trip name is required"))
    elif len(name) > NAME_MAX_CHARS:
        issues.append(FieldIssue("name", "too_long", f"at most {NAME_MAX_CHARS} characters"))
    channels = draft.alerts.channels
    if not channels:
        issues.append(FieldIssue("alerts.channels", "required", "choose at least one channel"))
    elif len(set(channels)) != len(channels):
        issues.append(FieldIssue("alerts.channels", "duplicate", "list each channel once"))
    route = None
    try:
        route = normalize_travel_request(
            TravelRequestInput(
                origin=draft.origin,
                destination=draft.destination,
                departure_time=draft.departure_time,
                timezone=draft.timezone,
                waypoints=draft.waypoints,
                preferences=draft.preferences,
            ),
            now=now,
            limits=limits,
            check_departure_window=window,
        )
    except InvalidInput as exc:
        issues.extend(exc.issues)
    if issues or route is None or name is None:
        raise InvalidInput(issues)
    return replace(
        draft,
        name=name,
        origin=route.origin,
        destination=route.destination,
        waypoints=route.waypoints,
        departure_time=route.departure_time,
        timezone=route.timezone,
        preferences=route.preferences,
    )


_CONSENT_MISSING = FieldIssue(
    "alerts.consent_at", "required", "live alerts need the user's consent"
)


def validate_trip(
    draft: TripDraft, *, now: datetime, limits: NormalizationLimits, check_departure_window: bool
) -> TripDraft:
    """A new trip. Consent is stored as the server time (D-62)."""
    alerts = draft.alerts
    issues = [_CONSENT_MISSING] if alerts.enabled and alerts.consent_at is None else []
    checked = _check(draft, now=now, limits=limits, window=check_departure_window, issues=issues)
    return replace(checked, alerts=replace(alerts, consent_at=now if alerts.enabled else None))


def _preferences(
    base: TravelPreferences, changes: PreferenceOverrides | None, nulls: frozenset[str]
) -> TravelPreferences:
    if "preferences" in nulls:
        base = TravelPreferences()
    changes = changes or PreferenceOverrides()

    def keep[T](name: str, override: T | None, value: T, empty: T) -> T:
        return empty if f"preferences.{name}" in nulls else _pick(override, value)

    return TravelPreferences(
        travel_modes=keep("travel_modes", changes.travel_modes, base.travel_modes, ()),
        avoid=keep("avoid", changes.avoid, base.avoid, ()),
        max_travel_hours=keep(
            "max_travel_hours", changes.max_travel_hours, base.max_travel_hours, None
        ),
        mobility_needs=keep("mobility_needs", changes.mobility_needs, base.mobility_needs, ()),
        traveler_count=_pick(changes.traveler_count, base.traveler_count),
    )


def _pick[T](override: T | None, base: T) -> T:
    return base if override is None else override


def _alerts(
    current: AlertSettings,
    changes: AlertChanges | None,
    nulls: frozenset[str],
    now: datetime,
    issues: list[FieldIssue],
) -> AlertSettings:
    base = AlertSettings() if "alerts" in nulls else current
    if changes is None:
        return base
    enabled = _pick(changes.enabled, base.enabled)
    channels = _pick(changes.channels, base.channels)
    if not enabled:
        return AlertSettings(enabled=False, consent_at=None, channels=channels)
    if current.enabled and current.consent_at is not None:
        return AlertSettings(enabled=True, consent_at=current.consent_at, channels=channels)
    if changes.consent_at is None:
        issues.append(_CONSENT_MISSING)
    return AlertSettings(enabled=True, consent_at=now, channels=channels)


def _status(current: TripStatus, target: TripStatus | None) -> TripStatus:
    if target is None:
        return current
    if target not in _MOVES[current]:
        raise InvalidInput(
            [
                FieldIssue(
                    "status",
                    "invalid_transition",
                    f"a {current.value} trip cannot become {target.value}",
                )
            ]
        )
    return target


def apply_trip_changes(
    current: TripDraft, changes: TripChanges, *, now: datetime, limits: NormalizationLimits
) -> TripDraft:
    nulls = changes.explicit_nulls
    required = [
        FieldIssue(name, "required", "this field cannot be null")
        for name in _REQUIRED
        if name in nulls
    ]
    if required:
        raise InvalidInput(required)
    if changes.is_empty():
        return current
    if is_closed(current.status):
        raise InvalidInput(
            [FieldIssue("status", "trip_closed", "a completed or cancelled trip cannot change")]
        )
    issues: list[FieldIssue] = []
    updated = TripDraft(
        name=_pick(changes.name, current.name),
        origin=_pick(changes.origin, current.origin),
        destination=_pick(changes.destination, current.destination),
        departure_time=_pick(changes.departure_time, current.departure_time),
        timezone=_pick(changes.timezone, current.timezone),
        waypoints=() if "waypoints" in nulls else _pick(changes.waypoints, current.waypoints),
        preferences=_preferences(current.preferences, changes.preferences, nulls),
        alerts=_alerts(current.alerts, changes.alerts, nulls, now, issues),
        status=_status(current.status, changes.status),
    )
    return _check(
        updated, now=now, limits=limits, window=changes.departure_time is not None, issues=issues
    )
