"""Convert TomTom Orbis traffic incidents to Module 05 transport records.

Road closures reported by TomTom remain transport_status, not official_alert.
The API key is read from TOMTOM_API_KEY and never included in source_lineage.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = "canonical-record-v0.1-proposed"
ENDPOINT = "https://api.tomtom.com/maps/orbis/traffic/incidents/details"
TTL = timedelta(minutes=5)
ATTRIBUTES = (
    "incidents(type,geometry(type,coordinates),properties("
    "id,iconCategory,magnitudeOfDelay,events(description),"
    "startTime,endTime,delayInSeconds,timeValidity,lastReportTime,"
    "probabilityOfOccurrence))"
)
SEVERITY = {"minor": "LOW", "moderate": "MEDIUM", "major": "HIGH"}


class TransportDataError(ValueError):
    """The provider response cannot safely be converted."""


def _aware_utc(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _point(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    lon, lat = value[:2]
    if (
        isinstance(lon, bool)
        or isinstance(lat, bool)
        or not isinstance(lon, (int, float))
        or not isinstance(lat, (int, float))
        or not math.isfinite(lon)
        or not math.isfinite(lat)
        or not -180 <= lon <= 180
        or not -90 <= lat <= 90
    ):
        return None
    return [float(lon), float(lat)]


def _geometry(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if value.get("type") == "Point":
        point = _point(value.get("coordinates"))
        return {"type": "Point", "coordinates": point} if point else None
    if value.get("type") == "LineString":
        raw = value.get("coordinates")
        if not isinstance(raw, list) or len(raw) < 2:
            return None
        points = [_point(item) for item in raw]
        if any(item is None for item in points):
            return None
        return {"type": "LineString", "coordinates": points}
    return None


def _bbox(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("bbox must be (min_lon, min_lat, max_lon, max_lat)")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise ValueError("bbox must contain numbers")
    west, south, east, north = map(float, value)
    if not all(map(math.isfinite, (west, south, east, north))):
        raise ValueError("bbox must contain finite numbers")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox longitude/latitude bounds are invalid")
    width_km = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
    height_km = (north - south) * 111.32
    if width_km * height_km > 10_000:
        raise ValueError("bbox exceeds TomTom's 10,000 km2 limit")
    return west, south, east, north


def _unavailable(now: datetime, bbox: tuple[float, ...], code: str) -> dict:
    identity = f"{bbox}|{now.isoformat()}|{code}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": SCHEMA,
        "record_id": f"tomtom:check:{suffix}",
        "record_kind": "transport_status",
        "status": "unavailable",
        "source": {"name": "TomTom Orbis Traffic", "authority": None},
        "source_lineage": None,
        "spatial_footprint": None,
        "observed_at": None,
        "valid_at": None,
        "issued_at": None,
        "event_time": None,
        "fetched_at": now.isoformat(),
        "expires_at": None,
        "severity": None,
        "quality_flags": ["unavailable"],
        "value": None,
        "error_code": code,
    }


def to_canonical_transport(
    payload: object, *, source_url: str, fetched_at: datetime
) -> list[dict]:
    """Convert Orbis v2 incidents; an empty list means no incident was reported."""
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must include a timezone")
    fetched_at = fetched_at.astimezone(timezone.utc)
    if not isinstance(payload, dict) or not isinstance(payload.get("incidents"), list):
        raise TransportDataError("response must contain an incidents list")

    records = []
    seen = set()
    for incident in payload["incidents"]:
        if not isinstance(incident, dict) or not isinstance(incident.get("properties"), dict):
            raise TransportDataError("incident properties are missing")
        properties = incident["properties"]
        incident_id = properties.get("id")
        if not isinstance(incident_id, str) or not incident_id:
            raise TransportDataError("incident id is missing")
        record_id = f"tomtom:{incident_id}"
        if record_id in seen:
            continue
        seen.add(record_id)

        footprint = _geometry(incident.get("geometry"))
        start = _aware_utc(properties.get("startTime"))
        end = _aware_utc(properties.get("endTime"))
        reported = _aware_utc(properties.get("lastReportTime"))
        if reported and datetime.fromisoformat(reported) > fetched_at:
            reported = None
        delay_seconds = properties.get("delayInSeconds")
        if delay_seconds is not None and (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(delay_seconds)
            or delay_seconds < 0
        ):
            raise TransportDataError("delayInSeconds must be non-negative")
        magnitude = properties.get("magnitudeOfDelay")
        category = properties.get("iconCategory")
        if magnitude is not None and not isinstance(magnitude, str):
            raise TransportDataError("magnitudeOfDelay must be a string")
        if category is not None and not isinstance(category, str):
            raise TransportDataError("iconCategory must be a string")
        severity = SEVERITY.get(magnitude)
        if category == "roadClosed":
            severity = "HIGH"
        events = properties.get("events")
        descriptions = (
            [item.get("description") for item in events if isinstance(item, dict)]
            if isinstance(events, list)
            else []
        )
        description = next(
            (item for item in descriptions if isinstance(item, str) and item), None
        )
        flags = []
        if footprint is None or start is None:
            flags.append("incomplete")
        if properties.get("probabilityOfOccurrence") not in (None, "certain"):
            flags.append("uncertain")

        records.append(
            {
                "schema_version": SCHEMA,
                "record_id": record_id,
                "record_kind": "transport_status",
                "status": "available",
                "source": {"name": "TomTom Orbis Traffic", "authority": None},
                "source_lineage": source_url,
                "spatial_footprint": footprint,
                "observed_at": reported,
                "valid_at": None,
                "issued_at": None,
                "event_time": start,
                "fetched_at": fetched_at.isoformat(),
                "expires_at": (fetched_at + TTL).isoformat(),
                "severity": severity,
                "quality_flags": flags,
                "value": {
                    "status": "CLOSED" if category == "roadClosed" else "INCIDENT",
                    "category": category,
                    "description": description,
                    "magnitude_of_delay": magnitude,
                    "delay_minutes": (
                        delay_seconds / 60 if delay_seconds is not None else None
                    ),
                    "starts_at": start,
                    "ends_at": end,
                    "time_validity": properties.get("timeValidity"),
                },
            }
        )
    return records


def fetch_canonical_transport(
    bbox: tuple[float, float, float, float],
    *,
    now: datetime | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Fetch present road incidents inside a supported bbox."""
    bounds = _bbox(bbox)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)
    key = api_key if api_key is not None else os.getenv("TOMTOM_API_KEY")
    if not key:
        return [_unavailable(now, bounds, "PROVIDER_NOT_CONFIGURED")]

    params = urlencode(
        {
            "apiVersion": 2,
            "bbox": ",".join(str(item) for item in bounds),
            "timeValidity": "present",
        }
    )
    request_url = f"{ENDPOINT}?{params}"
    request = Request(
        request_url,
        headers={
            "TomTom-Api-Key": key,
            "Attributes": ATTRIBUTES,
            "Accept-Language": "en-GB",
            "User-Agent": "Team-D-travel-project/0.1",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except HTTPError as error:
        code = "PROVIDER_AUTH_FAILED" if error.code in (401, 403) else "PROVIDER_HTTP_ERROR"
        return [_unavailable(now, bounds, code)]
    except (URLError, TimeoutError, socket.timeout):
        return [_unavailable(now, bounds, "PROVIDER_UNAVAILABLE")]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [_unavailable(now, bounds, "PROVIDER_DATA_INVALID")]
    try:
        return to_canonical_transport(payload, source_url=request_url, fetched_at=now)
    except TransportDataError:
        return [_unavailable(now, bounds, "PROVIDER_DATA_INVALID")]
