"""Unit and boundary tests for Thai Disaster Adapter."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import thai_disaster_adapter
from thai_disaster_adapter import (
    SCHEMA,
    fetch_canonical_disasters,
    to_canonical_disasters,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://data.go.th/api/3/action/datastore_search?resource_id=test"


def sample_datastore_record(
    incident_id="DPM-2026-001",
    title="น้ำท่วมฉับพลันและน้ำป่าไหลหลาก",
    province="เชียงราย",
    severity="วิกฤต",
    lat=20.433,
    lon=99.882,
    start_date="2026-09-21T08:00:00+07:00",
):
    return {
        "_id": 1,
        "incident_id": incident_id,
        "title": title,
        "province": province,
        "severity_level": severity,
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "situation": "ระดับน้ำแม่น้ำสายล้นตลิ่ง เข้าท่วมพื้นที่ชุมชนริมน้ำ",
    }


class ThaiDisasterAdapterTests(unittest.TestCase):
    def test_datastore_payload_converts_to_canonical_disaster_event(self):
        payload = {
            "success": True,
            "result": {
                "records": [sample_datastore_record()],
            },
        }

        records = to_canonical_disasters(payload, source_url=SOURCE_URL, fetched_at=NOW)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["schema_version"], SCHEMA)
        self.assertEqual(record["record_kind"], "disaster_event")
        self.assertEqual(record["status"], "available")
        self.assertEqual(record["record_id"], "thai_disaster:dpm:DPM-2026-001")
        self.assertEqual(record["severity"], "HIGH")
        self.assertEqual(record["source"]["authority"], "DDPM Thailand")
        self.assertEqual(
            record["spatial_footprint"],
            {"type": "Point", "coordinates": [99.882, 20.433]},
        )
        self.assertEqual(record["value"]["event_type"], "FL")
        self.assertEqual(record["value"]["country"], "Thailand")
        self.assertEqual(record["value"]["province"], "เชียงราย")
        self.assertEqual(record["event_time"], "2026-09-21T01:00:00+00:00")

    def test_province_centroid_lookup_when_coordinates_missing(self):
        payload = {
            "success": True,
            "result": {
                "records": [
                    sample_datastore_record(
                        incident_id="DPM-2026-002",
                        title="ดินโคลนถล่มปิดทับเส้นทาง",
                        province="เชียงใหม่",
                        severity="เฝ้าระวังพิเศษ",
                        lat=None,
                        lon=None,
                    )
                ],
            },
        }

        records = to_canonical_disasters(payload, source_url=SOURCE_URL, fetched_at=NOW)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["value"]["event_type"], "LS")
        self.assertEqual(record["severity"], "MEDIUM")
        # Centroid coordinates for Chiang Mai
        self.assertAlmostEqual(record["spatial_footprint"]["coordinates"][0], 98.9853, places=3)
        self.assertAlmostEqual(record["spatial_footprint"]["coordinates"][1], 18.7883, places=3)

    def test_storm_classification_and_geojson_feature_format(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [100.5954, 7.1897]},
                    "properties": {
                        "incident_id": "TMD-STORM-01",
                        "title": "เตือนภัยพายุดีเปรสชันและคลื่นลมแรงอ่าวไทย",
                        "province": "สงขลา",
                        "alert_level": "เตือนภัย",
                        "start_date": "2026-09-21 07:00:00",
                        "detail": "คลื่นลมแรงบริเวณอ่าวไทยตอนล่าง เรือเล็กควรงดออกจากฝั่ง",
                    },
                }
            ],
        }

        records = to_canonical_disasters(payload, source_url=SOURCE_URL, fetched_at=NOW)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_id"], "thai_disaster:dpm:TMD-STORM-01")
        self.assertEqual(record["value"]["event_type"], "ST")
        self.assertEqual(record["severity"], "MEDIUM")
        self.assertEqual(
            record["spatial_footprint"],
            {"type": "Point", "coordinates": [100.5954, 7.1897]},
        )

    def test_provider_offline_returns_unavailable_record(self):
        with patch.object(
            thai_disaster_adapter, "urlopen", side_effect=URLError("connection refused")
        ):
            records = fetch_canonical_disasters(now=NOW, endpoint=SOURCE_URL)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_UNAVAILABLE")
        self.assertIsNone(records[0]["value"])
        self.assertIsNone(records[0]["severity"])

    def test_provider_auth_failure(self):
        with patch.object(
            thai_disaster_adapter,
            "urlopen",
            side_effect=HTTPError(SOURCE_URL, 401, "Unauthorized", {}, None),
        ):
            records = fetch_canonical_disasters(now=NOW, endpoint=SOURCE_URL)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_AUTH_FAILED")

    def test_provider_not_configured_returns_unavailable(self):
        with patch.dict(thai_disaster_adapter.os.environ, {}, clear=True):
            records = fetch_canonical_disasters(now=NOW)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_NOT_CONFIGURED")

    def test_mock_fallback_returns_available_thai_events(self):
        with patch.dict(thai_disaster_adapter.os.environ, {"THAI_DISASTER_MOCK_FALLBACK": "true"}):
            records = fetch_canonical_disasters(now=NOW)
        self.assertGreaterEqual(len(records), 2)
        self.assertTrue(all(r["status"] == "available" for r in records))
        self.assertTrue(all(r["record_kind"] == "disaster_event" for r in records))


if __name__ == "__main__":
    unittest.main()
