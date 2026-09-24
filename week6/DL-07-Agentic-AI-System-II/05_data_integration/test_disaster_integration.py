"""Route and time boundary tests for Module 05 disaster evidence."""

import unittest
from datetime import datetime, timezone

from integration import build_context


NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)


def route_query():
    return {
        "run_id": "disaster-fixture",
        "routes": [
            {
                "route_id": "route-1",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100.0, 13.0], [100.1, 13.0]],
                },
                "segments": [
                    {
                        "start_index": 0,
                        "end_index": 1,
                        "enter_at": "2026-09-20T08:00:00+07:00",
                        "exit_at": "2026-09-20T08:20:00+07:00",
                    }
                ],
            }
        ],
    }


def disaster(record_id, longitude, ends_at, *, starts_at="2026-09-19T00:00:00Z"):
    return {
        "schema_version": "canonical-record-v0.1-proposed",
        "record_id": record_id,
        "record_kind": "disaster_event",
        "status": "available",
        "source": {"name": "synthetic GDACS fixture", "authority": "GDACS"},
        "source_lineage": "https://www.gdacs.org/example",
        "spatial_footprint": {
            "type": "Point",
            "coordinates": [longitude, 13.0],
        },
        "observed_at": None,
        "valid_at": None,
        "event_time": "2026-09-19T00:00:00Z",
        "fetched_at": "2026-09-20T00:00:00Z",
        "expires_at": "2026-09-20T00:30:00Z",
        "severity": "HIGH",
        "quality_flags": [],
        "value": {"starts_at": starts_at, "ends_at": ends_at},
    }


class DisasterIntegrationTests(unittest.TestCase):
    def test_only_active_nearby_disaster_reaches_risk_evidence(self):
        records = [
            disaster("active-near", 100.05, "2026-09-21T00:00:00Z"),
            disaster("active-far", 101.0, "2026-09-21T00:00:00Z"),
            disaster("ended-near", 100.05, "2026-09-19T12:00:00Z"),
        ]

        context = build_context(route_query(), records, now=NOW)
        segment = context["routes"][0]["segments"][0]

        self.assertEqual(
            segment["matched_record_ids"]["disaster_event"], ["active-near"]
        )
        self.assertEqual(
            [item["record_id"] for item in context["evidence"]], ["active-near"]
        )
        self.assertEqual(
            {item["record_id"] for item in context["unmatched_evidence"]},
            {"active-far", "ended-near"},
        )

    def test_interval_without_timezone_is_not_assumed_to_match(self):
        record = disaster(
            "unknown-time",
            100.05,
            "2026-09-21T00:00:00Z",
            starts_at="2026-09-19T00:00:00",
        )

        context = build_context(route_query(), [record], now=NOW)

        self.assertEqual(context["evidence"], [])
        self.assertEqual(
            [item["record_id"] for item in context["unmatched_evidence"]],
            ["unknown-time"],
        )


if __name__ == "__main__":
    unittest.main()