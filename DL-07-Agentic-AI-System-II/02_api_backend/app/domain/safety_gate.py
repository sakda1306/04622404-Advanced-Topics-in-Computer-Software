"""Safety Gate: rules R-01 to R-05 of docs/02_api_spec.md section 5.4.

A wrong "safe" answer can hurt someone, so when data is missing the result degrades
honestly instead of guessing. The gate either returns an adjusted result or raises
`SafetyGateRejection` when the Agent result cannot be shown at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.enums import (
    DataCategory,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    ServiceState,
    WarningCode,
)
from app.domain.errors import DomainError
from app.domain.freshness import FreshnessReport

# Services whose absence makes "travel normally" unprovable (R-02).
CRITICAL_SOURCES = {"weather": DataCategory.WEATHER, "disaster": DataCategory.DISASTER}
_AVAILABLE = frozenset({ServiceState.OK, ServiceState.DEGRADED})
_TROUBLED = frozenset({ServiceState.DEGRADED, ServiceState.UNAVAILABLE})

_MESSAGES = {
    "en": {
        WarningCode.DATA_INCOMPLETE: "Some safety data is missing.",
        WarningCode.DATA_STALE: "Some safety data is out of date.",
        WarningCode.SERVICE_DEGRADED: "Some services are degraded; details may be limited.",
        WarningCode.LOW_CONFIDENCE: "The risk estimate has low confidence.",
        "incomplete_summary": (
            "Weather or disaster data is incomplete, so we cannot confirm it is safe to "
            "travel. Check official announcements before you go."
        ),
    },
    "th": {
        WarningCode.DATA_INCOMPLETE: "ข้อมูลด้านความปลอดภัยบางส่วนขาดหายไป",
        WarningCode.DATA_STALE: "ข้อมูลด้านความปลอดภัยบางส่วนไม่เป็นปัจจุบัน",
        WarningCode.SERVICE_DEGRADED: "บางบริการทำงานไม่เต็มที่ รายละเอียดอาจไม่ครบ",
        WarningCode.LOW_CONFIDENCE: "การประเมินความเสี่ยงมีความเชื่อมั่นต่ำ",
        "incomplete_summary": (
            "ข้อมูลสภาพอากาศหรือภัยพิบัติไม่ครบถ้วน จึงยืนยันไม่ได้ว่าเดินทางได้อย่างปลอดภัย "
            "โปรดตรวจสอบประกาศจากหน่วยงานทางการก่อนเดินทาง"
        ),
    },
}


@dataclass(frozen=True, slots=True)
class GateInput:
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    summary: str | None
    has_clarification: bool
    emergency_instructions: Mapping[str, Any] | None
    service_status: Mapping[str, ServiceState]
    freshness: FreshnessReport


@dataclass(frozen=True, slots=True)
class GateWarning:
    code: WarningCode
    message: str


@dataclass(frozen=True, slots=True)
class GateResult:
    status: RecommendationStatus
    recommendation_type: RecommendationType | None
    summary: str | None
    emergency_instructions: Mapping[str, Any] | None
    warnings: tuple[GateWarning, ...]
    applied_rules: tuple[str, ...]


class SafetyGateRejection(DomainError):
    def __init__(
        self,
        rule: str,
        reason: str,
        *,
        needs_safety_review: bool = False,
        agent_failed: bool = False,
    ) -> None:
        super().__init__(f"{rule}: {reason}")
        self.rule = rule
        self.needs_safety_review = needs_safety_review
        self.agent_failed = agent_failed


class _Builder:
    def __init__(self, inp: GateInput, language: str) -> None:
        self.messages = _MESSAGES["th" if language.lower().startswith("th") else "en"]
        self.status = inp.status
        self.recommendation_type = inp.recommendation_type
        self.summary = inp.summary
        self.emergency_instructions = inp.emergency_instructions
        self.warnings: list[GateWarning] = []
        self.rules: list[str] = []

    def warn(self, code: WarningCode) -> None:
        if all(w.code is not code for w in self.warnings):
            self.warnings.append(GateWarning(code, str(self.messages[code])))

    def apply(self, rule: str) -> None:
        if rule not in self.rules:
            self.rules.append(rule)

    def downgrade(self) -> None:
        if self.status is RecommendationStatus.COMPLETED:
            self.status = RecommendationStatus.PARTIAL_RESULT

    def result(self) -> GateResult:
        return GateResult(
            status=self.status,
            recommendation_type=self.recommendation_type,
            summary=self.summary,
            emergency_instructions=self.emergency_instructions,
            warnings=tuple(self.warnings),
            applied_rules=tuple(self.rules),
        )


def _check_contract(inp: GateInput) -> None:
    if inp.status is RecommendationStatus.FAILED:
        raise SafetyGateRejection("AGENT_FAILED", "agent reported failure", agent_failed=True)
    if inp.status is RecommendationStatus.NEEDS_CLARIFICATION:
        if not inp.has_clarification:
            raise SafetyGateRejection("R-05", "clarification status without a question")
        return
    if inp.risk_level is RiskLevel.HIGH and (
        inp.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    ):
        raise SafetyGateRejection(
            "R-04", "high risk combined with travel normally", needs_safety_review=True
        )
    if inp.status is RecommendationStatus.COMPLETED and (
        inp.risk_level is None or inp.recommendation_type is None
    ):
        raise SafetyGateRejection("R-05", "completed result without risk or action")


def _critical_data_problems(inp: GateInput) -> list[WarningCode]:
    problems: list[WarningCode] = []
    for service, category in CRITICAL_SOURCES.items():
        item = inp.freshness.get(category)
        unavailable = inp.service_status.get(service) not in _AVAILABLE
        if unavailable or item is None or item.updated_at is None:
            problems.append(WarningCode.DATA_INCOMPLETE)
        elif item.is_stale:
            problems.append(WarningCode.DATA_STALE)
    return problems


def apply_safety_gate(
    inp: GateInput,
    *,
    language: str,
    emergency_fallback: Mapping[str, Any] | None,
    low_confidence_below: float = 0.5,
) -> GateResult:
    _check_contract(inp)
    out = _Builder(inp, language)
    if inp.status is RecommendationStatus.NEEDS_CLARIFICATION:
        return out.result()

    # R-02: without fresh weather and disaster data, "safe" cannot be claimed.
    problems = _critical_data_problems(inp)
    if problems:
        out.apply("R-02")
        out.downgrade()
        for code in problems:
            out.warn(code)
        if out.recommendation_type is RecommendationType.TRAVEL_NORMALLY:
            out.recommendation_type = None
            out.summary = str(out.messages["incomplete_summary"])

    # R-03: other degraded dependencies make the answer partial.
    if any(state in _TROUBLED for state in inp.service_status.values()):
        out.apply("R-03")
        out.downgrade()
        out.warn(WarningCode.SERVICE_DEGRADED)

    # R-01: high risk always comes with emergency instructions.
    if inp.risk_level is RiskLevel.HIGH and out.emergency_instructions is None:
        if emergency_fallback is None:
            raise SafetyGateRejection("R-01", "high risk without emergency instructions")
        out.apply("R-01")
        out.emergency_instructions = emergency_fallback
        out.warn(WarningCode.DATA_INCOMPLETE)

    if inp.risk_confidence is not None and inp.risk_confidence < low_confidence_below:
        out.warn(WarningCode.LOW_CONFIDENCE)

    return out.result()
