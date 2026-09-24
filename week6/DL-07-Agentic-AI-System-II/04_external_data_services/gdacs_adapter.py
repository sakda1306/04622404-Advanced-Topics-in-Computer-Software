"""Read GDACS GeoJSON and produce Module 05 disaster records."""

from __future__ import annotations

import json
import math
import os
import re
import socket
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = "canonical-record-v0.1-proposed"
SEARCH_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
CACHE_TTL = timedelta(minutes=30)
PAGE_SIZE = 100
MAX_PAGES = 10
ALERT_SEVERITY = {"green": "LOW", "orange": "MEDIUM", "red": "HIGH"}


class GDACSDataError(ValueError):
    """GDACS returned an unusable response."""


def _aware_utc(value: object) -> str | None:
    """Keep source time only when its timezone is explicit."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _point(geometry: object) -> dict | None:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        return None
    lon, lat = coordinates[:2]
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
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}


def _relevant_to_thailand(properties: dict, geometry: object) -> bool:
    country_text = " ".join(
        str(properties.get(key) or "")
        for key in ("country", "countryname", "iso2", "iso3", "countries")
    )
    if re.search(r"\b(thailand|tha|th)\b", country_text, re.IGNORECASE):
        return True

    point = _point(geometry)
    if point is None:
        return False
    lon, lat = point["coordinates"]
    return 97.0 <= lon <= 106.0 and 5.0 <= lat <= 21.0


def to_canonical_disasters(
    payload: object, *, source_url: str, fetched_at: datetime
) -> list[dict]:
    """Convert GDACS events without claiming a Thai government restriction."""
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must have a timezone")
    fetched_at = fetched_at.astimezone(timezone.utc)

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise GDACSDataError("GDACS response must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise GDACSDataError("GDACS features must be a list")

    records = []
    seen_ids = set()

    for feature in features:
        if not isinstance(feature, dict) or not isinstance(
            feature.get("properties"), dict
        ):
            raise GDACSDataError("GDACS feature has no properties")

        properties = feature["properties"]
        geometry = feature.get("geometry")
        if not _relevant_to_thailand(properties, geometry):
            continue

        event_id = properties.get("eventid")
        event_type = properties.get("eventtype")
        episode_id = properties.get("episodeid")
        if (
            not isinstance(event_id, (str, int))
            or isinstance(event_id, bool)
            or not isinstance(event_type, str)
            or not event_type.isalnum()
            or (
                episode_id is not None
                and (
                    not isinstance(episode_id, (str, int))
                    or isinstance(episode_id, bool)
                )
            )
        ):
            raise GDACSDataError("GDACS event identity is missing or invalid")

        record_id = f"gdacs:{event_type}:{event_id}:{episode_id or 0}"
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)

        if isinstance(geometry, dict) and geometry.get("type") == "Point":
            footprint = _point(geometry)
        elif isinstance(geometry, dict):
            footprint = geometry
        else:
            footprint = None

        event_time = _aware_utc(properties.get("fromdate"))
        alert_level = properties.get("alertlevel")
        severity = (
            ALERT_SEVERITY.get(alert_level.lower())
            if isinstance(alert_level, str)
            else None
        )
        flags = []
        if footprint is None or event_time is None or severity is None:
            flags.append("incomplete")

        records.append(
            {
                "schema_version": SCHEMA,
                "record_id": record_id,
                "record_kind": "disaster_event",
                "status": "available",
                "source": {
                    "name": "Global Disaster Alert and Coordination System, GDACS",
                    "authority": "GDACS",
                },
                "source_lineage": source_url,
                "spatial_footprint": footprint,
                "observed_at": None,
                "valid_at": None,
                "issued_at": _aware_utc(properties.get("datemodified")),
                "event_time": event_time,
                "fetched_at": fetched_at.isoformat(),
                "expires_at": (fetched_at + CACHE_TTL).isoformat(),
                "severity": severity,
                "quality_flags": flags,
                "value": {
                    "event_type": event_type,
                    "name": properties.get("name")
                    or properties.get("eventname"),
                    "alert_level": alert_level,
                    "country": properties.get("country"),
                    "starts_at": properties.get("fromdate"),
                    "ends_at": properties.get("todate"),
                    "description": properties.get("description"),
                },
            }
        )
    return records


def _unavailable(fetched_at: datetime, code: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "record_id": f"gdacs:check:{fetched_at.timestamp():.0f}",
        "record_kind": "disaster_event",
        "status": "unavailable",
        "source": {
            "name": "Global Disaster Alert and Coordination System, GDACS",
            "authority": "GDACS",
        },
        "source_lineage": None,
        "spatial_footprint": None,
        "observed_at": None,
        "valid_at": None,
        "issued_at": None,
        "event_time": None,
        "fetched_at": fetched_at.isoformat(),
        "expires_at": None,
        "severity": None,
        "quality_flags": ["unavailable"],
        "value": None,
        "error_code": code,
    }


def _fetch_gdacs(now: datetime) -> list[dict]:
    records = []
    seen_ids = set()
    for page in range(1, MAX_PAGES + 1):
        params = urlencode(
            {
                "fromdate": (now - timedelta(days=4)).date().isoformat(),
                "todate": now.date().isoformat(),
                "eventlist": "EQ;TC;FL;VO;WF;DR",
                "alertlevel": "red;orange;green",
                "pagesize": PAGE_SIZE,
                "pagenumber": page,
            }
        )
        request_url = f"{SEARCH_URL}?{params}"
        request = Request(
            request_url,
            headers={"User-Agent": "Team-D-travel-project/0.1"},
        )

        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except HTTPError:
            return [_unavailable(now, "PROVIDER_HTTP_ERROR")]
        except (URLError, TimeoutError, socket.timeout):
            return [_unavailable(now, "PROVIDER_UNAVAILABLE")]
        except (json.JSONDecodeError, UnicodeDecodeError):
            return [_unavailable(now, "PROVIDER_DATA_INVALID")]

        try:
            page_records = to_canonical_disasters(
                payload, source_url=request_url, fetched_at=now
            )
        except GDACSDataError:
            return [_unavailable(now, "PROVIDER_DATA_INVALID")]

        for record in page_records:
            if record["record_id"] not in seen_ids:
                records.append(record)
                seen_ids.add(record["record_id"])

        if len(payload["features"]) < PAGE_SIZE:
            return records

    return [_unavailable(now, "PROVIDER_RESULT_LIMIT")]


def fetch_canonical_disasters(*, now: datetime | None = None) -> list[dict]:
    """Fetch recent events from configured provider (Thai provider or GDACS)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must have a timezone")
    now = now.astimezone(timezone.utc)

    provider = os.getenv("DISASTER_PROVIDER", "gdacs").lower()

    if provider in ("thai", "dpm", "tmd"):
        try:
            from thai_disaster_adapter import fetch_canonical_disasters as fetch_thai
            return fetch_thai(now=now)
        except Exception:
            return _fetch_gdacs(now)

    if provider in ("both", "all", "merged"):
        results = []
        try:
            from thai_disaster_adapter import fetch_canonical_disasters as fetch_thai
            thai_records = fetch_thai(now=now)
            results.extend([r for r in thai_records if r.get("status") == "available"])
        except Exception:
            pass

        gdacs_records = _fetch_gdacs(now)
        results.extend([r for r in gdacs_records if r.get("status") == "available"])
        if results:
            return results
        if not any(r.get("status") == "unavailable" for r in gdacs_records):
            return []
        return gdacs_records

    return _fetch_gdacs(now)