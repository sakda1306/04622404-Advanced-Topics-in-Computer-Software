"""Focused tests for the provisional Module 05 core; all records are synthetic."""

import unittest
from datetime import datetime, timezone

from integration import ESSENTIAL_KINDS, ContractError, build_context


NOW = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)


def route_query():
    return {
        "run_id": "fixture-run",
        "routes": [{
            "route_id": "fixture-route",
            "geometry": {"type": "LineString", "coordinates": [[100.0, 13.0], [100.1, 13.0], [100.2, 13.0]]},
            "segments": [
                {"start_index": 0, "end_index": 1, "enter_at": "2026-09-20T08:00:00+07:00", "exit_at": "2026-09-20T08:20:00+07:00"},
                {"start_index": 1, "end_index": 2, "enter_at": "2026-09-20T08:20:00+07:00", "exit_at": "2026-09-20T08:40:00+07:00"},
            ],
        }],
    }


def forecast(**changes):
    record = {
        "schema_version": "canonical-record-v0.1-proposed",
        "record_id": "forecast-1",
        "record_kind": "weather_forecast",
        "status": "available",
        "source": {"name": "fixture-provider", "authority": None},
        "source_lineage": "https://example.org/fixture",
        "spatial_footprint": {"type": "Point", "coordinates": [100.05, 13.0]},
        "observed_at": None,
        "valid_at": "2026-09-20T08:10:00+07:00",
        "fetched_at": "2026-09-19T05:50:00Z",
        "expires_at": "2026-09-19T06:30:00Z",
        "value": {"temperature_c": 30.0},
        "quality_flags": [],
    }
    record.update(changes)
    return record


class IntegrationTests(unittest.TestCase):
    def test_forecast_valid_at_may_be_in_future_without_observed_at(self):
        context = build_context(route_query(), [forecast()], now=NOW)
        first, second = context["routes"][0]["segments"]
        self.assertEqual(first["coverage"]["weather_forecast"], "covered")
        self.assertEqual(first["matched_record_ids"]["weather_forecast"], ["forecast-1"])
        self.assertEqual(second["coverage"]["weather_forecast"], "missing")
        self.assertIsNone(context["evidence"][0]["observed_at"])
        self.assertIsNone(context["risk_score"])
        self.assertIn("partial", context["quality_flags"])

    def test_complete_fresh_evidence_marks_segment_covered(self):
        query = route_query()
        query["routes"][0]["segments"] = [
            {
                "start_index": 0,
                "end_index": 2,
                "enter_at": "2026-09-20T08:00:00+07:00",
                "exit_at": "2026-09-20T08:40:00+07:00",
            }
        ]
        records = []
        for kind in (
            "current_weather",
            "weather_forecast",
            "transport_status",
            "closure",
            "disaster_event",
            "official_alert",
        ):
            records.append(
                forecast(
                    record_id=f"{kind}-1",
                    record_kind=kind,
                )
            )

        context = build_context(query, records, now=NOW)
        segment = context["routes"][0]["segments"][0]

        self.assertEqual(
            segment["coverage"],
            {kind: "covered" for kind in segment["coverage"]},
        )
        self.assertEqual(context["quality_flags"], [])
        self.assertFalse(context["degraded"])

    def test_unavailable_provider_is_explicit_and_has_no_invented_value(self):
        unavailable = forecast(
            record_id="transport-1", record_kind="transport_status", status="unavailable",
            spatial_footprint=None, valid_at=None, value=None, error_code="PROVIDER_TIMEOUT",
        )
        context = build_context(route_query(), [unavailable], now=NOW)
        self.assertEqual(context["routes"][0]["segments"][0]["coverage"]["transport_status"], "unavailable")
        self.assertTrue(context["degraded"])
        self.assertIsNone(context["evidence"][0]["value"])
        self.assertIsNone(context["evidence"][0]["severity"])

    def test_expired_record_cannot_cover_segment(self):
        context = build_context(route_query(), [forecast(expires_at="2026-09-19T05:59:00Z")], now=NOW)
        self.assertEqual(context["routes"][0]["segments"][0]["coverage"]["weather_forecast"], "stale")
        self.assertEqual(context["routes"][0]["segments"][0]["matched_record_ids"]["weather_forecast"], [])

    def test_outside_time_or_corridor_does_not_match(self):
        too_late = forecast(record_id="late", valid_at="2026-09-20T09:00:00+07:00")
        too_far = forecast(record_id="far", spatial_footprint={"type": "Point", "coordinates": [101.0, 13.0]})
        context = build_context(route_query(), [too_late, too_far], now=NOW)
        self.assertEqual(context["routes"][0]["segments"][0]["coverage"]["weather_forecast"], "missing")

    def test_missing_route_segment_is_rejected(self):
        query = route_query()
        query["routes"][0]["segments"].pop()
        with self.assertRaisesRegex(ContractError, "full route"):
            build_context(query, [], now=NOW)

    def test_naive_time_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "timezone offset"):
            build_context(route_query(), [forecast(valid_at="2026-09-20T08:10:00")], now=NOW)

    def test_available_record_requires_traceable_source(self):
        with self.assertRaisesRegex(ContractError, "source_lineage"):
            build_context(route_query(), [forecast(source_lineage=None)], now=NOW)

    def test_route_label_and_modes_reach_output(self):
        query = route_query()
        query["routes"][0]["label"] = "Primary"
        query["routes"][0]["travel_modes"] = ["CAR"]

        context = build_context(query, [], now=NOW)
        route = context["routes"][0]

        self.assertEqual(route["label"], "Primary")
        self.assertEqual(route["travel_modes"], ["CAR"])

    def test_build_context_confidence_and_active_restriction_complete_records(self):
        query = route_query()
        query["routes"][0]["segments"] = [
            {
                "start_index": 0,
                "end_index": 2,
                "enter_at": "2026-09-20T08:00:00+07:00",
                "exit_at": "2026-09-20T08:40:00+07:00",
            }
        ]
        records = [
            forecast(
                record_id=f"{kind}-1",
                record_kind=kind,
                value={"status": "NORMAL", "active": False},
                severity="LOW",
            )
            for kind in (
                "current_weather",
                "weather_forecast",
                "transport_status",
                "closure",
                "disaster_event",
                "official_alert",
            )
        ]
        context = build_context(query, records, now=NOW)
        self.assertEqual(context["confidence"], "HIGH")
        self.assertFalse(context["active_restriction"])
        self.assertEqual(context["quality_flags"], [])

    def test_build_context_confidence_low_when_provider_unavailable(self):
        query = route_query()
        records = [
            forecast(
                record_id="transport-1",
                record_kind="transport_status",
                status="unavailable",
                spatial_footprint=None,
                valid_at=None,
                value=None,
                error_code="PROVIDER_TIMEOUT",
            )
        ]
        context = build_context(query, records, now=NOW)
        self.assertEqual(context["confidence"], "LOW")
        self.assertIsNone(context["active_restriction"])
        self.assertIn("unavailable", context["quality_flags"])

    def test_build_context_confidence_low_when_coverage_missing(self):
        query = route_query()
        context = build_context(query, [], now=NOW)
        self.assertEqual(context["confidence"], "LOW")
        self.assertIsNone(context["active_restriction"])
        self.assertIn("missing", context["quality_flags"])

    def test_build_context_active_restriction_detected(self):
        query = route_query()
        query["routes"][0]["segments"] = [
            {
                "start_index": 0,
                "end_index": 2,
                "enter_at": "2026-09-20T08:00:00+07:00",
                "exit_at": "2026-09-20T08:40:00+07:00",
            }
        ]
        records = [
            forecast(
                record_id=f"{kind}-1",
                record_kind=kind,
                value={"status": "CLOSED" if kind == "closure" else "NORMAL", "active": kind == "closure"},
                severity="HIGH" if kind == "closure" else "LOW",
            )
            for kind in (
                "current_weather",
                "weather_forecast",
                "transport_status",
                "closure",
                "disaster_event",
                "official_alert",
            )
        ]
        context = build_context(query, records, now=NOW)
        self.assertEqual(context["confidence"], "HIGH")
        self.assertTrue(context["active_restriction"])

    def test_confidence_with_only_the_kinds_module_04_can_produce(self):
        # Module 04 publishes weather, transport_status and disaster_event only; no
        # provider emits closure or official_alert. That must not force LOW forever.
        query = route_query()
        query["routes"][0]["segments"] = [{
            "start_index": 0,
            "end_index": 2,
            "enter_at": "2026-09-20T08:00:00+07:00",
            "exit_at": "2026-09-20T08:40:00+07:00",
        }]
        records = [
            forecast(record_id=f"{kind}-1", record_kind=kind, severity="LOW")
            for kind in ESSENTIAL_KINDS
        ]
        context = build_context(query, records, now=NOW)
        coverage = context["routes"][0]["segments"][0]["coverage"]
        self.assertEqual(coverage["closure"], "missing")
        self.assertEqual(coverage["official_alert"], "missing")
        self.assertEqual(context["quality_flags"], [])
        self.assertEqual(context["confidence"], "HIGH")
        self.assertFalse(context["active_restriction"])

    def test_failing_optional_provider_still_degrades_quality(self):
        query = route_query()
        query["routes"][0]["segments"] = [{
            "start_index": 0,
            "end_index": 2,
            "enter_at": "2026-09-20T08:00:00+07:00",
            "exit_at": "2026-09-20T08:40:00+07:00",
        }]
        records = [
            forecast(record_id=f"{kind}-1", record_kind=kind, severity="LOW")
            for kind in ESSENTIAL_KINDS
        ]
        records.append(
            forecast(
                record_id="closure-down",
                record_kind="closure",
                status="unavailable",
                spatial_footprint=None,
                valid_at=None,
                value=None,
                error_code="PROVIDER_UNAVAILABLE",
            )
        )
        context = build_context(query, records, now=NOW)
        self.assertIn("unavailable", context["quality_flags"])
        self.assertEqual(context["confidence"], "LOW")
        self.assertIsNone(context["active_restriction"])

    def test_missing_essential_kind_still_degrades_quality(self):
        query = route_query()
        records = [
            forecast(record_id=f"{kind}-1", record_kind=kind, severity="LOW")
            for kind in ESSENTIAL_KINDS
            if kind != "transport_status"
        ]
        context = build_context(query, records, now=NOW)
        self.assertIn("missing", context["quality_flags"])
        self.assertEqual(context["confidence"], "LOW")
        self.assertIsNone(context["active_restriction"])


if __name__ == "__main__":
    unittest.main()
