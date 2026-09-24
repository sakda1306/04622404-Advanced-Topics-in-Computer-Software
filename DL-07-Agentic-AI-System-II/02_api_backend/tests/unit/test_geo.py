from __future__ import annotations

import pytest

from app.core.geo import geohash_encode


@pytest.mark.parametrize(
    ("lat", "lon", "precision", "expected"),
    [
        (57.64911, 10.40744, 11, "u4pruydqqvj"),  # reference example of the algorithm
        (42.605, -5.603, 5, "ezs42"),
        (-90.0, -180.0, 3, "000"),
        (90.0, 180.0, 3, "zzz"),
    ],
)
def test_geohash_encode(lat: float, lon: float, precision: int, expected: str) -> None:
    assert geohash_encode(lat, lon, precision) == expected


@pytest.mark.parametrize("precision", [0, 13])
def test_geohash_precision_is_bounded(precision: int) -> None:
    with pytest.raises(ValueError, match="precision"):
        geohash_encode(0.0, 0.0, precision)
