"""Fetch driving routes and convert them to Module 03 RouteCandidate data.

Coordinates received from Module 03 are (latitude, longitude).
GeoJSON coordinates returned to Module 03 are [longitude, latitude].
"""

from __future__ import annotations

import json
import math
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class RouteProviderError(RuntimeError):
    """The routing service could not be reached or returned an error."""


class RouteDataError(ValueError):
    """The routing service returned data that cannot form a valid route."""


def _coordinate(value: object, minimum: float, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise RouteDataError("Invalid route coordinate")
    return float(value)


def _location(location: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(location, (tuple, list)) or len(location) != 2:
        raise ValueError("Location must be (latitude, longitude)")

    latitude = _coordinate(location[0], -90, 90)
    longitude = _coordinate(location[1], -180, 180)
    return latitude, longitude


def _number(value: object, field: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (positive and value <= 0)
        or (not positive and value < 0)
    ):
        raise RouteDataError(f"Invalid OSRM {field}")
    return float(value)


def to_route_candidates(response: dict) -> list[dict]:
    """Convert an OSRM response into Module 03's RouteCandidate shape."""
    if not isinstance(response, dict) or response.get("code") != "Ok":
        raise RouteDataError("OSRM did not return a successful route")

    routes = response.get("routes")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 10:
        raise RouteDataError("OSRM must return between 1 and 10 routes")

    candidates = []

    for index, route in enumerate(routes, start=1):
        if not isinstance(route, dict):
            raise RouteDataError("Invalid OSRM route")

        geometry = route.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            raise RouteDataError("OSRM route needs GeoJSON LineString geometry")

        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise RouteDataError("OSRM route needs at least two coordinates")

        clean_coordinates = []
        for point in coordinates:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise RouteDataError("Invalid OSRM route point")
            longitude = _coordinate(point[0], -180, 180)
            latitude = _coordinate(point[1], -90, 90)
            clean_coordinates.append([longitude, latitude])

        # A request with only origin and destination has one OSRM leg.
        # That leg covers the complete GeoJSON line.
        legs = route.get("legs")
        if not isinstance(legs, list) or len(legs) != 1:
            raise RouteDataError("Expected one OSRM leg for two locations")

        leg = legs[0]
        if not isinstance(leg, dict):
            raise RouteDataError("Invalid OSRM leg")

        duration_seconds = _number(
            leg.get("duration"), "leg duration", positive=True
        )
        distance_metres = _number(route.get("distance"), "route distance")

        candidates.append(
            {
                "route_id": f"osrm-route-{index}",
                "label": None,
                "travel_modes": ["CAR"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": clean_coordinates,
                },
                "legs": [
                    {
                        "start_index": 0,
                        "end_index": len(clean_coordinates) - 1,
                        "duration_minutes": duration_seconds / 60,
                        "mode": "CAR",
                    }
                ],
                "distance_km": distance_metres / 1000,
            }
        )

    return candidates


def fetch_route_candidates(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    base_url: str,
) -> list[dict]:
    """Fetch actual driving routes from a configured HTTPS OSRM server."""
    origin_lat, origin_lon = _location(origin)
    destination_lat, destination_lon = _location(destination)

    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.path not in ("", "/")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError("base_url must be an HTTPS server address")

    coordinates = (
        f"{origin_lon},{origin_lat};"
        f"{destination_lon},{destination_lat}"
    )
    options = urlencode(
        {
            "alternatives": "3",
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }
    )
    request_url = (
        f"{base_url.rstrip('/')}/route/v1/driving/"
        f"{coordinates}?{options}"
    )
    request = Request(
        request_url,
        headers={"User-Agent": "Team-D-travel-project/0.1"},
    )

    try:
        with urlopen(request, timeout=10) as reply:
            response = json.load(reply)
    except HTTPError as error:
        raise RouteProviderError(f"OSRM HTTP {error.code}") from error
    except (TimeoutError, socket.timeout) as error:
        raise RouteProviderError("OSRM timeout") from error
    except URLError as error:
        raise RouteProviderError("OSRM network error") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RouteDataError("OSRM returned invalid JSON") from error

    return to_route_candidates(response)