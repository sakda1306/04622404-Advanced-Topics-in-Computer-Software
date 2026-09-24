"""Boundary tests for GDACS disaster records; all events are synthetic."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import URLError

import gdacs_adapter
from gdacs_adapter import fetch_canonical_disasters, to_canonical_disasters


NOW = datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


def event(country, lon, lat, *, event_id=1, fromdate="2026-09-20T05:00:00Z"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "eventid": event_id,
            "eventtype": "FL",
            "episodeid": 1,
            "country": country,
            "alertlevel": "Red",
            "fromdate": fromdate,
            "todate": "2026-09-21T05:00:00Z",
            "name": "Synthetic flood",
        },
    }


class GDACSAdapterTests(unittest.TestCase):
    def test_thai_event_has_traceable_source_and_severity(self):
        payload = {
            "type": "FeatureCollection",
            "features": [event("Thailand", 100.5, 13.5)],
        }

        records = to_canonical_disasters(
            payload, source_url=SOURCE_URL, fetched_at=NOW
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_kind"], "disaster_event")
        self.assertEqual(record["severity"], "HIGH")
        self.assertEqual(
            record["spatial_footprint"],
            {"type": "Point", "coordinates": [100.5, 13.5]},
        )
        self.assertEqual(record["source_lineage"], SOURCE_URL)
        self.assertEqual(record["event_time"], "2026-09-20T05:00:00+00:00")

    def test_event_outside_thailand_is_excluded(self):
        payload = {
            "type": "FeatureCollection",
            "features": [event("Brazil", -50.0, -10.0)],
        }

        records = to_canonical_disasters(
            payload, source_url=SOURCE_URL, fetched_at=NOW
        )

        self.assertEqual(records, [])

    def test_time_without_timezone_is_marked_incomplete(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                event(
                    "Thailand",
                    100.5,
                    13.5,
                    fromdate="2026-09-20T05:00:00",
                )
            ],
        }

        record = to_canonical_disasters(
            payload, source_url=SOURCE_URL, fetched_at=NOW
        )[0]

        self.assertIsNone(record["event_time"])
        self.assertIn("incomplete", record["quality_flags"])

    def test_provider_failure_has_no_invented_event(self):
        with patch.object(
            gdacs_adapter, "urlopen", side_effect=URLError("offline")
        ):
            records = fetch_canonical_disasters(now=NOW)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_UNAVAILABLE")
        self.assertIsNone(records[0]["value"])
        self.assertIsNone(records[0]["severity"])

    def test_disaster_provider_env_routes_to_thai_adapter(self):
        with patch.dict(gdacs_adapter.os.environ, {"DISASTER_PROVIDER": "thai"}):
            with patch("thai_disaster_adapter.fetch_canonical_disasters", return_value=[{"record_id": "mock-thai", "status": "available"}]) as mock_thai:
                records = fetch_canonical_disasters(now=NOW)
                mock_thai.assert_called_once_with(now=NOW)
                self.assertEqual(records, [{"record_id": "mock-thai", "status": "available"}])


if __name__ == "__main__":
    unittest.main()