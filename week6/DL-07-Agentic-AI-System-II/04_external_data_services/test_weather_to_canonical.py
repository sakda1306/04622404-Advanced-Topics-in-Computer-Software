"""Contract tests for the Module 04 to Module 05 weather adapter."""

import unittest

from weather_to_canonical import WeatherContractError, to_canonical_weather_record


class WeatherToCanonicalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = {
            "schema_version": "weather-record-v0.1",
            "data_kind": "forecast",
            "latitude": 13.75,
            "longitude": 100.50,
            "valid_at": "2026-09-20T08:00:00+07:00",
            "fetched_at": "2026-09-19T06:00:00+00:00",
            "expires_at": "2026-09-19T06:30:00+00:00",
            "source": "Open-Meteo",
            "source_lineage": "https://api.open-meteo.com/v1/forecast?example=1",
            "quality_flags": [],
            "temperature_c": 30.0,
            "rain_mm": None,
        }

    def test_forecast_maps_without_inventing_observation(self) -> None:
        result = to_canonical_weather_record(self.record)
        self.assertEqual(result["record_kind"], "weather_forecast")
        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["observed_at"])
        self.assertEqual(result["valid_at"], self.record["valid_at"])
        self.assertEqual(result["spatial_footprint"]["coordinates"], [100.50, 13.75])
        self.assertEqual(result["value"]["temperature_c"], 30.0)
        self.assertEqual(result["source_lineage"], self.record["source_lineage"])

    def test_model_current_maps_to_current_weather(self) -> None:
        self.record["data_kind"] = "model_current"
        result = to_canonical_weather_record(self.record)
        self.assertEqual(result["record_kind"], "current_weather")
        self.assertIsNone(result["observed_at"])

    def test_missing_all_values_is_unavailable(self) -> None:
        self.record["temperature_c"] = None
        result = to_canonical_weather_record(self.record)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["value"])
        self.assertEqual(result["error_code"], "WEATHER_VALUES_MISSING")

    def test_missing_lineage_is_rejected(self) -> None:
        self.record["source_lineage"] = None
        with self.assertRaises(WeatherContractError):
            to_canonical_weather_record(self.record)


if __name__ == "__main__":
    unittest.main()
