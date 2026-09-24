"""Normalize a travel request before it reaches the Agent (docs/02_api_spec.md 5.1).

The API schema checks types; this module applies the rules that need context (time
window, distinct locations, timezone database) and produces a canonical form: UTC
time, 6-decimal coordinates, supported language, sorted unique preferences and a
cleaned question. Every problem is reported at once.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from zoneinfo import available_timezones

from app.core.geo import haversine_m
from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.sanitizer import clean_text

SUPPORTED_LANGUAGES = ("th", "en")
DEFAULT_LANGUAGE = "th"
COORDINATE_DECIMALS = 6
MAX_TRAVEL_HOURS = (1, 48)
TRAVELER_COUNT = (1, 20)
NAME_MAX_LENGTH = 200


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lon: float
    name: str | None = None
    place_id: str | None = None


@dataclass(frozen=True, slots=True)
class TravelPreferences:
    travel_modes: tuple[TravelMode, ...] = ()
    avoid: tuple[AvoidOption, ...] = ()
    max_travel_hours: int | None = None
    mobility_needs: tuple[MobilityNeed, ...] = ()
    traveler_count: int = 1


@dataclass(frozen=True, slots=True)
class TravelRequestInput:
    origin: GeoPoint
    destination: GeoPoint
    departure_time: datetime
    timezone: str
    waypoints: Sequence[GeoPoint] = ()
    language: str | None = None
    accept_language: str | None = None
    preferences: TravelPreferences = field(default_factory=TravelPreferences)
    question: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationLimits:
    max_waypoints: int = 5  # P-42
    max_days_ahead: int = 14  # P-43
    max_question_chars: int = 1000  # P-41
    min_distance_m: float = 50.0
    past_tolerance: timedelta = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class NormalizedTravelRequest:
    origin: GeoPoint
    destination: GeoPoint
    waypoints: tuple[GeoPoint, ...]
    departure_time: datetime
    timezone: str
    language: str
    preferences: TravelPreferences
    question: str | None


def _primary_language(tag: str | None) -> str | None:
    if not tag:
        return None
    primary = tag.strip().split("-")[0].split("_")[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else None


def _accept_language_candidates(header: str) -> list[str]:
    weighted: list[tuple[float, int, str]] = []
    for position, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        if tag and quality > 0:
            weighted.append((-quality, position, tag))
    return [tag for _, _, tag in sorted(weighted)]


def negotiate_language(explicit: str | None, accept_language: str | None) -> str:
    chosen = _primary_language(explicit)
    if chosen:
        return chosen
    for tag in _accept_language_candidates(accept_language or ""):
        chosen = _primary_language(tag)
        if chosen:
            return chosen
    return DEFAULT_LANGUAGE


def _point(point: GeoPoint, prefix: str, issues: list[FieldIssue]) -> GeoPoint:
    valid = True
    for name, value, bound in (("lat", point.lat, 90.0), ("lon", point.lon, 180.0)):
        if not math.isfinite(value) or abs(value) > bound:
            issues.append(
                FieldIssue(f"{prefix}.{name}", "out_of_range", f"must be within ±{bound:g}")
            )
            valid = False
    place_id = clean_text(point.place_id)
    if place_id is not None and len(place_id) > NAME_MAX_LENGTH:
        # An identifier cannot be shortened without changing its meaning.
        issues.append(
            FieldIssue(f"{prefix}.place_id", "too_long", f"at most {NAME_MAX_LENGTH} characters")
        )
        valid = False
    if not valid:
        return point
    label = clean_text(point.name)
    return GeoPoint(
        lat=round(point.lat, COORDINATE_DECIMALS),
        lon=round(point.lon, COORDINATE_DECIMALS),
        name=label[:NAME_MAX_LENGTH] if label else None,
        place_id=place_id,
    )


def _distance(a: GeoPoint, b: GeoPoint) -> float:
    return haversine_m(a.lat, a.lon, b.lat, b.lon)


def _departure(
    value: datetime,
    now: datetime,
    limits: NormalizationLimits,
    issues: list[FieldIssue],
    *,
    check_window: bool,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        issues.append(FieldIssue("departure_time", "timezone_required", "include a UTC offset"))
        return value
    utc = value.astimezone(UTC)
    if not check_window:
        return utc
    if utc < now - limits.past_tolerance:
        issues.append(FieldIssue("departure_time", "in_past", "departure time has passed"))
    elif utc > now + timedelta(days=limits.max_days_ahead):
        issues.append(
            FieldIssue(
                "departure_time",
                "too_far_ahead",
                f"at most {limits.max_days_ahead} days ahead",
            )
        )
    return utc


@cache
def _known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def _timezone(name: str, issues: list[FieldIssue]) -> str:
    # Compare with the canonical list: opening the zone file alone is not enough, because
    # Windows resolves "Asia/Bangkok " and "Asia/Bangkok." to the same file.
    if name not in _known_timezones():
        issues.append(FieldIssue("timezone", "unknown_timezone", "use an IANA timezone name"))
    return name


def _preferences(prefs: TravelPreferences, issues: list[FieldIssue]) -> TravelPreferences:
    low, high = MAX_TRAVEL_HOURS
    if prefs.max_travel_hours is not None and not low <= prefs.max_travel_hours <= high:
        issues.append(
            FieldIssue("preferences.max_travel_hours", "out_of_range", f"must be {low}-{high}")
        )
    low, high = TRAVELER_COUNT
    if not low <= prefs.traveler_count <= high:
        issues.append(
            FieldIssue("preferences.traveler_count", "out_of_range", f"must be {low}-{high}")
        )
    return TravelPreferences(
        travel_modes=tuple(sorted(set(prefs.travel_modes))),
        avoid=tuple(sorted(set(prefs.avoid))),
        max_travel_hours=prefs.max_travel_hours,
        mobility_needs=tuple(sorted(set(prefs.mobility_needs))),
        traveler_count=prefs.traveler_count,
    )


def _waypoints(
    points: Sequence[GeoPoint], limits: NormalizationLimits, issues: list[FieldIssue]
) -> tuple[GeoPoint, ...]:
    if len(points) > limits.max_waypoints:
        issues.append(
            FieldIssue("waypoints", "too_many", f"at most {limits.max_waypoints} waypoints")
        )
        return tuple(points)
    cleaned: list[GeoPoint] = []
    for index, point in enumerate(points):
        before = len(issues)
        normalized = _point(point, f"waypoints.{index}", issues)
        if len(issues) > before:
            continue
        if cleaned and _distance(cleaned[-1], normalized) < limits.min_distance_m:
            continue
        cleaned.append(normalized)
    return tuple(cleaned)


def normalize_travel_request(
    raw: TravelRequestInput,
    *,
    now: datetime,
    limits: NormalizationLimits,
    check_departure_window: bool = True,
) -> NormalizedTravelRequest:
    issues: list[FieldIssue] = []
    before = len(issues)
    origin = _point(raw.origin, "origin", issues)
    destination = _point(raw.destination, "destination", issues)
    if len(issues) == before and _distance(origin, destination) < limits.min_distance_m:
        issues.append(
            FieldIssue("destination", "same_as_origin", "destination must differ from origin")
        )
    waypoints = _waypoints(raw.waypoints, limits, issues)
    departure = _departure(
        raw.departure_time, now, limits, issues, check_window=check_departure_window
    )
    timezone_name = _timezone(raw.timezone, issues)
    preferences = _preferences(raw.preferences, issues)
    question = clean_text(raw.question)
    if question is not None and len(question) > limits.max_question_chars:
        issues.append(
            FieldIssue("question", "too_long", f"at most {limits.max_question_chars} characters")
        )
    if issues:
        raise InvalidInput(issues)
    return NormalizedTravelRequest(
        origin=origin,
        destination=destination,
        waypoints=waypoints,
        departure_time=departure,
        timezone=timezone_name,
        language=negotiate_language(raw.language, raw.accept_language),
        preferences=preferences,
        question=question,
    )
