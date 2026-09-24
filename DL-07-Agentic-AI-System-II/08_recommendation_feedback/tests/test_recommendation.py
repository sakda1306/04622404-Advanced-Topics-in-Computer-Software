"""
Unit tests that do NOT require a running Postgres/Redis — safe to run with
plain `pytest` on a laptop, in CI, or inside the app container.

For tests against the real database (via docker compose), see
tests/test_db_integration.py, which is skipped automatically if
DATABASE_URL is unreachable.
"""

import asyncio

import pytest
from pydantic import ValidationError

from app.live_update import AlertEvent, FakeRedis, LiveUpdateBroker
from app.mock_data import ALL_SCENARIOS
from app.schema import ActionCode, RecommendationResponse, RiskLevel
from app.feedback import classify_free_text, FeedbackCategory


# ---------------------------------------------------------------------------
# Schema / fixture snapshot tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_name", list(ALL_SCENARIOS.keys()))
def test_mock_scenario_matches_schema(scenario_name):
    scenario = ALL_SCENARIOS[scenario_name]
    assert isinstance(scenario, RecommendationResponse)
    dumped = scenario.model_dump_json()
    restored = RecommendationResponse.model_validate_json(dumped)
    assert restored == scenario


def test_expires_at_after_fetched_at_is_enforced():
    # NB: model_copy(update=...) skips validation in pydantic v2, so the
    # payload must go through model_validate to exercise the validator.
    scenario = ALL_SCENARIOS["travel_normally"]
    bad = {**scenario.model_dump(), "expires_at": scenario.fetched_at}
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(bad)


# ---------------------------------------------------------------------------
# Contract alignment (Contract Register v3)
# ---------------------------------------------------------------------------

def test_risk_levels_match_other_modules():
    assert {r.value for r in RiskLevel} == {"LOW", "MEDIUM", "HIGH"}


def test_action_codes_match_02_backend_names():
    assert {a.value for a in ActionCode} == {
        "TRAVEL_NORMALLY", "CHANGE_ROUTE", "DELAY_TRAVEL", "AVOID_TRAVEL",
    }


@pytest.mark.parametrize("legacy", ["MODERATE", "CRITICAL"])
def test_legacy_risk_values_are_rejected(legacy):
    payload = {**ALL_SCENARIOS["travel_normally"].model_dump(mode="json"), "risk_level": legacy}
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(payload)


def test_legacy_emergency_action_code_is_rejected():
    payload = {
        **ALL_SCENARIOS["travel_normally"].model_dump(mode="json"),
        "action_code": "EMERGENCY_INSTRUCTIONS",
    }
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(payload)


def test_null_emergency_fields_from_03_are_accepted():
    """03 currently forwards emergency_instructions = null (register open question)."""
    payload = {
        **ALL_SCENARIOS["travel_normally"].model_dump(mode="json"),
        "emergency_instructions": None,
        "official_contacts": None,
    }
    r = RecommendationResponse.model_validate(payload)
    assert r.emergency_instructions == []
    assert r.official_contacts == []


def test_emergency_scenario_has_contacts_and_instructions():
    e = ALL_SCENARIOS["emergency_instructions"]
    assert e.action_code == ActionCode.AVOID_TRAVEL
    assert e.risk_level == RiskLevel.HIGH
    assert len(e.emergency_instructions) > 0
    assert len(e.official_contacts) > 0


def test_change_route_scenario_has_waypoints_for_map_rendering():
    r = ALL_SCENARIOS["change_route"]
    assert len(r.primary_route.waypoints) > 0
    assert len(r.alternative_routes[0].waypoints) > 0


def test_confidence_may_be_null_when_only_categorical_level_is_known():
    """
    Mirrors what 03_travel_ai_agent forwards today: 07 only emits a
    categorical confidence (LOW/MEDIUM/HIGH), so the numeric field is
    null until the team agrees on a 0-1 scale. The schema must accept
    this instead of rejecting the payload.
    """
    r = ALL_SCENARIOS["delay_travel"]
    assert r.confidence is None
    assert r.confidence_level is not None

    # Round-trips through JSON the same as every other fixture.
    restored = RecommendationResponse.model_validate_json(r.model_dump_json())
    assert restored.confidence is None
    assert restored.confidence_level == r.confidence_level


# ---------------------------------------------------------------------------
# Feedback classification (pure function, no DB)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "comment,expected",
    [
        ("This felt unsafe and dangerous", FeedbackCategory.UNSAFE),
        ("The info was outdated", FeedbackCategory.STALE),
        ("The route suggestion was wrong", FeedbackCategory.ROUTE_ISSUE),
        ("The forecast was wrong", FeedbackCategory.INCORRECT),
        ("The source link is broken", FeedbackCategory.SOURCE_ISSUE),
        ("It was cold but the advice worked great", FeedbackCategory.HELPFUL),
        ("Thanks, worked great", FeedbackCategory.HELPFUL),
    ],
)
def test_classify_free_text(comment, expected):
    assert classify_free_text(comment) == expected


# ---------------------------------------------------------------------------
# Live update: consent, dedup, cooldown, severity override (FakeRedis only)
# ---------------------------------------------------------------------------

def test_no_consent_blocks_send():
    broker = LiveUpdateBroker(cooldown_seconds=60, redis_client=FakeRedis())
    event = AlertEvent("user-1", "req-1", RiskLevel.HIGH, "Alert")
    sent = asyncio.run(broker.publish(event))
    assert sent is False


def test_cooldown_suppresses_same_severity_repeat():
    broker = LiveUpdateBroker(cooldown_seconds=300, redis_client=FakeRedis())
    broker.grant_consent("user-1")
    e1 = AlertEvent("user-1", "req-1", RiskLevel.MEDIUM, "Rain")
    e2 = AlertEvent("user-1", "req-1", RiskLevel.MEDIUM, "Still rain", timestamp=e1.timestamp + 5)

    assert asyncio.run(broker.publish(e1)) is True
    assert asyncio.run(broker.publish(e2)) is False


def test_severity_increase_overrides_cooldown():
    broker = LiveUpdateBroker(cooldown_seconds=300, redis_client=FakeRedis())
    broker.grant_consent("user-1")
    e1 = AlertEvent("user-1", "req-1", RiskLevel.MEDIUM, "Rain")
    e2 = AlertEvent("user-1", "req-1", RiskLevel.HIGH, "Flash flood", timestamp=e1.timestamp + 5)

    assert asyncio.run(broker.publish(e1)) is True
    assert asyncio.run(broker.publish(e2)) is True


def test_legacy_risk_value_in_redis_does_not_break_or_suppress_alerts():
    redis = FakeRedis()
    broker = LiveUpdateBroker(cooldown_seconds=300, redis_client=redis)
    broker.grant_consent("user-1")
    now = 1_000_000.0
    redis._store["live_update:last_sent:user-1"] = str(now)
    redis._store["live_update:last_risk:user-1"] = "CRITICAL"  # written before the change -> HIGH
    same = AlertEvent("user-1", "req-1", RiskLevel.HIGH, "still high", timestamp=now + 5)
    assert asyncio.run(broker.publish(same)) is False  # equal severity inside cooldown
    redis._store["live_update:last_risk:user-1"] = "MODERATE"  # -> MEDIUM
    higher = AlertEvent("user-1", "req-1", RiskLevel.HIGH, "worse", timestamp=now + 10)
    assert asyncio.run(broker.publish(higher)) is True  # increase is never suppressed
