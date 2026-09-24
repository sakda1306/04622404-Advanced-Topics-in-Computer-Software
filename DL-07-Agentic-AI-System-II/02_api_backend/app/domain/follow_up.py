"""Follow-up questions: apply partial changes to the conversation's last request (D-54).

`None` means "keep the earlier value". Preferences are merged key by key; every other
field is replaced as a whole (an empty waypoint tuple removes the waypoints). The result
is raw input, so it goes through normalization again like any new request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.normalization import (
    GeoPoint,
    NormalizedTravelRequest,
    TravelPreferences,
    TravelRequestInput,
)


@dataclass(frozen=True, slots=True)
class PreferenceOverrides:
    travel_modes: tuple[TravelMode, ...] | None = None
    avoid: tuple[AvoidOption, ...] | None = None
    max_travel_hours: int | None = None
    mobility_needs: tuple[MobilityNeed, ...] | None = None
    traveler_count: int | None = None


@dataclass(frozen=True, slots=True)
class RequestOverrides:
    origin: GeoPoint | None = None
    destination: GeoPoint | None = None
    waypoints: tuple[GeoPoint, ...] | None = None
    departure_time: datetime | None = None
    timezone: str | None = None
    language: str | None = None
    preferences: PreferenceOverrides | None = None


def _pick[T](override: T | None, base: T) -> T:
    return base if override is None else override


def _preferences(base: TravelPreferences, changes: PreferenceOverrides | None) -> TravelPreferences:
    if changes is None:
        return base
    return TravelPreferences(
        travel_modes=_pick(changes.travel_modes, base.travel_modes),
        avoid=_pick(changes.avoid, base.avoid),
        max_travel_hours=_pick(changes.max_travel_hours, base.max_travel_hours),
        mobility_needs=_pick(changes.mobility_needs, base.mobility_needs),
        traveler_count=_pick(changes.traveler_count, base.traveler_count),
    )


def _without_base(
    overrides: RequestOverrides,
    *,
    question: str | None,
    accept_language: str | None,
    default_language: str,
) -> TravelRequestInput:
    if (
        overrides.origin is None
        or overrides.destination is None
        or overrides.departure_time is None
        or overrides.timezone is None
    ):
        required = {
            "origin": overrides.origin,
            "destination": overrides.destination,
            "departure_time": overrides.departure_time,
            "timezone": overrides.timezone,
        }
        missing = [name for name, value in required.items() if value is None]
        raise InvalidInput(
            [
                FieldIssue(
                    "overrides",
                    "travel_context_required",
                    f"the conversation has no earlier trip; provide {', '.join(missing)}",
                )
            ]
        )
    return TravelRequestInput(
        origin=overrides.origin,
        destination=overrides.destination,
        waypoints=overrides.waypoints or (),
        departure_time=overrides.departure_time,
        timezone=overrides.timezone,
        language=overrides.language or default_language,
        accept_language=accept_language,
        preferences=_preferences(TravelPreferences(), overrides.preferences),
        question=question,
    )


def merge_overrides(
    base: NormalizedTravelRequest | None,
    overrides: RequestOverrides,
    *,
    question: str | None,
    accept_language: str | None,
    default_language: str,
) -> TravelRequestInput:
    if base is None:
        return _without_base(
            overrides,
            question=question,
            accept_language=accept_language,
            default_language=default_language,
        )
    return TravelRequestInput(
        origin=_pick(overrides.origin, base.origin),
        destination=_pick(overrides.destination, base.destination),
        waypoints=_pick(overrides.waypoints, base.waypoints),
        departure_time=_pick(overrides.departure_time, base.departure_time),
        timezone=_pick(overrides.timezone, base.timezone),
        language=_pick(overrides.language, base.language),
        accept_language=accept_language,
        preferences=_preferences(base.preferences, overrides.preferences),
        question=question,
    )
