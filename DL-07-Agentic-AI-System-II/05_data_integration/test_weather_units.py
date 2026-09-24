"""Check Module 05's weather values at the provisional Module 06 boundary."""

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("integration.py")
SPEC = importlib.util.spec_from_file_location("integration", MODULE_PATH)
integration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(integration)


class WeatherUnitsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = {
            "run_id": "synthetic-weather-units",
            "routes": [{
                "route_id": "synthetic-route",
                "geometry": {"type": "LineString", "coordinates": [[100.49, 13.75], [100.51, 13.75]]},
                "segments": [{
                    "start_index": 0,
                    "end_index": 1,
                    "enter_at": "2026-09-20T07:50:00+07:00",
                    "exit_at": "2026-09-20T08:10:00+07:00",
                }],
            }],
        }
        self.record = {
            "schema_version": "canonical-record-v0.1-proposed",
            "record_id": "synthetic-open-meteo-1",
            "record_kind": "weather_forecast",
            "status": "available",
            "source": {"name": "Open-Meteo", "authority": None},
            "source_lineage": "https://api.open-meteo.com/v1/forecast?example=1",
            "spatial_footprint": {"type": "Point", "coordinates": [100.50, 13.75]},
            "observed_at": None,
            "valid_at": "2026-09-20T08:00:00+07:00",
            "fetched_at": "2026-09-19T06:00:00+00:00",
            "expires_at": "2026-09-19T06:30:00+00:00",
            "quality_flags": [],
            "value": {
                "wind_speed_kmh": 72.0,
                "visibility_m": 800.0,
                "rain_probability_percent": 80.0,
            },
        }
        self.now = datetime.fromisoformat("2026-09-19T06:10:00+00:00")

    def test_units_are_available_to_06_and_source_values_are_preserved(self) -> None:
        context = integration.build_context(self.query, [self.record], now=self.now)
        value = context["evidence"][0]["value"]
        self.assertEqual(value["wind_speed_kmh"], 72.0)
        self.assertEqual(value["wind_speed_kph"], 72.0)
        self.assertEqual(value["visibility_m"], 800.0)
        self.assertEqual(value["visibility_km"], 0.8)
        self.assertEqual(value["rain_probability_percent"], 80.0)
        self.assertEqual(value["rain_probability"], 0.8)
        self.assertEqual(context["routes"][0]["segments"][0]["coverage"]["weather_forecast"], "covered")
        self.assertEqual(self.record["value"].keys(), {
            "wind_speed_kmh", "visibility_m", "rain_probability_percent"
        })

    def test_null_source_values_are_not_filled(self) -> None:
        self.record["value"]["visibility_m"] = None
        context = integration.build_context(self.query, [self.record], now=self.now)
        self.assertNotIn("visibility_km", context["evidence"][0]["value"])

    def test_conflicting_alias_is_rejected(self) -> None:
        self.record["value"]["wind_speed_kph"] = 20.0
        with self.assertRaises(integration.ContractError):
            integration.build_context(self.query, [self.record], now=self.now)


if __name__ == "__main__":
    unittest.main()
