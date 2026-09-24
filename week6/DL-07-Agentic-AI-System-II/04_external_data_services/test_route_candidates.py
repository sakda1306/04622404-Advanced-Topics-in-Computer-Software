"""Tests for Module 04 route conversion; all route data is synthetic."""

import unittest

from route_candidates import RouteDataError, to_route_candidates


def osrm_response():
    return {
        "code": "Ok",
        "routes": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100.0, 13.0], [100.1, 13.1]],
                },
                "legs": [{"duration": 1200}],
                "distance": 5000,
            }
        ],
    }


class RouteCandidatesTests(unittest.TestCase):
    def test_converts_provider_units_and_geometry(self):
        candidate = to_route_candidates(osrm_response())[0]

        self.assertEqual(candidate["geometry"]["coordinates"][0], [100.0, 13.0])
        self.assertEqual(candidate["legs"][0]["start_index"], 0)
        self.assertEqual(candidate["legs"][0]["end_index"], 1)
        self.assertEqual(candidate["legs"][0]["duration_minutes"], 20)
        self.assertEqual(candidate["distance_km"], 5)

    def test_rejects_missing_travel_time(self):
        response = osrm_response()
        response["routes"][0]["legs"][0].pop("duration")

        with self.assertRaises(RouteDataError):
            to_route_candidates(response)

    def test_rejects_invalid_geometry(self):
        response = osrm_response()
        response["routes"][0]["geometry"]["coordinates"] = [[100.0, 13.0]]

        with self.assertRaises(RouteDataError):
            to_route_candidates(response)


if __name__ == "__main__":
    unittest.main()