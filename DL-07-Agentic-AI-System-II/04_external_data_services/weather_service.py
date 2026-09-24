"""Module 04 entry points that return Module 05's provisional weather records.

Provider failures become explicit unavailable records. They never become an
empty result or a fabricated weather measurement.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from open_meteo_adapter import (
    WeatherDataError,
    WeatherProviderError,
    fetch_current_weather,
    fetch_weather_forecast,
)
from weather_to_canonical import CANONICAL_SCHEMA, to_canonical_weather_record


def _point(latitude: float, longitude: float) -> list[float]:
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
            or not math.isfinite(latitude) or not math.isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise ValueError("Invalid latitude or longitude")
    return [float(longitude), float(latitude)]


def _unavailable(kind: str, latitude: float, longitude: float, code: str) -> dict:
    point = _point(latitude, longitude)
    attempted_at = datetime.now(timezone.utc).isoformat()
    identity = f"{kind}|{point}|{attempted_at}|{code}"
    record_id = "open-meteo:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": CANONICAL_SCHEMA,
        "record_id": record_id,
        "record_kind": kind,
        "status": "unavailable",
        "source": {"name": "Open-Meteo", "authority": None},
        "source_lineage": None,
        "spatial_footprint": {"type": "Point", "coordinates": point},
        "observed_at": None,
        "valid_at": None,
        "issued_at": None,
        "event_time": None,
        "fetched_at": attempted_at,
        "expires_at": None,
        "value": None,
        "quality_flags": ["unavailable"],
        "severity": None,
        "error_code": code,
    }


def fetch_canonical_current_weather(latitude: float, longitude: float) -> dict:
    """Fetch one current model record or an explicit unavailable record."""
    _point(latitude, longitude)
    try:
        return to_canonical_weather_record(fetch_current_weather(latitude, longitude))
    except WeatherProviderError:
        return _unavailable("current_weather", latitude, longitude, "PROVIDER_UNAVAILABLE")
    except WeatherDataError:
        return _unavailable("current_weather", latitude, longitude, "PROVIDER_DATA_INVALID")


def fetch_canonical_forecast(latitude: float, longitude: float) -> list[dict]:
    """Fetch hourly forecast records or one explicit unavailable record."""
    _point(latitude, longitude)
    try:
        return [to_canonical_weather_record(item) for item in fetch_weather_forecast(latitude, longitude)]
    except WeatherProviderError:
        return [_unavailable("weather_forecast", latitude, longitude, "PROVIDER_UNAVAILABLE")]
    except WeatherDataError:
        return [_unavailable("weather_forecast", latitude, longitude, "PROVIDER_DATA_INVALID")]
