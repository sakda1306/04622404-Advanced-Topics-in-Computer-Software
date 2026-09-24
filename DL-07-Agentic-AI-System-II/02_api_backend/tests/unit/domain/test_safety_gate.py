from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.enums import (
    DataCategory,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    ServiceState,
    WarningCode,
)
from app.domain.freshness import FreshnessInput, StalenessPolicy, assess_freshness
from app.domain.safety_gate import (
    GateInput,
    SafetyGateRejection,
    apply_safety_gate,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
OK = ServiceState.OK
FALLBACK: Mapping[str, Any] = {
    "what_to_do_now": "Move to a safe place.",
    "safety_steps": [],
    "contacts": [{"name": "Police", "phone": "191"}],
    "nearest_support": [],
}
AGENT_STEPS: Mapping[str, Any] = {**FALLBACK, "what_to_do_now": "Agent steps"}


def report(**ages: float | None) -> Any:
    items = [
        FreshnessInput(
            DataCategory(name.upper()), None if m is None else NOW - timedelta(minutes=m)
        )
        for name, m in ages.items()
    ]
    return assess_freshness(items, now=NOW, policy=StalenessPolicy.default())


def gate_input(**overrides: Any) -> GateInput:
    base = GateInput(
        status=RecommendationStatus.COMPLETED,
        risk_level=RiskLevel.LOW,
        risk_confidence=0.9,
        recommendation_type=RecommendationType.TRAVEL_NORMALLY,
        summary="Safe to travel.",
        has_clarification=False,
        emergency_instructions=None,
        service_status={"weather": OK, "transport": OK, "disaster": OK},
        freshness=report(weather=5, transport=1, disaster=1),
    )
    return replace(base, **overrides)


def run(
    inp: GateInput, *, language: str = "en", fallback: Mapping[str, Any] | None = FALLBACK
) -> Any:
    return apply_safety_gate(inp, language=language, emergency_fallback=fallback)


def codes(result: Any) -> list[WarningCode]:
    return [w.code for w in result.warnings]


# ------------------------------------------------------------ clean pass


def test_complete_and_fresh_result_passes_unchanged() -> None:
    result = run(gate_input())

    assert result.status is RecommendationStatus.COMPLETED
    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert result.summary == "Safe to travel."
    assert result.warnings == ()
    assert result.applied_rules == ()


# ------------------------------------------------------------ R-02


@pytest.mark.parametrize(
    ("overrides", "warning"),
    [
        (
            {
                "service_status": {
                    "weather": OK,
                    "transport": OK,
                    "disaster": ServiceState.UNAVAILABLE,
                }
            },
            WarningCode.DATA_INCOMPLETE,
        ),
        (
            {"service_status": {"weather": ServiceState.NOT_USED, "transport": OK, "disaster": OK}},
            WarningCode.DATA_INCOMPLETE,
        ),
        ({"service_status": {"transport": OK, "disaster": OK}}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1)}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1, disaster=None)}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1, disaster=16)}, WarningCode.DATA_STALE),
        ({"freshness": report(weather=61, transport=1, disaster=1)}, WarningCode.DATA_STALE),
    ],
)
def test_r02_missing_or_stale_critical_data_blocks_travel_normally(
    overrides: dict[str, Any], warning: WarningCode
) -> None:
    result = run(gate_input(**overrides))

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is None
    assert "incomplete" in (result.summary or "")
    assert warning in codes(result)
    assert "R-02" in result.applied_rules


def test_r02_message_follows_the_language() -> None:
    inp = gate_input(freshness=report(weather=5, transport=1))

    assert "ไม่ครบถ้วน" in (run(inp, language="th").summary or "")


@pytest.mark.parametrize(
    "action",
    [
        RecommendationType.AVOID_TRAVEL,
        RecommendationType.DELAY_TRAVEL,
        RecommendationType.CHANGE_ROUTE,
    ],
)
def test_r02_keeps_a_more_cautious_action(action: RecommendationType) -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.MEDIUM,
            recommendation_type=action,
            summary="Delay your trip.",
            freshness=report(weather=5, transport=1),
        )
    )

    assert result.recommendation_type is action
    assert result.summary == "Delay your trip."
    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert WarningCode.DATA_INCOMPLETE in codes(result)


def test_r02_does_not_fire_when_only_transport_is_stale() -> None:
    result = run(gate_input(freshness=report(weather=5, transport=30, disaster=1)))

    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert "R-02" not in result.applied_rules


# ------------------------------------------------------------ R-03


@pytest.mark.parametrize(
    "status",
    [
        {"weather": OK, "transport": ServiceState.DEGRADED, "disaster": OK},
        {"weather": OK, "transport": OK, "disaster": OK, "llm": ServiceState.UNAVAILABLE},
        {"weather": ServiceState.DEGRADED, "transport": OK, "disaster": OK},
    ],
)
def test_r03_degraded_dependency_makes_a_partial_result(status: dict[str, ServiceState]) -> None:
    result = run(gate_input(service_status=status))

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert codes(result) == [WarningCode.SERVICE_DEGRADED]
    assert result.applied_rules == ("R-03",)


def test_r03_not_used_service_is_not_degraded() -> None:
    status = {"weather": OK, "transport": OK, "disaster": OK, "rag": ServiceState.NOT_USED}

    assert run(gate_input(service_status=status)).warnings == ()


# ------------------------------------------------------------ R-01


def test_r01_high_risk_without_steps_gets_the_regional_fallback() -> None:
    result = run(
        gate_input(risk_level=RiskLevel.HIGH, recommendation_type=RecommendationType.AVOID_TRAVEL)
    )

    assert result.emergency_instructions == FALLBACK
    assert WarningCode.DATA_INCOMPLETE in codes(result)
    assert result.applied_rules == ("R-01",)


def test_r01_agent_steps_are_kept() -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.HIGH,
            recommendation_type=RecommendationType.AVOID_TRAVEL,
            emergency_instructions=AGENT_STEPS,
        )
    )

    assert result.emergency_instructions == AGENT_STEPS
    assert result.applied_rules == ()


def test_r01_without_fallback_rejects_the_result() -> None:
    inp = gate_input(risk_level=RiskLevel.HIGH, recommendation_type=RecommendationType.AVOID_TRAVEL)

    with pytest.raises(SafetyGateRejection) as info:
        run(inp, fallback=None)

    assert info.value.rule == "R-01"
    assert info.value.agent_failed is False


def test_r01_does_not_apply_below_high_risk() -> None:
    result = run(
        gate_input(risk_level=RiskLevel.MEDIUM, recommendation_type=RecommendationType.CHANGE_ROUTE)
    )

    assert result.emergency_instructions is None
    assert result.applied_rules == ()


# ------------------------------------------------------------ R-04


def test_r04_high_risk_with_travel_normally_is_rejected_for_review() -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(risk_level=RiskLevel.HIGH, emergency_instructions=AGENT_STEPS))

    assert info.value.rule == "R-04"
    assert info.value.needs_safety_review is True


def test_r04_is_checked_before_r02_can_hide_it() -> None:
    inp = gate_input(risk_level=RiskLevel.HIGH, freshness=report(weather=5, transport=1))

    with pytest.raises(SafetyGateRejection) as info:
        run(inp)

    assert info.value.rule == "R-04"


# ------------------------------------------------------------ R-05 and contract checks


def test_r05_clarification_passes_without_risk_or_action() -> None:
    result = run(
        gate_input(
            status=RecommendationStatus.NEEDS_CLARIFICATION,
            risk_level=None,
            risk_confidence=None,
            recommendation_type=None,
            summary=None,
            has_clarification=True,
            service_status={},
            freshness=report(),
        )
    )

    assert result.status is RecommendationStatus.NEEDS_CLARIFICATION
    assert result.recommendation_type is None
    assert result.warnings == ()


def test_r05_clarification_status_without_question_is_rejected() -> None:
    inp = gate_input(
        status=RecommendationStatus.NEEDS_CLARIFICATION,
        recommendation_type=None,
        has_clarification=False,
    )

    with pytest.raises(SafetyGateRejection) as info:
        run(inp)

    assert info.value.rule == "R-05"


@pytest.mark.parametrize(
    "overrides",
    [{"recommendation_type": None}, {"risk_level": None}],
)
def test_completed_result_needs_risk_and_action(overrides: dict[str, Any]) -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(**overrides))

    assert info.value.rule == "R-05"


def test_partial_result_may_come_without_an_action() -> None:
    result = run(
        gate_input(
            status=RecommendationStatus.PARTIAL_RESULT,
            recommendation_type=None,
            summary=None,
            freshness=report(weather=5, transport=1),
        )
    )

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is None


def test_agent_failure_is_rejected_as_unavailable() -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(status=RecommendationStatus.FAILED))

    assert info.value.agent_failed is True


# ------------------------------------------------------------ confidence and combinations


def test_low_confidence_adds_a_warning_only() -> None:
    result = run(gate_input(risk_confidence=0.49))

    assert codes(result) == [WarningCode.LOW_CONFIDENCE]
    assert result.status is RecommendationStatus.COMPLETED


def test_confidence_at_threshold_is_fine() -> None:
    assert run(gate_input(risk_confidence=0.5)).warnings == ()


def test_all_rules_together_keep_one_warning_per_code() -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.HIGH,
            risk_confidence=0.2,
            recommendation_type=RecommendationType.AVOID_TRAVEL,
            service_status={
                "weather": OK,
                "transport": ServiceState.DEGRADED,
                "disaster": ServiceState.UNAVAILABLE,
            },
            freshness=report(weather=5, transport=1),
        )
    )

    assert codes(result) == [
        WarningCode.DATA_INCOMPLETE,
        WarningCode.SERVICE_DEGRADED,
        WarningCode.LOW_CONFIDENCE,
    ]
    assert result.applied_rules == ("R-02", "R-03", "R-01")
    assert result.recommendation_type is RecommendationType.AVOID_TRAVEL
    assert result.emergency_instructions == FALLBACK
