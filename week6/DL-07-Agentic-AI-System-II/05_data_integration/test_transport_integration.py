"""Synthetic route and time boundaries for transport incident lines."""

import unittest
from datetime import datetime, timezone

from integration import ContractError, build_context


NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)


def route_query():
    return {
        "run_id": "transport-fixture",
        "routes": [
            {
                "route_id": "route-1",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100.0, 13.0], [100.2, 13.0]],
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


def incident(record_id, coordinates, ends_at):
    return {
        "schema_version": "canonical-record-v0.1-proposed",
        "record_id": record_id,
        "record_kind": "transport_status",
        "status": "available",
        "source": {"name": "synthetic traffic provider", "authority": None},
        "source_lineage": "https://example.org/incident",
        "spatial_footprint": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "observed_at": None,
        "valid_at": None,
        "event_time": "2026-09-19T00:00:00Z",
        "fetched_at": "2026-09-20T00:00:00Z",
        "expires_at": "2026-09-20T00:30:00Z",
        "severity": "HIGH",
        "quality_flags": [],
        "value": {
            "status": "CLOSED",
            "starts_at": "2026-09-19T00:00:00Z",
            "ends_at": ends_at,
        },
    }


class TransportIntegrationTests(unittest.TestCase):
    def test_crossing_line_matches_even_when_endpoints_are_far(self):
        records = [
            incident(
                "crossing", [[100.1, 12.9], [100.1, 13.1]],
                "2026-09-21T00:00:00Z",
            ),
            incident(
                "distant", [[100.0, 13.05], [100.2, 13.05]],
                "2026-09-21T00:00:00Z",
            ),
            incident(
                "ended", [[100.1, 12.9], [100.1, 13.1]],
                "2026-09-19T12:00:00Z",
            ),
        ]

        context = build_context(route_query(), records, now=NOW)
        segment = context["routes"][0]["segments"][0]

        self.assertEqual(
            segment["matched_record_ids"]["transport_status"], ["crossing"]
        )
        self.assertEqual(
            [item["record_id"] for item in context["evidence"]], ["crossing"]
        )
        self.assertEqual(
            {item["record_id"] for item in context["unmatched_evidence"]},
            {"distant", "ended"},
        )

    def test_invalid_line_coordinate_is_rejected(self):
        invalid = incident(
            "invalid", [[100.0, 13.0], [200.0, 13.0]],
            "2026-09-21T00:00:00Z",
        )
        with self.assertRaisesRegex(ContractError, "longitude/latitude bounds"):
            build_context(route_query(), [invalid], now=NOW)


if __name__ == "__main__":
    unittest.main()
