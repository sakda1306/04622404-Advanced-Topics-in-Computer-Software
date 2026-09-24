"""
Unit tests for Module 07 Decision Engine integration (client, adapter, and endpoint).
No running Postgres, Redis, or 07 service required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.adapter import apply_emergency_fragment, decision_to_recommendation
from app.decision_client import DecisionEngineClient
from app.main import app
from app.mock_data import ALL_SCENARIOS
from app.schema import ActionCode, ConfidenceLevel, RecommendationResponse, RiskLevel

SAMPLE_07_RESPONSE = {
    "request_id": "00000000-0000-4000-8000-000000000007",
    "action_code": "AVOID",
    "backend_action_code": "AVOID_TRAVEL",
    "risk_level": "HIGH",
    "confidence": 0.85,
    "confidence_kind": "heuristic_policy_score",
    "confidence_details": {"base": 0.85},
    "emergency_instructions": {
        "what_to_do_now": "งดการเดินทางและรอคำแนะนำในที่ปลอดภัย",
        "safety_steps": ["หลีกเลี่ยงพื้นที่เสี่ยงภัย", "ติดตามประกาศทางการ"],
        "contacts": [
            {
                "name": "ตำรวจท่องเที่ยว",
                "phone": "1155",
            }
        ],
        "nearest_support": [],
    },
    "emergency_contact_metadata": {
        "0": {
            "contact_type": "police",
            "region": "TH",
            "effective_date": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "directory_version": "v1",
            "source_url": "https://example.org/emergency",
        }
    },
    "emergency_assessment": {
        "status": "grounded",
        "issues": [],
    },
    "escalation_required": False,
    "escalation_reasons": [],
    "selected_route_id": None,
    "suggested_departure_time": None,
    "explanation": {
        "summary": "เส้นทางมีความเสี่ยงสูงเนื่องจากภัยพิบัติ แนะนำให้งดการเดินทาง",
        "reasons": ["พบความเสี่ยงระดับสูงในพื้นที่เส้นทางหลัก"],
        "instructions": ["หลีกเลี่ยงการเดินทางจนกว่าสถานการณ์จะคลี่คลาย"],
        "uncertainty": ["ข้อมูลสภาพอากาศอาจมีการเปลี่ยนแปลง"],
        "mode": "template",
    },
    "citations": [
        {
            "evidence_id": "mock-risk-1",
            "source_name": "TMD Weather Warning",
            "url": "https://example.org/weather",
            "observed_at": "2026-09-20T00:00:00Z",
            "fetched_at": "2026-09-20T00:05:00Z",
            "expires_at": "2026-09-20T06:00:00Z",
        }
    ],
    "degraded_services": ["transport_service"],
    "evaluated_at": "2026-09-20T00:05:00Z",
    "valid_until": "2026-09-20T03:00:00Z",
}


def test_adapter_maps_07_decision_to_recommendation():
    reco = decision_to_recommendation(SAMPLE_07_RESPONSE, traveler_region="TH")
    assert isinstance(reco, RecommendationResponse)
    assert reco.request_id == "00000000-0000-4000-8000-000000000007"
    assert reco.action_code == ActionCode.AVOID_TRAVEL
    assert reco.risk_level == RiskLevel.HIGH
    assert reco.confidence == 0.85
    assert reco.confidence_level == ConfidenceLevel.HIGH
    assert "งดการเดินทาง" in reco.short_summary
    assert len(reco.immediate_actions) == 1
    assert len(reco.reasons) == 1
    assert len(reco.sources) == 1
    assert reco.sources[0].name == "TMD Weather Warning"
    assert len(reco.degraded_services) == 1
    assert reco.degraded_services[0].service_name == "transport_service"
    assert len(reco.official_contacts) == 1
    assert reco.official_contacts[0].phone == "1155"
    assert reco.expires_at > reco.fetched_at


def test_adapter_emergency_contacts_filtered_on_mismatched_region():
    # Region US does not match contact's region TH -> contacts withheld
    reco = decision_to_recommendation(SAMPLE_07_RESPONSE, traveler_region="US")
    assert reco.official_contacts == []
    assert any("region_mismatch" in (deg.detail or "") for deg in reco.degraded_services)
    assert any("location" in lim.lower() for lim in reco.limitations)


def test_confidence_level_categorization():
    low_conf = {**SAMPLE_07_RESPONSE, "confidence": 0.25}
    reco_low = decision_to_recommendation(low_conf, traveler_region="TH")
    assert reco_low.confidence_level == ConfidenceLevel.LOW

    med_conf = {**SAMPLE_07_RESPONSE, "confidence": 0.55}
    reco_med = decision_to_recommendation(med_conf, traveler_region="TH")
    assert reco_med.confidence_level == ConfidenceLevel.MEDIUM


@pytest.mark.asyncio
async def test_decision_client_success():
    client = DecisionEngineClient(base_url="http://mock-07:8050")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = SAMPLE_07_RESPONSE

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.request_decision({"test": "payload"})
        assert result["action_code"] == "AVOID"
        assert result["confidence"] == 0.85


@pytest.mark.asyncio
async def test_decision_client_connection_error():
    client = DecisionEngineClient(base_url="http://mock-07:8050")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(HTTPException) as exc:
            await client.request_decision({"test": "payload"})
        assert exc.value.status_code == 503
        assert "unreachable" in exc.value.detail


@pytest.mark.asyncio
async def test_decision_client_timeout():
    client = DecisionEngineClient(base_url="http://mock-07:8050")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(HTTPException) as exc:
            await client.request_decision({"test": "payload"})
        assert exc.value.status_code == 504
        assert "timed out" in exc.value.detail


def test_endpoint_generate_recommendation():
    test_client = TestClient(app)
    with patch("app.main.decision_client.request_decision", new=AsyncMock(return_value=SAMPLE_07_RESPONSE)):
        with patch("app.main.db.save_recommendation", new=AsyncMock()):
            response = test_client.post(
                "/recommendation/generate?region=TH&user_id=test-user",
                json={"context": {"request_id": "00000000-0000-4000-8000-000000000007"}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["action_code"] == "AVOID_TRAVEL"
            assert data["risk_level"] == "HIGH"
            assert data["confidence"] == 0.85
            assert len(data["official_contacts"]) == 1


def test_adapter_direct_handoff_fragment_format():
    # Test when 07 DecisionResponse has direct lists (handoff.py format)
    fragment_response = {
        "request_id": "00000000-0000-4000-8000-000000000008",
        "action_code": "AVOID",
        "backend_action_code": "AVOID_TRAVEL",
        "risk_level": "HIGH",
        "confidence": 0.9,
        "emergency_instructions": ["แจ้งเหตุทันที", "หาที่กำบัง"],
        "official_contacts": [
            {
                "name": "ศูนย์เตือนภัยพิบัติแห่งชาติ",
                "phone": "192",
                "contact_type": "disaster",
                "region": "TH",
                "effective_date": "2026-01-01T00:00:00Z",
            }
        ],
        "explanation": {"summary": "ฉุกเฉิน", "instructions": [], "reasons": []},
    }
    reco = decision_to_recommendation(fragment_response, traveler_region="TH")
    assert len(reco.emergency_instructions) == 2
    assert reco.emergency_instructions[0] == "แจ้งเหตุทันที"
    assert len(reco.official_contacts) == 1
    assert reco.official_contacts[0].phone == "192"


def test_apply_emergency_fragment_to_existing_recommendation():
    base_reco = ALL_SCENARIOS["travel_normally"]
    fragment = {
        "emergency_instructions": ["ปฏิบัติตามคำสั่งเจ้าหน้าที่"],
        "official_contacts": [
            {
                "name": "สายด่วนตำรวจ",
                "phone": "191",
                "contact_type": "police",
                "region": "TH",
                "effective_date": "2026-01-01T00:00:00Z",
            }
        ],
        "limitations": ["flood_warning_active"],
    }
    updated = apply_emergency_fragment(base_reco, fragment, traveler_region="TH")
    assert "ปฏิบัติตามคำสั่งเจ้าหน้าที่" in updated.emergency_instructions
    assert len(updated.official_contacts) == 1
    assert updated.official_contacts[0].phone == "191"
    assert "flood_warning_active" in updated.limitations
