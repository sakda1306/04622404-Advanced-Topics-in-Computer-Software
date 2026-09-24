"""TomTom transport boundaries; all provider records are synthetic."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import URLError

import tomtom_transport
from tomtom_transport import fetch_canonical_transport, to_canonical_transport


NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
BBOX = (100.0, 13.0, 100.1, 13.1)


def incident():
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[100.0, 13.0], [100.1, 13.0]],
        },
        "properties": {
            "id": "fixture-incident",
            "iconCategory": "roadClosed",
            "magnitudeOfDelay": "undefined",
            "startTime": "2026-09-19T00:00:00Z",
            "endTime": "2026-09-21T00:00:00Z",
            "lastReportTime": "2026-09-19T23:55:00Z",
            "delayInSeconds": 150,
            "timeValidity": "present",
            "events": [{"description": "Road closed"}],
        },
    }


class TomTomTransportTests(unittest.TestCase):
    def test_closure_preserves_provider_line_without_claiming_official_alert(self):
        records = to_canonical_transport(
            {"incidents": [incident()]},
            source_url="https://api.tomtom.com/maps/orbis/traffic/incidents/details?apiVersion=2",
            fetched_at=NOW,
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_kind"], "transport_status")
        self.assertEqual(record["spatial_footprint"]["type"], "LineString")
        self.assertEqual(record["value"]["status"], "CLOSED")
        self.assertEqual(record["value"]["delay_minutes"], 2.5)
        self.assertEqual(record["severity"], "HIGH")
        self.assertEqual(record["observed_at"], "2026-09-19T23:55:00+00:00")
        self.assertNotIn("key=", record["source_lineage"])

    def test_missing_key_returns_unavailable_without_calling_provider(self):
        with patch.dict(tomtom_transport.os.environ, {}, clear=True):
            with patch.object(tomtom_transport, "urlopen") as request:
                records = fetch_canonical_transport(BBOX, now=NOW)

        request.assert_not_called()
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_NOT_CONFIGURED")
        self.assertIsNone(records[0]["value"])

    def test_provider_failure_has_no_invented_incident(self):
        with patch.object(
            tomtom_transport, "urlopen", side_effect=URLError("offline")
        ):
            records = fetch_canonical_transport(BBOX, now=NOW, api_key="fixture")

        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_UNAVAILABLE")
        self.assertIsNone(records[0]["value"])
        self.assertIsNone(records[0]["severity"])

    def test_oversized_bbox_is_rejected_before_network_call(self):
        with patch.object(tomtom_transport, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "10,000 km2"):
                fetch_canonical_transport((97.0, 5.0, 106.0, 21.0), now=NOW)

        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()