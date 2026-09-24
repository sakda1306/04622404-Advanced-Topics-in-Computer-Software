"""Which recommendations may be shared from the cache (docs/02_api_spec.md 11.2)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.core.geo import geohash_encode
from app.domain.enums import RecommendationStatus, RiskLevel
from app.domain.normalization import NormalizedTravelRequest

GEOHASH_PRECISION = 6  # ~1 km cell


def departure_bucket(value: datetime, minutes: int) -> datetime:
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % (minutes * 60), tz=UTC)


def request_is_cacheable(request: NormalizedTravelRequest, *, has_conversation: bool) -> bool:
    # A question or earlier messages make the answer personal.
    return request.question is None and not has_conversation


def _cell(lat: float, lon: float) -> str:
    return geohash_encode(lat, lon, GEOHASH_PRECISION)


def cache_key(request: NormalizedTravelRequest, *, bucket_minutes: int) -> str:
    prefs = request.preferences
    parts = {
        "origin": _cell(request.origin.lat, request.origin.lon),
        "destination": _cell(request.destination.lat, request.destination.lon),
        "waypoints": [_cell(p.lat, p.lon) for p in request.waypoints],
        "departure": departure_bucket(request.departure_time, bucket_minutes).isoformat(),
        "modes": list(prefs.travel_modes),
        "avoid": list(prefs.avoid),
        "mobility": list(prefs.mobility_needs),
        "max_hours": prefs.max_travel_hours,
        "travelers": prefs.traveler_count,
        "language": request.language,
    }
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def result_is_cacheable(
    *, status: RecommendationStatus, risk_level: RiskLevel | None, overall_is_stale: bool
) -> bool:
    return (
        status is RecommendationStatus.COMPLETED
        and risk_level is not RiskLevel.HIGH
        and not overall_is_stale
    )


def cache_ttl_seconds(*, now: datetime, valid_until: datetime | None, max_seconds: int) -> int:
    """Seconds a result may stay cached; 0 means do not cache."""
    if valid_until is None:
        return 0
    return max(0, min(max_seconds, int((valid_until - now).total_seconds())))
