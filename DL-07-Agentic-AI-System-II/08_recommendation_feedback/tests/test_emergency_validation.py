"""Emergency contact validation (no DB / Redis needed)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.emergency import (
    NO_VERIFIED_CONTACTS_NOTE,
    REGION_UNVERIFIED_NOTE,
    SERVICE_NAME,
    validate_emergency_content,
)
from app.main import app
from app.mock_data import ALL_SCENARIOS
from app.schema import EmergencyContact, ServiceStatus

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _contact(**kw) -> EmergencyContact:
    base = dict(
        name="Police", phone="191", contact_type="police", region="TH",
        effective_date=NOW - timedelta(days=30),
    )
    base.update(kw)
    return EmergencyContact(**base)


def _resp(*contacts, instructions=("Drop, cover, hold on.",)):
    return ALL_SCENARIOS["emergency_instructions"].model_copy(
        update={
            "official_contacts": list(contacts),
            "emergency_instructions": list(instructions),
            "limitations": [],
            "degraded_services": [],
        }
    )


def test_matching_region_and_valid_date_passes_untouched():
    r = _resp(_contact())
    out = validate_emergency_content(r, "th", now=NOW)
    assert out is r  # nothing to change


def test_region_mismatch_is_withheld_with_notice():
    out = validate_emergency_content(_resp(_contact(), _contact(name="US", phone="911", region="US")), "US", now=NOW)
    assert [c.region for c in out.official_contacts] == ["US"]
    svc = [d for d in out.degraded_services if d.service_name == SERVICE_NAME]
    assert svc and svc[0].status == ServiceStatus.DEGRADED
    assert "region_mismatch" in svc[0].detail


def test_future_effective_date_is_withheld():
    out = validate_emergency_content(_resp(_contact(effective_date=NOW + timedelta(days=1))), "TH", now=NOW)
    assert out.official_contacts == []
    assert NO_VERIFIED_CONTACTS_NOTE in out.limitations  # instructions remain, so say why no number


def test_naive_effective_date_is_treated_as_utc():
    naive_past = (NOW - timedelta(days=2)).replace(tzinfo=None)
    out = validate_emergency_content(_resp(_contact(effective_date=naive_past)), "TH", now=NOW)
    assert len(out.official_contacts) == 1


@pytest.mark.parametrize("phone", ["", "abc", "call 191", "1" * 30])
def test_invalid_phone_is_withheld(phone):
    out = validate_emergency_content(_resp(_contact(phone=phone)), "TH", now=NOW)
    assert out.official_contacts == []


@pytest.mark.parametrize("phone", ["191", "1669", "+66 2 123 4567", "(02) 123-4567"])
def test_valid_phone_formats_pass(phone):
    out = validate_emergency_content(_resp(_contact(phone=phone)), "TH", now=NOW)
    assert len(out.official_contacts) == 1


def test_unknown_region_keeps_contact_but_says_unverified():
    out = validate_emergency_content(_resp(_contact()), None, now=NOW)
    assert len(out.official_contacts) == 1
    assert REGION_UNVERIFIED_NOTE in out.limitations


def test_unknown_region_strict_mode_withholds():
    out = validate_emergency_content(_resp(_contact()), None, now=NOW, strict_region=True)
    assert out.official_contacts == []


def test_input_is_not_mutated():
    r = _resp(_contact(region="US"))
    validate_emergency_content(r, "TH", now=NOW)
    assert len(r.official_contacts) == 1 and r.limitations == [] and r.degraded_services == []


def test_no_instructions_and_no_contacts_adds_no_noise():
    r = ALL_SCENARIOS["travel_normally"]
    assert validate_emergency_content(r, "TH", now=NOW) is r


def test_null_from_03_then_validation_does_not_break():
    from app.schema import RecommendationResponse

    payload = {**ALL_SCENARIOS["avoid_travel"].model_dump(mode="json"),
               "emergency_instructions": None, "official_contacts": None}
    r = RecommendationResponse.model_validate(payload)
    assert validate_emergency_content(r, "TH", now=NOW) is r


# ---- endpoint wiring (db is patched; no Postgres needed) -------------------

def _client():
    return TestClient(app)  # no context manager -> startup (DB wait) is not run


def test_mock_endpoint_withholds_contacts_for_wrong_region():
    with patch("app.main.db.save_recommendation", new=AsyncMock()):
        body = _client().get("/recommendation/mock/emergency_instructions?region=US").json()
    assert body["official_contacts"] == []
    assert body["action_code"] == "AVOID_TRAVEL" and body["risk_level"] == "HIGH"
    assert any(d["service_name"] == SERVICE_NAME for d in body["degraded_services"])

def test_mock_endpoint_keeps_contacts_for_matching_region():
    with patch("app.main.db.save_recommendation", new=AsyncMock()):
        body = _client().get("/recommendation/mock/emergency_instructions?region=TH").json()
    assert len(body["official_contacts"]) == 2
