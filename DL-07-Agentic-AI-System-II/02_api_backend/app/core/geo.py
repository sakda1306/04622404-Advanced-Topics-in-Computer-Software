"""Geographic helpers (WGS84)."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash_encode(lat: float, lon: float, precision: int) -> str:
    """Standard base32 geohash; used to coarsen locations for keys and analytics."""
    if not 1 <= precision <= 12:
        raise ValueError("precision must be between 1 and 12")
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    chars: list[str] = []
    bits = bit_count = 0
    use_lon = True
    while len(chars) < precision:
        bounds, value = (lon_range, lon) if use_lon else (lat_range, lat)
        mid = (bounds[0] + bounds[1]) / 2
        bits <<= 1
        if value >= mid:
            bits |= 1
            bounds[0] = mid
        else:
            bounds[1] = mid
        use_lon = not use_lon
        bit_count += 1
        if bit_count == 5:
            chars.append(_BASE32[bits])
            bits = bit_count = 0
    return "".join(chars)
