"""Provisional Module 05 contract and deterministic integration core.

This module consumes canonical source records, never raw provider payloads. The
wire format is deliberately marked v0.1-proposed until Modules 03 and 06 agree
on route ownership and the final feature schema.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

FEATURE_SCHEMA_VERSION = "integrated-travel-v0.1-proposed"
RECORD_SCHEMA_VERSION = "canonical-record-v0.1-proposed"
KINDS = (
    "current_weather",
    "weather_forecast",
    "transport_status",
    "closure",
    "disaster_event",
    "official_alert",
)
# Same essential set as Module 06 routing.py (Contract Register issue #2). Optional
# kinds have no live provider yet: their absence is reported per segment but does not
# degrade quality. A provider that exists and fails (unavailable/stale) still does.
ESSENTIAL_KINDS = (
    "current_weather",
    "weather_forecast",
    "transport_status",
    "disaster_event",
)
OPTIONAL_KINDS = tuple(kind for kind in KINDS if kind not in ESSENTIAL_KINDS)
STATUSES = {"available", "unavailable"}
EARTH_RADIUS_M = 6_371_000.0


class ContractError(ValueError):
    """Input cannot be interpreted without guessing."""


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO 8601 string with an offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{field} is not an ISO 8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _point(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ContractError(f"{field} must be [longitude, latitude]")
    lon, lat = value
    if any(
        isinstance(number, bool) or not isinstance(number, (int, float))
        for number in (lon, lat)
    ):
        raise ContractError(f"{field} must contain numbers")
    if not all(math.isfinite(number) for number in (lon, lat)) or not (
        -180 <= lon <= 180 and -90 <= lat <= 90
    ):
        raise ContractError(f"{field} is outside valid longitude/latitude bounds")
    return float(lon), float(lat)


def _route(route: Any) -> dict[str, Any]:
    if (
        not isinstance(route, dict)
        or not isinstance(route.get("route_id"), str)
        or not route["route_id"]
    ):
        raise ContractError("each route needs route_id")

    label = route.get("label")
    travel_modes = route.get("travel_modes", [])
    if label is not None and not isinstance(label, str):
        raise ContractError("route.label must be a string or null")
    if not isinstance(travel_modes, list) or not all(
        isinstance(mode, str) for mode in travel_modes
    ):
        raise ContractError("route.travel_modes must be a list of strings")

    geometry = route.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise ContractError("route geometry must be GeoJSON LineString")
    raw_coordinates = geometry.get("coordinates")
    if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 2:
        raise ContractError("route geometry needs at least two coordinates")
    coordinates = [_point(value, "route coordinate") for value in raw_coordinates]

    raw_segments = route.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ContractError("route needs timed segments covering its full geometry")
    segments = []
    previous_end = 0
    previous_exit = None

    for raw in raw_segments:
        if not isinstance(raw, dict):
            raise ContractError("segment must be an object")
        start_index, end_index = raw.get("start_index"), raw.get("end_index")
        if type(start_index) is not int or type(end_index) is not int:
            raise ContractError("segment coordinate indices must be integers")
        if start_index != previous_end or not start_index < end_index < len(coordinates):
            raise ContractError("segments must cover consecutive route coordinates")
        enter_at = _time(raw.get("enter_at"), "segment.enter_at")
        exit_at = _time(raw.get("exit_at"), "segment.exit_at")
        if enter_at >= exit_at or (
            previous_exit is not None and enter_at < previous_exit
        ):
            raise ContractError("segment times must be ordered and non-overlapping")
        segments.append(
            {
                "start_index": start_index,
                "end_index": end_index,
                "enter_at": enter_at,
                "exit_at": exit_at,
                "matched_record_ids": {kind: [] for kind in KINDS},
            }
        )
        previous_end, previous_exit = end_index, exit_at

    if previous_end != len(coordinates) - 1:
        raise ContractError("segments must cover the full route")
    return {
        "route_id": route["route_id"],
        "label": label,
        "travel_modes": travel_modes,
        "coordinates": coordinates,
        "segments": segments,
    }


def _weather_value_for_06(kind: str, value: Any) -> Any:
    """Add unit-explicit aliases read by 06, retaining every source value.

    The mapping is deterministic: km/h and kph are the same unit, metres become
    kilometres, and a percentage becomes a fraction. No missing value is filled.
    """
    if kind not in {"current_weather", "weather_forecast"} or not isinstance(
        value, dict
    ):
        return value
    normalized = value.copy()
    aliases = (
        ("wind_speed_kmh", "wind_speed_kph", 1.0),
        ("visibility_m", "visibility_km", 0.001),
        ("rain_probability_percent", "rain_probability", 0.01),
    )
    for source_field, target_field, factor in aliases:
        source_value = value.get(source_field)
        if source_value is None:
            continue
        if (
            isinstance(source_value, bool)
            or not isinstance(source_value, (int, float))
            or not math.isfinite(source_value)
        ):
            raise ContractError(
                f"weather {source_field} must be a finite number or null"
            )
        if source_field == "rain_probability_percent" and not 0 <= source_value <= 100:
            raise ContractError("rain_probability_percent must be between 0 and 100")
        if source_field in {"wind_speed_kmh", "visibility_m"} and source_value < 0:
            raise ContractError(f"weather {source_field} cannot be negative")
        derived = source_value * factor
        existing = value.get(target_field)
        if existing is not None:
            if (
                isinstance(existing, bool)
                or not isinstance(existing, (int, float))
                or not math.isfinite(existing)
                or not math.isclose(existing, derived, rel_tol=1e-9, abs_tol=1e-9)
            ):
                raise ContractError(
                    f"weather {target_field} conflicts with {source_field}"
                )
        normalized[target_field] = derived
    return normalized


def _record(record: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ContractError("record must be an object")
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise ContractError("unsupported record schema_version")
    record_id, kind, status = (
        record.get("record_id"),
        record.get("record_kind"),
        record.get("status"),
    )
    if (
        not isinstance(record_id, str)
        or not record_id
        or kind not in KINDS
        or status not in STATUSES
    ):
        raise ContractError("record_id, record_kind, or status is invalid")
    source = record.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("name"), str)
        or not source["name"]
    ):
        raise ContractError("record source.name is required")

    fetched_at = _time(record.get("fetched_at"), "record.fetched_at")
    expires_at = (
        _time(record["expires_at"], "record.expires_at")
        if record.get("expires_at")
        else None
    )
    if expires_at is not None and expires_at <= fetched_at:
        raise ContractError("record.expires_at must be after fetched_at")
    valid_at = (
        _time(record["valid_at"], "record.valid_at") if record.get("valid_at") else None
    )
    observed_at = (
        _time(record["observed_at"], "record.observed_at")
        if record.get("observed_at")
        else None
    )
    issued_at = (
        _time(record["issued_at"], "record.issued_at")
        if record.get("issued_at")
        else None
    )
    event_time = (
        _time(record["event_time"], "record.event_time")
        if record.get("event_time")
        else None
    )
    if observed_at is not None and observed_at > fetched_at:
        raise ContractError("record.observed_at cannot follow fetched_at")
    if kind == "weather_forecast" and status == "available" and valid_at is None:
        raise ContractError("available weather_forecast requires valid_at")
    if status == "available" and record.get("value") is None:
        raise ContractError("available record requires value")
    if status == "available" and (
        not isinstance(record.get("source_lineage"), str)
        or not record["source_lineage"]
    ):
        raise ContractError("available record requires source_lineage")
    if status == "unavailable" and record.get("value") is not None:
        raise ContractError("unavailable record cannot contain a value")
    if status == "unavailable" and not record.get("error_code"):
        raise ContractError("unavailable record requires error_code")

    footprint = record.get("spatial_footprint")
    point = None
    incident_line = None
    if footprint is not None:
        if not isinstance(footprint, dict):
            raise ContractError("spatial_footprint must be GeoJSON or null")
        if footprint.get("type") == "Point":
            point = _point(footprint.get("coordinates"), "record point")
        elif footprint.get("type") == "LineString":
            raw_line = footprint.get("coordinates")
            if not isinstance(raw_line, list) or len(raw_line) < 2:
                raise ContractError("record line needs at least two coordinates")
            incident_line = [_point(item, "record line coordinate") for item in raw_line]
    flags = record.get("quality_flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ContractError("quality_flags must be a list of strings")
    freshness = (
        "unknown"
        if expires_at is None
        else "stale"
        if now >= expires_at
        else "fresh"
    )
    return {
        "record_id": record_id,
        "record_kind": kind,
        "status": status,
        "source": source,
        "source_lineage": record.get("source_lineage"),
        "spatial_footprint": footprint,
        "point": point,
        "line": incident_line,
        "valid_at": valid_at,
        "observed_at": observed_at,
        "issued_at": issued_at,
        "event_time": event_time,
        "fetched_at": fetched_at,
        "expires_at": expires_at,
        "freshness": freshness,
        "severity": record.get("severity"),
        "quality_flags": flags,
        "value": _weather_value_for_06(kind, record.get("value")),
        "error_code": record.get("error_code"),
    }


def _distance_to_line_m(
    point: tuple[float, float], line: list[tuple[float, float]]
) -> float:
    """Local metric approximation; used only to find nearby point evidence."""
    lon0, lat0 = point
    latitude_scale = EARTH_RADIUS_M * math.pi / 180
    longitude_scale = latitude_scale * math.cos(math.radians(lat0))
    coordinates = [
        ((lon - lon0) * longitude_scale, (lat - lat0) * latitude_scale)
        for lon, lat in line
    ]
    best = math.inf
    for (ax, ay), (bx, by) in zip(coordinates, coordinates[1:]):
        dx, dy = bx - ax, by - ay
        fraction = (
            0.0
            if dx == dy == 0
            else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        )
        best = min(best, math.hypot(ax + fraction * dx, ay + fraction * dy))
    return best


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    """Check whether two straight GeoJSON stretches cross or touch."""
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    epsilon = 0.0
    if (
        max(min(a[0], b[0]), min(c[0], d[0]))
        > min(max(a[0], b[0]), max(c[0], d[0])) + epsilon
        or max(min(a[1], b[1]), min(c[1], d[1]))
        > min(max(a[1], b[1]), max(c[1], d[1])) + epsilon
    ):
        return False
    return (
        cross(a, b, c) * cross(a, b, d) <= epsilon
        and cross(c, d, a) * cross(c, d, b) <= epsilon
    )


def _distance_between_lines_m(
    route_line: list[tuple[float, float]],
    incident_line: list[tuple[float, float]],
) -> float:
    """Minimum local distance; crossings count even without nearby vertices."""
    for start, end in zip(route_line, route_line[1:]):
        for other_start, other_end in zip(incident_line, incident_line[1:]):
            if _segments_intersect(start, end, other_start, other_end):
                return 0.0
    return min(
        *(_distance_to_line_m(point, route_line) for point in incident_line),
        *(_distance_to_line_m(point, incident_line) for point in route_line),
    )


def _record_time(record: dict[str, Any]) -> datetime | None:
    return (
        record["valid_at"]
        or record["observed_at"]
        or record["event_time"]
        or record["issued_at"]
    )


def _matches_segment_time(
    record: dict[str, Any], segment: dict[str, Any]
) -> bool:
    """Match an event interval, or a single timestamp when no interval exists."""
    if record["record_kind"] in {"disaster_event", "transport_status"} and isinstance(
        record["value"], dict
    ):
        start_raw = record["value"].get("starts_at")
        end_raw = record["value"].get("ends_at")
        if start_raw is not None and end_raw is not None:
            try:
                start = _time(start_raw, "event.starts_at")
                end = _time(end_raw, "event.ends_at")
            except ContractError:
                return False
            return (
                start < end
                and start < segment["exit_at"]
                and segment["enter_at"] < end
            )

    source_time = _record_time(record)
    return source_time is not None and (
        segment["enter_at"] <= source_time <= segment["exit_at"]
    )


def build_context(
    query: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    corridor_m: float = 1000.0,
) -> dict[str, Any]:
    """Build a conservative provisional context for every candidate route.

    Match fresh point or LineString records near a route at travel time.
    Disaster and transport intervals can overlap a segment. Polygon
    intersection awaits the final cross-team contract.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ContractError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if not math.isfinite(corridor_m) or corridor_m <= 0:
        raise ContractError("corridor_m must be positive")
    if (
        not isinstance(query, dict)
        or not isinstance(query.get("run_id"), str)
        or not query["run_id"]
    ):
        raise ContractError("run_id is required")
    raw_routes = query.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ContractError("at least one route is required")
    routes = [_route(route) for route in raw_routes]
    route_ids = [route["route_id"] for route in routes]
    if len(set(route_ids)) != len(route_ids):
        raise ContractError("route_id must be unique")
    if not isinstance(records, list):
        raise ContractError("records must be a list")
    normalized = [_record(record, now) for record in records]
    record_ids = [record["record_id"] for record in normalized]
    if len(set(record_ids)) != len(record_ids):
        raise ContractError("record_id must be unique")

    for route in routes:
        for segment in route["segments"]:
            line = route["coordinates"][
                segment["start_index"] : segment["end_index"] + 1
            ]
            for record in normalized:
                if (
                    record["status"] != "available"
                    or record["freshness"] != "fresh"
                    or (record["point"] is None and record["line"] is None)
                    or not _matches_segment_time(record, segment)
                ):
                    continue
                distance = (
                    _distance_to_line_m(record["point"], line)
                    if record["point"] is not None
                    else _distance_between_lines_m(line, record["line"])
                )
                if distance <= corridor_m:
                    segment["matched_record_ids"][record["record_kind"]].append(
                        record["record_id"]
                    )

    unavailable = {
        record["record_kind"]
        for record in normalized
        if record["status"] == "unavailable"
    }
    stale = {
        record["record_kind"]
        for record in normalized
        if record["freshness"] == "stale"
    }
    output_routes = []
    all_flags = set()
    for route in routes:
        output_segments = []
        for segment in route["segments"]:
            coverage = {}
            for kind in KINDS:
                coverage[kind] = (
                    "covered"
                    if segment["matched_record_ids"][kind]
                    else "unavailable"
                    if kind in unavailable
                    else "stale"
                    if kind in stale
                    else "missing"
                )
                if coverage[kind] == "covered":
                    continue
                if kind in ESSENTIAL_KINDS or coverage[kind] != "missing":
                    all_flags.add(coverage[kind])
            essential = [coverage[kind] for kind in ESSENTIAL_KINDS]
            if "covered" in essential and any(status != "covered" for status in essential):
                all_flags.add("partial")
            output_segments.append(
                {
                    "start_index": segment["start_index"],
                    "end_index": segment["end_index"],
                    "enter_at": segment["enter_at"].isoformat(),
                    "exit_at": segment["exit_at"].isoformat(),
                    "matched_record_ids": segment["matched_record_ids"],
                    "coverage": coverage,
                }
            )
        output_routes.append(
            {
                "route_id": route["route_id"],
                "label": route["label"],
                "travel_modes": route["travel_modes"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(point) for point in route["coordinates"]],
                },
                "segments": output_segments,
            }
        )
    matched_ids = {
        record_id
        for route in routes
        for segment in route["segments"]
        for ids in segment["matched_record_ids"].values()
        for record_id in ids
    }
    evidence = []
    unmatched_evidence = []
    for record in normalized:
        serialized = {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in record.items()
            if key not in {"point", "line"}
        }
        if record["record_id"] in matched_ids or record["status"] == "unavailable":
            evidence.append(serialized)
            all_flags.update(record["quality_flags"])
            if record["status"] == "available" and (
                (record["point"] is None and record["line"] is None)
                or _record_time(record) is None
            ):
                all_flags.add("incomplete")
            if record["freshness"] == "unknown":
                all_flags.add("freshness_unknown")
        else:
            unmatched_evidence.append(serialized)

    if not all_flags:
        confidence = "HIGH"
    elif any(f in all_flags for f in ("unavailable", "missing", "incomplete", "stale", "partial")):
        confidence = "LOW"
    else:
        confidence = "MEDIUM"

    has_active_block = any(
        r.get("severity") in ("HIGH", "CRITICAL")
        or (
            isinstance(r.get("value"), dict)
            and (
                r["value"].get("status") == "CLOSED"
                or (
                    r["value"].get("active") is True
                    and r["value"].get("severity") in ("HIGH", "CRITICAL")
                )
            )
        )
        for r in normalized
        if r.get("record_id") in matched_ids
    )

    if confidence == "LOW":
        active_restriction = None
    else:
        active_restriction = bool(has_active_block)

    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "run_id": query["run_id"],
        "created_at": now.isoformat(),
        "routes": output_routes,
        "evidence": evidence,
        "unmatched_evidence": unmatched_evidence,
        "quality_flags": sorted(all_flags),
        "degraded": bool(all_flags),
        "risk_score": None,
        "confidence": confidence,
        "active_restriction": active_restriction,
    }
