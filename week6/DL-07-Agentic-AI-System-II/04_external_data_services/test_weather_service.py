"""Check Module 04's canonical success and provider-failure paths."""

import unittest
from unittest.mock import patch

import weather_service
from open_meteo_adapter import WeatherDataError, WeatherProviderError


class WeatherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {
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
        }

    def test_successful_forecast_is_canonical(self) -> None:
        with patch.object(weather_service, "fetch_weather_forecast", return_value=[self.raw]):
            records = weather_service.fetch_canonical_forecast(13.75, 100.50)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_kind"], "weather_forecast")
        self.assertEqual(records[0]["status"], "available")
        self.assertIsNone(records[0]["observed_at"])

    def test_provider_failure_is_unavailable_without_value(self) -> None:
        with patch.object(weather_service, "fetch_weather_forecast", side_effect=WeatherProviderError("timeout")):
            records = weather_service.fetch_canonical_forecast(13.75, 100.50)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_UNAVAILABLE")
        self.assertIsNone(records[0]["value"])
        self.assertIsNone(records[0]["observed_at"])

    def test_invalid_provider_data_is_distinct(self) -> None:
        with patch.object(weather_service, "fetch_current_weather", side_effect=WeatherDataError("invalid")):
            record = weather_service.fetch_canonical_current_weather(13.75, 100.50)
        self.assertEqual(record["record_kind"], "current_weather")
        self.assertEqual(record["error_code"], "PROVIDER_DATA_INVALID")

    def test_invalid_coordinates_are_not_reported_as_provider_failure(self) -> None:
        with self.assertRaises(ValueError):
            weather_service.fetch_canonical_forecast(100.0, 100.50)


if __name__ == "__main__":
    unittest.main()
