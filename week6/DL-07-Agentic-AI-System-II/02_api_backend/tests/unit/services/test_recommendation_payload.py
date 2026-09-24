from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.enums import RecommendationStatus, RecommendationType, RiskLevel
from app.domain.freshness import StalenessPolicy
from app.domain.safety_gate import SafetyGateRejection
from app.infrastructure.agent.contracts import AgentRunResponse, AgentVersions
from app.services.ports import StoredResult
from app.services.recommendation_payload import Assessment, assess, refresh_freshness
from mock_agent.main import SCENARIOS, build_result

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
RUN_ID = "0192f0c2-aaaa-7bbb-8ccc-123456789abc"
POLICY = StalenessPolicy.default()
FALLBACK = {"what_to_do_now": "Go to a safe place.", "contacts": [{"name": "EMS", "phone": "1669"}]}


def agent_body(name: str) -> dict[str, Any]:
    return build_result(SCENARIOS[name], RUN_ID, NOW)


def run(
    body: dict[str, Any],
    *,
    language: str = "en",
    fallback: dict[str, Any] | None = None,
) -> Assessment:
    return assess(
        AgentRunResponse.model_validate(body),
        now=NOW,
        language=language,
        policy=POLICY,
        emergency_fallback=fallback,
        low_confidence_below=0.5,
        api_version="1.0.0",
    )


def test_low_risk_result_is_complete_and_fresh() -> None:
    result = run(agent_body("low_risk"))

    payload = result.payload
    assert result.status is RecommendationStatus.COMPLETED
    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert result.risk_level is RiskLevel.LOW
    assert payload["warnings"] == []
    assert payload["status"] == "completed"
    assert payload["recommendation"]["type"] == "TRAVEL_NORMALLY"
    assert payload["data_freshness"]["overall_is_stale"] is False
    assert len(payload["data_freshness"]["items"]) == 3
    # Transport is 120 s old with a 600 s limit, the earliest expiry (R-07).
    assert result.valid_until == NOW + timedelta(seconds=480)
    assert payload["valid_until"] == "2026-09-17T08:08:00Z"
    assert payload["versions"] == {
        "api": "1.0.0",
        "agent": "mock-0.1.0",
        "risk_model": "mock-risk-2026.09",
        "prompt": "mock-advice-v1",
    }
    assert payload["routes"]["primary"]["legs"][0]["from"] == "Krung Thep Aphiwat"
    assert "diagnostics" not in json.dumps(payload)
    assert "mock-trace" not in json.dumps(payload)


def test_disclaimer_follows_the_language() -> None:
    english = run(agent_body("low_risk"), language="en").payload["disclaimer"]
    thai = run(agent_body("low_risk"), language="th").payload["disclaimer"]

    assert english.startswith("This advice")
    assert thai.startswith("คำแนะนำนี้")


def test_missing_disaster_data_never_says_travel_normally() -> None:
    result = run(agent_body("partial_disaster_down"))

    payload = result.payload
    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is None
    assert payload["recommendation"]["type"] is None
    assert payload["recommendation"]["reasons"] == []
    assert payload["recommendation"]["summary"].startswith("Weather or disaster data")
    assert result.warning_codes == ("DATA_INCOMPLETE", "SERVICE_DEGRADED", "LOW_CONFIDENCE")
    assert result.applied_rules == ("R-02", "R-03")
    disaster = next(i for i in payload["data_freshness"]["items"] if i["category"] == "DISASTER")
    assert disaster == {
        "category": "DISASTER",
        "updated_at": None,
        "age_seconds": None,
        "is_stale": True,
    }
    assert result.overall_is_stale is True


def test_unreported_disaster_category_is_added_as_missing() -> None:
    body = agent_body("low_risk")
    body["data_freshness"]["items"] = [
        i for i in body["data_freshness"]["items"] if i["category"] != "DISASTER"
    ]

    result = run(body)

    categories = [i["category"] for i in result.payload["data_freshness"]["items"]]
    assert "DISASTER" in categories
    assert result.recommendation_type is None


def test_high_risk_keeps_agent_emergency_instructions() -> None:
    result = run(agent_body("high_risk"))

    payload = result.payload
    assert result.risk_level is RiskLevel.HIGH
    assert payload["emergency_instructions"]["contacts"][0]["phone"] == "1669"
    assert payload["hazards"][0]["type"] == "FLOOD"
    assert result.valid_until == NOW + timedelta(seconds=480)
    assert result.applied_rules == ()


def test_high_risk_without_instructions_uses_the_fallback() -> None:
    body = agent_body("high_risk")
    body["emergency_instructions"] = None

    result = run(body, fallback=FALLBACK)

    assert result.payload["emergency_instructions"]["what_to_do_now"] == "Go to a safe place."
    assert "R-01" in result.applied_rules
    assert "DATA_INCOMPLETE" in result.warning_codes


def test_high_risk_without_instructions_or_fallback_is_rejected() -> None:
    body = agent_body("high_risk")
    body["emergency_instructions"] = None

    with pytest.raises(SafetyGateRejection) as info:
        run(body)

    assert info.value.rule == "R-01"


def test_high_risk_with_travel_normally_needs_safety_review() -> None:
    body = agent_body("high_risk")
    body["recommendation"]["type"] = "TRAVEL_NORMALLY"

    with pytest.raises(SafetyGateRejection) as info:
        run(body)

    assert info.value.rule == "R-04"
    assert info.value.needs_safety_review is True


def test_clarification_is_passed_through() -> None:
    result = run(agent_body("needs_clarification"))

    payload = result.payload
    assert result.status is RecommendationStatus.NEEDS_CLARIFICATION
    assert payload["clarification"]["question"] == "Which day do you plan to travel?"
    assert payload["risk"] is None
    assert payload["recommendation"] is None


def test_untrusted_text_links_and_fields_are_cleaned() -> None:
    body = agent_body("high_risk")
    body["recommendation"]["summary"] = "Avoid travel\x07‮"
    body["sources"][0]["url"] = "javascript:alert(1)"
    body["emergency_instructions"]["contacts"][0]["url"] = "http://example.org"
    body["hazards"][0]["area"]["_debug"] = {"prompt": "secret"}
    body["hazards"][0]["internal_score"] = 3
    body["service_status"]["internal_router"] = "ok"

    payload = run(body).payload

    assert payload["recommendation"]["summary"] == "Avoid travel"
    assert payload["sources"][0]["url"] is None
    assert payload["emergency_instructions"]["contacts"][0]["url"] is None
    assert "_debug" not in payload["hazards"][0]["area"]
    assert "internal_score" not in payload["hazards"][0]
    assert "internal_router" not in payload["service_status"]


def test_unknown_degraded_service_is_hidden_but_still_counts() -> None:
    body = agent_body("low_risk")
    body["service_status"]["geocoder"] = "degraded"

    result = run(body)

    assert "geocoder" not in result.payload["service_status"]
    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert "SERVICE_DEGRADED" in result.warning_codes


def test_refresh_freshness_updates_ages() -> None:
    payload = run(agent_body("low_risk")).payload

    refreshed = refresh_freshness(payload, now=NOW + timedelta(seconds=60), policy=POLICY)

    assert refreshed is not None
    ages = {i["category"]: i["age_seconds"] for i in refreshed["data_freshness"]["items"]}
    assert ages == {"WEATHER": 1260, "TRANSPORT": 180, "DISASTER": 240}
    assert payload["data_freshness"]["items"][0]["age_seconds"] == 1200  # input unchanged


def test_refresh_freshness_rejects_data_that_became_stale() -> None:
    payload = run(agent_body("low_risk")).payload

    assert refresh_freshness(payload, now=NOW + timedelta(seconds=600), policy=POLICY) is None


@pytest.mark.parametrize(("language", "start"), [("en", "We could not"), ("th", "ยังให้คำแนะนำ")])
def test_stored_result_always_has_a_reply(language: str, start: str) -> None:
    body = agent_body("partial_disaster_down")
    body["recommendation"] = None

    assessment = run(body, language=language)
    stored = StoredResult.from_assessment(assessment, versions=AgentVersions(), api_version="1.0.0")

    assert assessment.summary is None
    assert stored.message is not None
    assert stored.message.startswith(start)


def test_stored_result_uses_the_clarifying_question() -> None:
    assessment = run(agent_body("needs_clarification"))

    stored = StoredResult.from_assessment(assessment, versions=AgentVersions(), api_version="1.0.0")

    assert stored.message == "Which day do you plan to travel?"
