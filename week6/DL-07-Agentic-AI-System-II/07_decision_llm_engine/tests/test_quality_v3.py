import pytest
from pydantic import ValidationError

from decision_engine.config import Settings
from decision_engine.policy import Policy


@pytest.mark.parametrize(
    "flag,meaning", [("partial", "incomplete"), ("freshness_unknown", "freshness_requires_review")]
)
@pytest.mark.parametrize("scenario", ["low_risk", "safer_route", "safer_time"])
def test_new_flags_block_optimistic_actions(client, samples, flag, meaning, scenario):
    body = samples[scenario]
    body["quality"]["flags"] = [flag]
    response = client.post("/v1/decisions", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["action_code"] == "AVOID"
    assert result["selected_route_id"] is None
    assert result["suggested_departure_time"] is None
    assert result["confidence"] <= 0.25
    assert {flag, meaning} <= set(result["escalation_reasons"])
    assert result["escalation_required"]
    assert result["versions"]["policy"] == "prototype-v3"
    assert result["versions"]["schema_version"] == "07-draft-v3"


@pytest.mark.parametrize(
    "scenario,rule", [("high_risk", "HIGH_RISK"), ("closure", "OFFICIAL_RESTRICTION")]
)
def test_new_flags_preserve_warning_precedence(client, samples, scenario, rule):
    body = samples[scenario]
    body["quality"]["flags"] = ["partial", "freshness_unknown"]
    result = client.post("/v1/decisions", json=body).json()
    assert result["rules_fired"] == [rule]
    assert result["action_code"] == "AVOID"
    assert result["confidence"] <= 0.25


def test_all_flags_and_unknown_flag(client, samples):
    body = samples["low_risk"]
    body["quality"]["flags"] = [
        "missing",
        "stale",
        "conflicting",
        "incomplete",
        "inferred",
        "partial",
        "freshness_unknown",
    ]
    result = client.post("/v1/decisions", json=body)
    assert result.status_code == 200
    assert result.json()["confidence"] == 0.1
    body["quality"]["flags"] = ["invented_flag"]
    assert client.post("/v1/decisions", json=body).status_code == 422


def test_summary_only_and_partial_route_do_not_imply_safe(client, samples):
    for scenario in ("summary_only_risk", "partial_alternative"):
        result = client.post("/v1/decisions", json=samples[scenario]).json()
        assert result["action_code"] == "AVOID"
        assert result["confidence"] <= 0.25
        assert result["selected_route_id"] is None
        assert result["escalation_required"]


def test_old_policy_requires_matching_old_code():
    with pytest.raises(ValueError):
        Policy.load("prototype-v2")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, decision_policy_version="prototype-v2")
