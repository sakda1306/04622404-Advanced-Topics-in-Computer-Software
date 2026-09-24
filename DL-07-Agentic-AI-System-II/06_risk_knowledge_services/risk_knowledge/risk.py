"""Explainable conservative baseline risk assessment.

The numeric value is an uncalibrated normalized score. It must not be presented as
a probability until a trained model is calibrated and approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .evidence import module_record
from .models import (
    IntegratedEvidence,
    IntegratedTravelContext,
    Level,
    RiskFactorResult,
    RiskResult,
    as_mapping,
)


MODEL_VERSION = "rule-baseline-v0.1.2"
KNOWN_FEATURE_SCHEMAS = {None, "integrated-travel-v0.1-proposed"}
SEVERITY_SCORE = {"LOW": 0.2, "MEDIUM": 0.55, "HIGH": 0.85, "CRITICAL": 1.0}
BAD_QUALITY_FLAGS = {
    "missing",
    "stale",
    "conflicting",
    "incomplete",
    "unavailable",
    "partial",
    "freshness_unknown",
    "uncertain",
}


@dataclass(frozen=True)
class RiskThresholds:
    medium: float = 0.35
    high: float = 0.70

    def __post_init__(self) -> None:
        if not 0 <= self.medium < self.high <= 1:
            raise ValueError("thresholds must satisfy 0 <= medium < high <= 1")


def _level(score: float, thresholds: RiskThresholds) -> Level:
    if score >= thresholds.high:
        return Level.HIGH
    if score >= thresholds.medium:
        return Level.MEDIUM
    return Level.LOW


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _factor_from_record(record: IntegratedEvidence) -> tuple[float, RiskFactorResult | None, bool]:
    """Return score, factor, and whether the record is a hard safety constraint."""

    if record.status != "available" or record.freshness == "stale":
        return 0.0, None, False
    value = _mapping(record.value)
    severity = str(record.severity or value.get("severity") or "").upper()
    score = SEVERITY_SCORE.get(severity, 0.0)
    kind = record.record_kind

    if kind in {"closure", "official_alert"}:
        active = value.get("active", True)
        alert_level = str(value.get("level") or value.get("status") or "").upper()
        hard_level = kind == "closure" or alert_level in {"AVOID", "CLOSURE", "CLOSED"}
        if active is not False and hard_level:
            return 0.95, RiskFactorResult(
                type="OFFICIAL_RESTRICTION",
                level=Level.HIGH,
                description=f"Active {kind} record {record.record_id} is a hard safety constraint.",
            ), True

    if kind == "disaster_event" and score:
        level = _level(score, RiskThresholds())
        return score, RiskFactorResult(
            type="DISASTER_EVENT",
            level=level,
            description=f"Disaster record {record.record_id} has {severity} severity.",
        ), False

    if kind in {"current_weather", "weather_forecast"}:
        candidates: list[tuple[float, str]] = []
        rain = _number(value.get("precipitation_mm") or value.get("rain_mm"))
        wind = _number(value.get("wind_speed_kph") or value.get("wind_kph"))
        visibility = _number(value.get("visibility_km"))
        probability = _number(
            value.get("rain_probability") or value.get("precipitation_probability")
        )
        if rain is not None:
            candidates.append((0.80 if rain >= 50 else 0.50 if rain >= 20 else 0.20, "rain"))
        if wind is not None:
            candidates.append((0.85 if wind >= 90 else 0.55 if wind >= 50 else 0.15, "wind"))
        if visibility is not None:
            visibility_score = 0.80 if visibility < 1 else 0.50 if visibility < 3 else 0.10
            candidates.append((visibility_score, "visibility"))
        if probability is not None:
            probability = probability / 100 if probability > 1 else probability
            probability_score = (
                0.50 if probability >= 0.8 else 0.25 if probability >= 0.5 else 0.05
            )
            candidates.append((probability_score, "rain_probability"))
        if candidates:
            weather_score, feature = max(candidates)
            score = max(score, weather_score)
            return score, RiskFactorResult(
                type="WEATHER",
                level=_level(score, RiskThresholds()),
                description=f"Weather record {record.record_id} is elevated by {feature}.",
            ), False

    if kind == "transport_status":
        status = str(value.get("status") or "").upper()
        delay = _number(value.get("delay_minutes"))
        if status in {"CANCELLED", "CLOSED", "SUSPENDED"}:
            score = max(score, 0.85)
        elif delay is not None:
            score = max(score, 0.75 if delay >= 120 else 0.45 if delay >= 30 else 0.15)
        if score:
            return score, RiskFactorResult(
                type="TRANSPORT",
                level=_level(score, RiskThresholds()),
                description=f"Transport record {record.record_id} reports disruption or delay.",
            ), False

    if score:
        return score, RiskFactorResult(
            type="SOURCE_SEVERITY",
            level=_level(score, RiskThresholds()),
            description=f"Record {record.record_id} reports {severity} severity.",
        ), False
    return 0.0, None, False


def _confidence(context: IntegratedTravelContext, has_usable_evidence: bool) -> float:
    flags = {flag.lower() for flag in context.flags + context.quality_flags}
    for record in context.evidence:
        flags.update(flag.lower() for flag in record.quality_flags)
        if record.freshness in {None, "unknown"}:
            flags.add("freshness_unknown")
    bad = flags & BAD_QUALITY_FLAGS
    if "conflicting" in bad:
        return 0.10
    if not has_usable_evidence or len(bad) >= 3:
        return 0.25
    if context.degraded or bad:
        return 0.65
    if context.confidence is not None:
        if isinstance(context.confidence, Level):
            return {"LOW": 0.25, "MEDIUM": 0.65, "HIGH": 0.90}[context.confidence.value]
        return float(context.confidence)
    return 0.90


def assess_risk(
    context: IntegratedTravelContext | dict[str, Any] | None,
    *,
    thresholds: RiskThresholds = RiskThresholds(),
    now: datetime | None = None,
) -> RiskResult:
    """Assess route risk without inventing missing inputs.

    Official restrictions are hard overrides. Missing context returns a conservative
    HIGH result with LOW confidence so downstream policy can escalate safely.
    """

    current = (now or datetime.now(UTC)).astimezone(UTC)
    if context is None:
        factor = RiskFactorResult(
            type="DATA_UNAVAILABLE",
            level=Level.HIGH,
            description="Integrated travel context is unavailable; conservative fallback applied.",
        )
        return RiskResult(
            level=Level.HIGH,
            score=None,
            confidence=0.10,
            model_version=MODEL_VERSION,
            factors=[factor],
            records=[module_record("risk", factor.description, now=current)],
        )

    parsed = IntegratedTravelContext.model_validate(as_mapping(context))
    if parsed.feature_schema_version not in KNOWN_FEATURE_SCHEMAS:
        raise ValueError(f"unsupported feature_schema_version: {parsed.feature_schema_version}")

    factors: list[RiskFactorResult] = []
    score = 0.10
    hard_constraint = False
    usable = False
    for record in parsed.evidence:
        record_score, factor, hard = _factor_from_record(record)
        if record.status == "available" and record.freshness == "fresh":
            usable = True
        score = max(score, record_score)
        hard_constraint = hard_constraint or hard
        is_new_factor = factor and all(
            item.type != factor.type or item.description != factor.description for item in factors
        )
        if factor and is_new_factor:
            factors.append(factor)

    if parsed.active_restriction is True:
        score = max(score, 0.95)
        hard_constraint = True
        factors.append(RiskFactorResult(
            type="OFFICIAL_RESTRICTION",
            level=Level.HIGH,
            description="Integrated context reports an active travel restriction.",
        ))
    elif not parsed.evidence:
        factors.append(RiskFactorResult(
            type="DATA_INCOMPLETE",
            level=Level.MEDIUM,
            description=(
                "No detailed evidence was supplied; restriction status alone cannot establish "
                "low travel risk."
            ),
        ))

    evidence_incomplete = not parsed.evidence and parsed.active_restriction is not True
    risk_level = (
        Level.HIGH
        if hard_constraint
        else Level.MEDIUM
        if evidence_incomplete
        else _level(score, thresholds)
    )
    output_score = None if evidence_incomplete else round(score, 4)
    confidence = _confidence(parsed, usable or parsed.active_restriction is True)
    if not factors:
        factors.append(RiskFactorResult(
            type="NO_ELEVATED_FACTOR",
            level=Level.LOW,
            description="No supplied feature crossed an approved baseline threshold.",
        ))
    excerpt = (
        f"model={MODEL_VERSION}; score={output_score}; level={risk_level}; "
        f"confidence={confidence}; factors={','.join(item.type for item in factors)}"
    )
    return RiskResult(
        level=risk_level,
        score=output_score,
        confidence=confidence,
        model_version=MODEL_VERSION,
        factors=factors[:12],
        records=[module_record("risk", excerpt, now=current)],
    )
