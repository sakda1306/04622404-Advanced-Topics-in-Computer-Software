"""Unit tests for Longdo Traffic adapter."""

import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import longdo_traffic_adapter
from longdo_traffic_adapter import fetch_canonical_transport, to_canonical_transport

NOW = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
BBOX_BANGKOK = (100.4, 13.7, 100.6, 13.9)


def sample_longdo_events():
    return [
        {
            "eid": "1001",
            "title": "ปิดสะพานข้ามแยก",
            "title_en": "Road Closed at Overpass",
            "description": "ปิดสะพานซ่อมบำรุง 24 ชม.",
            "latitude": "13.7550",
            "longitude": "100.5050",
            "type": "19",
            "start": "2026-09-20 00:00:00",
            "stop": "2026-09-30 23:59:59",
            "contributor": "itic.police",
            "icon": "roadclosed",
        },
        {
            "eid": "1002",
            "title": "น้ำท่วมขังผิวจราจร",
            "title_en": "Flooding on road surface",
            "description": "ระดับน้ำสูง 15 ซม. รถเล็กสัญจรลำบาก",
            "latitude": "13.8000",
            "longitude": "100.5200",
            "type": "6",
            "start": "2026-09-22 00:30:00",
            "stop": "2026-09-22 04:00:00",
            "contributor": "itic.fm91",
            "icon": "flood",
        },
        {
            "eid": "1003",
            "title": "อุบัติเหตุรถชน",
            "title_en": "Car Accident",
            "description": "กีดขวางช่องทางขวา",
            "latitude": "13.7600",
            "longitude": "100.5100",
            "type": "3",
            "start": "2026-09-22 00:45:00",
            "stop": "2026-09-22 02:00:00",
            "contributor": "itic.traffic",
            "icon": "accident",
        },
        {
            "eid": "2001",
            "title": "ก่อสร้างทางเชียงใหม่",
            "title_en": "Chiang Mai Construction",
            "description": "ก่อสร้างขยายผิวทาง",
            "latitude": "18.7900",
            "longitude": "98.9800",
            "type": "2",
            "start": "2026-09-01 00:00:00",
            "stop": "2026-10-01 00:00:00",
            "contributor": "itic.north",
            "icon": "construction",
        },
    ]


class LongdoTrafficAdapterTests(unittest.TestCase):
    def test_canonical_conversion_and_severity_mapping(self):
        records = to_canonical_transport(
            sample_longdo_events(),
            bbox=BBOX_BANGKOK,
            fetched_at=NOW,
        )

        # 3 Bangkok incidents should match, 1 Chiang Mai incident should be filtered out
        self.assertEqual(len(records), 3)

        # 1. Check Road Closed (type 19)
        road_closed = next(r for r in records if r["record_id"] == "longdo:1001")
        self.assertEqual(road_closed["record_kind"], "transport_status")
        self.assertEqual(road_closed["status"], "available")
        self.assertEqual(road_closed["severity"], "HIGH")
        self.assertEqual(road_closed["value"]["status"], "CLOSED")
        self.assertEqual(road_closed["value"]["category"], "roadClosed")
        self.assertEqual(road_closed["spatial_footprint"]["type"], "Point")
        self.assertAlmostEqual(road_closed["spatial_footprint"]["coordinates"][0], 100.505)
        self.assertAlmostEqual(road_closed["spatial_footprint"]["coordinates"][1], 13.755)
        self.assertEqual(road_closed["value"]["time_validity"], "present")
        self.assertEqual(road_closed["observed_at"], NOW.isoformat())

        # 2. Check Flood (type 6)
        flood = next(r for r in records if r["record_id"] == "longdo:1002")
        self.assertEqual(flood["severity"], "HIGH")
        self.assertEqual(flood["value"]["status"], "INCIDENT")
        self.assertEqual(flood["value"]["category"], "flood")

        # 3. Check Accident (type 3)
        accident = next(r for r in records if r["record_id"] == "longdo:1003")
        self.assertEqual(accident["severity"], "MEDIUM")
        self.assertEqual(accident["value"]["status"], "INCIDENT")
        self.assertEqual(accident["value"]["category"], "accident")

    def test_fetch_canonical_transport_live_or_mock_network(self):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_longdo_events()).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch.object(longdo_traffic_adapter, "urlopen", return_value=mock_response):
            records = fetch_canonical_transport(BBOX_BANGKOK, now=NOW)

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["status"], "available")

    def test_network_failure_returns_unavailable_record(self):
        with patch.object(
            longdo_traffic_adapter, "urlopen", side_effect=URLError("Network unreachable")
        ):
            records = fetch_canonical_transport(BBOX_BANGKOK, now=NOW)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "unavailable")
        self.assertEqual(records[0]["error_code"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(records[0]["record_kind"], "transport_status")
