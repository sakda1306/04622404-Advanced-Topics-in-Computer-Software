from copy import deepcopy
from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from decision_engine.models import Action, DecisionRequest
from decision_engine.policy import Policy, evaluate
from decision_engine.sample_data import scenarios


@pytest.mark.parametrize(
    ("scenario", "action", "rule"),
    [
        ("low_risk", "NORMAL", "LOW_RISK_CLEAR"),
        ("high_risk", "AVOID", "HIGH_RISK"),
        ("closure", "AVOID", "OFFICIAL_RESTRICTION"),
        ("safer_route", "CHANGE_ROUTE", "SAFER_ROUTE"),
        ("safer_time", "DELAY", "SAFER_TIME"),
        ("missing_data", "AVOID", "INSUFFICIENT_EVIDENCE"),
        ("stale_data", "AVOID", "INSUFFICIENT_EVIDENCE"),
        ("conflicting_data", "AVOID", "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_golden_scenarios(client, samples, scenario, action, rule):
    response = client.post("/v1/decisions", json=samples[scenario])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action_code"] == action
    assert body["rules_fired"] == [rule]
    assert body["explanation"]["mode"] == "template"
    assert body["versions"]["policy_status"] == "prototype"
    assert body["prototype_only"] is True
    assert body["confidence_kind"] == "heuristic_policy_score"


def test_closure_overrides_alternative_and_time(client, samples):
    body = samples["safer_route"]
    body["alerts"] = samples["closure"]["alerts"]
    body["time_assessment"] = samples["safer_time"]["time_assessment"]
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert result["rules_fired"] == ["OFFICIAL_RESTRICTION"]
    assert result["selected_route_id"] is None
    assert result["suggested_departure_time"] is None


def test_supported_restriction_is_not_itself_low_confidence(client, samples):
    result = client.post("/v1/decisions", json=samples["closure"]).json()
    assert result["action_code"] == "AVOID"
    assert result["confidence"] == 0.9
    assert result["escalation_reasons"] == [
        "emergency_context_missing",
        "emergency_guidance_unavailable",
    ]


@pytest.mark.parametrize("mutation", ["closed", "not_safer", "same_risk"])
def test_unsupported_alternative_never_selected(client, samples, mutation):
    body = samples["safer_route"]
    option = body["routes"]["alternatives"][0]
    if mutation == "closed":
        option["usable"] = False
    elif mutation == "not_safer":
        option["clearly_safer"] = False
    else:
        option["risk_level"] = "MEDIUM"
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert result["escalation_required"]


@pytest.mark.parametrize("field", ["request_id", "route_id", "departure_time"])
def test_context_mismatch_rejected_without_echoing_input(client, samples, field):
    body = deepcopy(samples["low_risk"])
    changes = {
        "request_id": "00000000-0000-4000-8000-000000000008",
        "route_id": "PRIVATE-LOCATION-DO-NOT-ECHO",
        "departure_time": "2026-09-18T16:00:00Z",
    }
    body["risk"]["context"] = {**body["risk"]["context"], field: changes[field]}
    response = client.post("/v1/decisions", json=body)
    assert response.status_code == 422
    assert "PRIVATE-LOCATION" not in response.text
    assert "input" not in response.json()["errors"][0]


@pytest.mark.parametrize("case", ["unknown", "duplicate", "no_timezone", "credentials"])
def test_invalid_evidence_rejected(client, samples, case):
    body = samples["low_risk"]
    if case == "unknown":
        body["risk"]["evidence_ids"] = ["absent"]
    elif case == "duplicate":
        body["evidence"].append(deepcopy(body["evidence"][0]))
    elif case == "no_timezone":
        body["evidence"][0]["observed_at"] = "2026-09-18T11:00:00"
    else:
        body["evidence"][0]["url"] = "https://secret:password@example.org/"
    assert client.post("/v1/decisions", json=body).status_code == 422


@pytest.mark.parametrize("flag", ["missing", "stale", "conflicting", "incomplete", "inferred"])
def test_quality_flags_prevent_normal(client, samples, flag):
    body = samples["low_risk"]
    body["quality"]["flags"] = [flag]
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert result["confidence"] <= 0.25
    assert result["escalation_required"]


def test_freshness_boundary_and_future_fetch(client, samples, now):
    body = samples["low_risk"]
    body["evidence"][0]["expires_at"] = (now + timedelta(microseconds=1)).isoformat()
    assert client.post("/v1/decisions", json=body).json()["action_code"] == "NORMAL"
    body["evidence"][0]["expires_at"] = now.isoformat()
    assert client.post("/v1/decisions", json=body).json()["action_code"] == "AVOID"
    body = samples["safer_route"]
    body["evidence"][0]["fetched_at"] = (now + timedelta(seconds=1)).isoformat()
    result = client.post("/v1/decisions", json=body).json()
    assert "future_data" in result["escalation_reasons"]
    assert result["selected_route_id"] is None


def test_no_safe_route_and_low_confidence(client, samples):
    body = samples["low_risk"]
    body["routes"]["no_safe_route"] = True
    assert client.post("/v1/decisions", json=body).json()["rules_fired"] == ["NO_SAFE_ROUTE"]
    body["routes"]["no_safe_route"] = False
    body["risk"]["confidence"] = "LOW"
    assert client.post("/v1/decisions", json=body).json()["action_code"] == "AVOID"


@pytest.mark.parametrize("case", ["alert", "routes"])
def test_derived_conflicts_escalate_even_if_upstream_flags_are_empty(client, samples, case):
    body = samples["safer_route"]
    if case == "alert":
        body["alerts"] = samples["closure"]["alerts"]
        body["quality"]["active_restriction"] = False
    else:
        body["routes"]["no_safe_route"] = True
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert "conflicting" in result["escalation_reasons"]
    assert result["confidence"] <= 0.25
    assert result["escalation_required"]


def test_stale_unverified_unused_evidence_is_not_a_valid_citation(client, samples, now):
    body = samples["closure"]
    body["evidence"][5]["official_source"] = False
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert result["citations"] == []
    statuses = {item["evidence_id"]: item for item in result["evidence_status"]}
    assert statuses["mock-official"]["used_by_decision"]
    assert "unverified_warning" in statuses["mock-official"]["validation_issues"]
    body = samples["high_risk"]
    body["evidence"][0]["expires_at"] = now.isoformat()
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert result["citations"] == []
    assert result["escalation_required"]


def test_unknown_restriction_caution_and_unverified_alert(client, samples):
    body = samples["low_risk"]
    body["quality"]["active_restriction"] = None
    assert client.post("/v1/decisions", json=body).json()["action_code"] == "AVOID"
    body = samples["closure"]
    body["alerts"][0]["level"] = "CAUTION"
    body["evidence"][5]["official_source"] = False
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert "unverified_warning" in result["escalation_reasons"]
    assert "caution_requires_review" in result["escalation_reasons"]


def test_evidence_type_mismatch_blocks_normal(client, samples):
    body = samples["low_risk"]
    body["risk"]["evidence_ids"] = ["mock-weather"]
    result = client.post("/v1/decisions", json=body).json()
    assert result["action_code"] == "AVOID"
    assert "evidence_kind_mismatch" in result["escalation_reasons"]


def test_alternative_id_and_later_time_validation(samples):
    body = samples["safer_route"]
    body["routes"]["alternatives"][0]["route_id"] = "mock-primary"
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(body)
    body = samples["safer_time"]
    body["time_assessment"]["suggested_departure_time"] = body["context"]["departure_time"]
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(body)


@given(st.sampled_from(["low_risk", "safer_route", "safer_time"]), st.booleans())
def test_increasing_to_high_never_weakens_decision(scenario, has_closure):
    from datetime import UTC, datetime

    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    data = scenarios(now)
    body = data[scenario]
    body["risk"]["level"] = "HIGH"
    if has_closure:
        body["alerts"] = data["closure"]["alerts"]
    request = DecisionRequest.model_validate(body)
    policy = Policy.load("prototype-v3")
    first = evaluate(request, now, policy)
    assert first.action == Action.AVOID
    assert evaluate(request, now, policy) == first
