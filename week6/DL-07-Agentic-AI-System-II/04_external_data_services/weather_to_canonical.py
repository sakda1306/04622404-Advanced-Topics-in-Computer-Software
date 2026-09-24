"""Adapt Module 04 weather records to Module 05's provisional record contract.

This adapter does not infer observations, severity, confidence, or route coverage.
The canonical contract is provisional until the team freezes its schema.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Any

WEATHER_SCHEMA = "weather-record-v0.1"
CANONICAL_SCHEMA = "canonical-record-v0.1-proposed"
VALUE_FIELDS = (
    "temperature_c",
    "rain_mm",
    "rain_probability_percent",
    "snowfall_cm",
    "wind_speed_kmh",
    "wind_direction_degrees",
    "visibility_m",
    "weather_code",
)
KINDS = {"model_current": "current_weather", "forecast": "weather_forecast"}


class WeatherContractError(ValueError):
    """The Module 04 record cannot be converted without guessing."""


def _time(record: dict[str, Any], field: str) -> datetime:
    value = record.get(field)
    if not isinstance(value, str):
        raise WeatherContractError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WeatherContractError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeatherContractError(f"{field} must include a timezone offset")
    return parsed


def _coordinate(record: dict[str, Any], field: str, low: float, high: float) -> float:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherContractError(f"{field} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise WeatherContractError(f"{field} is outside valid bounds")
    return float(value)


def to_canonical_weather_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one successful 04 record; retain its values, times, and lineage."""
    if not isinstance(record, dict) or record.get("schema_version") != WEATHER_SCHEMA:
        raise WeatherContractError("unsupported weather schema_version")
    data_kind = record.get("data_kind")
    if data_kind not in KINDS:
        raise WeatherContractError("unsupported data_kind")
    kind = KINDS[data_kind]
    latitude = _coordinate(record, "latitude", -90, 90)
    longitude = _coordinate(record, "longitude", -180, 180)
    valid_at = _time(record, "valid_at")
    fetched_at = _time(record, "fetched_at")
    expires_at = _time(record, "expires_at")
    if expires_at <= fetched_at:
        raise WeatherContractError("expires_at must follow fetched_at")
    source = record.get("source")
    lineage = record.get("source_lineage")
    if not isinstance(source, str) or not source:
        raise WeatherContractError("source must be a nonempty name")
    if not isinstance(lineage, str) or not lineage:
        raise WeatherContractError("source_lineage must be nonempty")
    flags = record.get("quality_flags")
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise WeatherContractError("quality_flags must be a list of strings")
    values = {field: record.get(field) for field in VALUE_FIELDS}
    for field, value in values.items():
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        ):
            raise WeatherContractError(f"{field} must be a finite number or null")
    has_value = any(value is not None for value in values.values())
    identity = "|".join((lineage, kind, str(longitude), str(latitude),
                         valid_at.isoformat(), fetched_at.isoformat()))
    record_id = "open-meteo:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    output = {
        "schema_version": CANONICAL_SCHEMA,
        "record_id": record_id,
        "record_kind": kind,
        "status": "available" if has_value else "unavailable",
        "source": {"name": source, "authority": None},
        "source_lineage": lineage,
        "spatial_footprint": {"type": "Point", "coordinates": [longitude, latitude]},
        "observed_at": None,  # Open-Meteo model times are not sensor observations.
        "valid_at": valid_at.isoformat(),
        "issued_at": None,
        "event_time": None,
        "fetched_at": fetched_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "value": values if has_value else None,
        "quality_flags": flags if has_value else sorted(set(flags + ["missing"])),
        "severity": None,
    }
    if not has_value:
        output["error_code"] = "WEATHER_VALUES_MISSING"
    return output
