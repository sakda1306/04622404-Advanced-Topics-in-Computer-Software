"""Convert Longdo Traffic / iTIC incident events to Module 05 transport records.

Provides real-time road closures, floodings, accidents, and traffic incidents in Thailand.
Conforms to schema canonical-record-v0.1-proposed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA = "canonical-record-v0.1-proposed"
ENDPOINT = "https://event.longdo.com/feed/json"
TTL = timedelta(minutes=10)
BANGKOK_TZ = timezone(timedelta(hours=7))

# Mapping Longdo event types to (canonical category, severity, status)
EVENT_TYPE_INFO: dict[str, tuple[str, str, str]] = {
    "1": ("carBreakDown", "LOW", "INCIDENT"),
    "2": ("construction", "LOW", "INCIDENT"),
    "3": ("accident", "MEDIUM", "INCIDENT"),
    "5": ("rain", "LOW", "INCIDENT"),
    "6": ("flood", "HIGH", "INCIDENT"),
    "7": ("crowd", "MEDIUM", "INCIDENT"),
    "8": ("information", "LOW", "INCIDENT"),
    "9": ("checkPoint", "LOW", "INCIDENT"),
    "10": ("trafficjam", "LOW", "INCIDENT"),
    "11": ("misc", "LOW", "INCIDENT"),
    "12": ("warning", "MEDIUM", "INCIDENT"),
    "13": ("event", "LOW", "INCIDENT"),
    "14": ("sale", "LOW", "INCIDENT"),
    "15": ("fire", "HIGH", "INCIDENT"),
    "16": ("complaint", "LOW", "INCIDENT"),
    "18": ("diversion", "LOW", "INCIDENT"),
    "19": ("roadClosed", "HIGH", "CLOSED"),
    "20": ("earthquake", "HIGH", "INCIDENT"),
}


class LongdoTransportDataError(ValueError):
    """The provider response cannot safely be converted."""


def _parse_bangkok_time(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    val = value.strip()
    try:
        # Longdo format: "YYYY-MM-DD HH:MM:SS"
        dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BANGKOK_TZ)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BANGKOK_TZ)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _bbox(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("bbox must be (min_lon, min_lat, max_lon, max_lat)")
    west, south, east, north = map(float, value)
    if not all(map(math.isfinite, (west, south, east, north))):
        raise ValueError("bbox must contain finite numbers")
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("bbox bounds are invalid")
    return west, south, east, north


def _unavailable(now: datetime, bbox: tuple[float, ...], code: str) -> dict:
    identity = f"{bbox}|{now.isoformat()}|{code}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": SCHEMA,
        "record_id": f"longdo:check:{suffix}",
        "record_kind": "transport_status",
        "status": "unavailable",
        "error_code": code,
        "source": {"name": "Longdo Traffic (iTIC)", "authority": "iTIC / สวพ.91 / จส.100"},
        "source_lineage": ENDPOINT,
        "spatial_footprint": None,
        "observed_at": now.isoformat(),
        "valid_at": None,
        "issued_at": None,
        "event_time": None,
        "fetched_at": now.isoformat(),
        "expires_at": (now + TTL).isoformat(),
        "severity": None,
        "quality_flags": ["provider_unavailable"],
        "value": None,
    }


def to_canonical_transport(
    payload: object,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    source_url: str = ENDPOINT,
    fetched_at: datetime,
) -> list[dict]:
    """Convert raw Longdo events JSON array to canonical transport records filtered by bbox."""
    if not isinstance(payload, list):
        raise LongdoTransportDataError("Longdo feed must return a JSON array")

    bounds = _bbox(bbox) if bbox is not None else None
    # Add a generous tolerance padding (~0.1 degree ≈ 11 km) around the bbox
    padding = 0.1
    min_lon = bounds[0] - padding if bounds else -180.0
    min_lat = bounds[1] - padding if bounds else -90.0
    max_lon = bounds[2] + padding if bounds else 180.0
    max_lat = bounds[3] + padding if bounds else 90.0

    records: list[dict] = []
    seen: set[str] = set()

    for item in payload:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("eid") or "").strip()
        if not eid:
            continue
        record_id = f"longdo:{eid}"
        if record_id in seen:
            continue
        seen.add(record_id)

        try:
            lat = float(item.get("latitude"))
            lon = float(item.get("longitude"))
        except (TypeError, ValueError):
            continue

        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue

        # Spatial filter: keep incidents that fall within the query bounding box
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue

        event_type_str = str(item.get("type", "")).strip()
        category, severity, status = EVENT_TYPE_INFO.get(
            event_type_str, ("incident", "LOW", "INCIDENT")
        )

        title = str(item.get("title") or item.get("title_en") or "Traffic Event").strip()
        description = str(item.get("description") or item.get("description_en") or title).strip()
        contributor = str(item.get("contributor") or "").strip() or None

        start_utc = _parse_bangkok_time(item.get("start"))
        stop_utc = _parse_bangkok_time(item.get("stop"))

        # Event is active right now in live feed
        records.append(
            {
                "schema_version": SCHEMA,
                "record_id": record_id,
                "record_kind": "transport_status",
                "status": "available",
                "source": {
                    "name": "Longdo Traffic (iTIC)",
                    "authority": contributor or "iTIC / สวพ.91 / จส.100",
                },
                "source_lineage": source_url,
                "spatial_footprint": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "observed_at": fetched_at.isoformat(),
                "valid_at": None,
                "issued_at": start_utc or fetched_at.isoformat(),
                "event_time": start_utc or fetched_at.isoformat(),
                "fetched_at": fetched_at.isoformat(),
                "expires_at": (fetched_at + TTL).isoformat(),
                "severity": severity,
                "quality_flags": [],
                "value": {
                    "status": status,
                    "category": category,
                    "title": title,
                    "description": description,
                    "starts_at": start_utc,
                    "ends_at": stop_utc,
                    "time_validity": "present",
                    "contributor": contributor,
                    "event_type_id": event_type_str,
                },
            }
        )

    return records


def fetch_canonical_transport(
    bbox: tuple[float, float, float, float],
    *,
    now: datetime | None = None,
    api_key: str | None = None,
    endpoint: str = ENDPOINT,
) -> list[dict]:
    """Fetch present road incidents in Thailand from Longdo Traffic feed filtered by bbox."""
    bounds = _bbox(bbox)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)

    url = endpoint
    key = api_key if api_key is not None else os.getenv("LONGDO_API_KEY")
    if key:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}key={key}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Team-D-travel-project/0.1",
        },
    )

    try:
        with urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except HTTPError as error:
        code = "PROVIDER_AUTH_FAILED" if error.code in (401, 403) else "PROVIDER_HTTP_ERROR"
        return [_unavailable(now, bounds, code)]
    except (URLError, TimeoutError, socket.timeout):
        return [_unavailable(now, bounds, "PROVIDER_UNAVAILABLE")]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [_unavailable(now, bounds, "PROVIDER_DATA_INVALID")]

    try:
        return to_canonical_transport(payload, bbox=bounds, source_url=url, fetched_at=now)
    except LongdoTransportDataError:
        return [_unavailable(now, bounds, "PROVIDER_DATA_INVALID")]
