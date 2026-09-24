"""Route exposure scoring with hard official-closure constraints."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .evidence import module_record
from .models import (
    IntegratedEvidence,
    IntegratedRoute,
    IntegratedTravelContext,
    Level,
    RiskResult,
    RouteInfo,
    RouteResult,
    TravelQuery,
    as_mapping,
)


LEVEL_RANK = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2}


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    delta_lon, delta_lat = lon2 - lon1, lat2 - lat1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(value))


def _distance(route: IntegratedRoute) -> float | None:
    geometry = route.geometry or {}
    coordinates = geometry.get("coordinates") if geometry.get("type") == "LineString" else None
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        points = [(float(item[0]), float(item[1])) for item in coordinates]
    except (TypeError, ValueError, IndexError):
        return None
    return round(sum(_haversine_km(left, right) for left, right in zip(points, points[1:])), 3)


def _duration(route: IntegratedRoute) -> float | None:
    if not route.segments:
        return None
    duration = (route.segments[-1].exit_at - route.segments[0].enter_at).total_seconds() / 60
    return round(duration, 2) if duration >= 0 else None


def _matched_ids(route: IntegratedRoute) -> set[str]:
    found: set[str] = set()
    for segment in route.segments:
        for ids in segment.matched_record_ids.values():
            found.update(ids)
    return found


def _is_hard_closure(record: IntegratedEvidence) -> bool:
    if record.status != "available" or record.freshness == "stale":
        return False
    value = record.value if isinstance(record.value, dict) else {}
    active = value.get("active", True)
    level = str(value.get("level") or value.get("status") or "").upper()
    return active is not False and (
        record.record_kind == "closure"
        or (record.record_kind == "official_alert" and level in {"AVOID", "CLOSURE", "CLOSED"})
    )


def _record_level(record: IntegratedEvidence) -> Level:
    value = record.value if isinstance(record.value, dict) else {}
    raw = str(record.severity or value.get("severity") or "LOW").upper()
    if raw in {"HIGH", "CRITICAL"}:
        return Level.HIGH
    return Level.MEDIUM if raw == "MEDIUM" else Level.LOW


ESSENTIAL_KINDS = {
    "current_weather",
    "weather_forecast",
    "transport_status",
    "disaster_event",
}


def _has_complete_coverage(route: IntegratedRoute) -> bool:
    return bool(route.segments) and all(
        segment.coverage
        and all(
            segment.coverage.get(kind, "").lower() == "covered"
            for kind in ESSENTIAL_KINDS
        )
        for segment in route.segments
    )


def _route_info(
    route: IntegratedRoute,
    evidence_by_id: dict[str, IntegratedEvidence],
    *,
    default_level: Level,
    travel_modes: list[str],
) -> RouteInfo:
    ids = _matched_ids(route)
    matched = [evidence_by_id[item] for item in ids if item in evidence_by_id]
    closure = any(_is_hard_closure(record) for record in matched)
    level = default_level
    for record in matched:
        if record.status == "available" and record.freshness != "stale":
            candidate = _record_level(record)
            if LEVEL_RANK[candidate] > LEVEL_RANK[level]:
                level = candidate
    incomplete = not _has_complete_coverage(route)
    if incomplete and LEVEL_RANK[level] < LEVEL_RANK[Level.MEDIUM]:
        level = Level.MEDIUM
    if closure:
        level = Level.HIGH
    return RouteInfo(
        route_id=route.route_id,
        label=route.label,
        travel_modes=route.travel_modes or travel_modes,
        distance_km=_distance(route),
        duration_minutes=_duration(route),
        risk_level=level,
        usable=not closure,
    )


def analyze_routes(
    query: TravelQuery | dict[str, Any],
    context: IntegratedTravelContext | dict[str, Any] | None,
    risk: RiskResult | dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> RouteResult:
    """Evaluate candidate routes; closures are never traded against time or distance."""

    parsed_query = TravelQuery.model_validate(as_mapping(query))
    parsed_risk = RiskResult.model_validate(as_mapping(risk)) if risk is not None else None
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if context is None:
        primary = RouteInfo(
            route_id="unknown-route",
            travel_modes=parsed_query.travel_modes,
            risk_level=Level.HIGH,
            usable=False,
        )
        return RouteResult(
            primary=primary,
            no_safe_route=True,
            records=[
                module_record(
                    "route",
                    "Integrated context unavailable; no route can be verified safe.",
                    now=current,
                )
            ],
        )

    parsed = IntegratedTravelContext.model_validate(as_mapping(context))
    default_level = parsed_risk.level if parsed_risk else Level.MEDIUM
    evidence_by_id = {item.record_id: item for item in parsed.evidence}

    if parsed.routes:
        infos = [
            _route_info(
                route,
                evidence_by_id,
                default_level=default_level if index == 0 else Level.LOW,
                travel_modes=parsed_query.travel_modes,
            )
            for index, route in enumerate(parsed.routes)
        ]
        primary = infos[0]
        alternatives = infos[1:11]
    else:
        primary = RouteInfo(
            route_id=parsed.resolved_primary_route_id,
            travel_modes=parsed_query.travel_modes,
            risk_level=default_level,
            usable=parsed.active_restriction is not True,
        )
        alternatives = []

    if parsed.active_restriction is True:
        primary = primary.model_copy(update={"usable": False, "risk_level": Level.HIGH})
    alternative_routes = parsed.routes[1:11] if parsed.routes else []
    alternatives = [
        item.model_copy(update={
            "clearly_safer": _has_complete_coverage(route) and item.usable and (
                not primary.usable or LEVEL_RANK[item.risk_level] < LEVEL_RANK[primary.risk_level]
            )
        })
        for route, item in zip(alternative_routes, alternatives, strict=True)
    ]
    no_safe_route = not primary.usable and not any(item.usable for item in alternatives)
    excerpt = (
        f"primary={primary.route_id}; primary_level={primary.risk_level}; usable={primary.usable}; "
        f"alternatives={len(alternatives)}; no_safe_route={no_safe_route}"
    )
    return RouteResult(
        primary=primary,
        alternatives=alternatives,
        no_safe_route=no_safe_route,
        safer_later=False,
        suggested_departure_time=None,
        records=[module_record("route", excerpt, now=current)],
    )
