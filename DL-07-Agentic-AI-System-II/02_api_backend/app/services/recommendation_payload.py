"""Turn a validated Agent result into the stored, user-facing recommendation.

The Agent is untrusted: text is cleaned, links must be https and internal fields are
dropped (R-06); the Safety Gate decides status and action (R-01..R-05); data age and
validity are computed here, never taken from the Agent (R-07).

The payload is the RecommendationResponse without the per-request identifiers
(recommendation_id, conversation_id, request_id, created_at), so the same document can
be stored in the database and in the shared cache.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import (
    DataCategory,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from app.domain.freshness import (
    FreshnessInput,
    FreshnessReport,
    StalenessPolicy,
    assess_freshness,
    compute_valid_until,
)
from app.domain.safety_gate import CRITICAL_SOURCES, GateInput, GateResult, apply_safety_gate
from app.domain.sanitizer import clean_text, safe_url, strip_internal
from app.infrastructure.agent.contracts import AgentRunResponse

KNOWN_SERVICES = ("weather", "transport", "disaster", "risk_model", "rag", "llm")

DISCLAIMERS = {
    "th": "คำแนะนำนี้เป็นข้อมูลประกอบการตัดสินใจ โปรดติดตามประกาศจากหน่วยงานทางการ",
    "en": (
        "This advice supports your decision only. Always follow announcements from "
        "official authorities."
    ),
}


FALLBACK_REPLIES = {
    "th": "ยังให้คำแนะนำไม่ได้ในตอนนี้ เพราะข้อมูลไม่ครบ โปรดตรวจสอบประกาศจากหน่วยงานทางการ",
    "en": (
        "We could not give a recommendation because some data is missing. "
        "Check official announcements before you travel."
    ),
}


def fallback_reply(language: str) -> str:
    """Assistant text when the Agent gave neither advice nor a question (D-55)."""
    return FALLBACK_REPLIES["th" if language == "th" else "en"]


@dataclass(frozen=True, slots=True)
class Assessment:
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    summary: str | None
    warning_codes: tuple[str, ...]
    applied_rules: tuple[str, ...]
    overall_is_stale: bool
    valid_until: datetime | None
    payload: dict[str, Any]


def iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _freshness_inputs(response: AgentRunResponse) -> list[FreshnessInput]:
    inputs = [FreshnessInput(i.category, i.updated_at) for i in response.data_freshness.items]
    reported = {i.category for i in inputs}
    # A critical source the Agent did not mention is reported as missing, not hidden.
    inputs.extend(
        FreshnessInput(category, None)
        for category in CRITICAL_SOURCES.values()
        if category not in reported
    )
    return inputs


def _freshness_payload(report: FreshnessReport) -> dict[str, Any]:
    return {
        "overall_is_stale": report.overall_is_stale,
        "items": [
            {
                "category": item.category.value,
                "updated_at": iso(item.updated_at),
                "age_seconds": item.age_seconds,
                "is_stale": item.is_stale,
            }
            for item in report.items
        ],
    }


def _clean(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        if key == "url":
            return safe_url(value)
        return clean_text(value) or ""
    return value


def _recommendation(response: AgentRunResponse, gate: GateResult) -> dict[str, Any] | None:
    agent = response.recommendation
    if agent is None:
        return None
    removed = gate.recommendation_type is None and agent.type is not None
    return {
        "type": gate.recommendation_type.value if gate.recommendation_type else None,
        "summary": gate.summary,
        # Reasons and timing argued for the action the gate removed (D-48).
        "reasons": [] if removed else list(agent.reasons),
        "suggested_departure_time": None if removed else iso(agent.suggested_departure_time),
    }


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True) if model is not None else None


def _payload(
    response: AgentRunResponse,
    gate: GateResult,
    report: FreshnessReport,
    *,
    valid_until: datetime | None,
    language: str,
    api_version: str,
) -> dict[str, Any]:
    raw = {
        "status": gate.status.value,
        "valid_until": iso(valid_until),
        "language": language,
        "risk": _dump(response.risk),
        "recommendation": _recommendation(response, gate),
        "routes": _dump(response.routes),
        "hazards": [_dump(h) for h in response.hazards],
        "emergency_instructions": (
            copy.deepcopy(dict(gate.emergency_instructions))
            if gate.emergency_instructions is not None
            else None
        ),
        "sources": [_dump(s) for s in response.sources],
        "data_freshness": _freshness_payload(report),
        "service_status": {
            name: state.value
            for name, state in response.service_status.items()
            if name in KNOWN_SERVICES
        },
        "clarification": _dump(response.clarification),
        "warnings": [{"code": w.code.value, "message": w.message} for w in gate.warnings],
        "disclaimer": DISCLAIMERS["th" if language == "th" else "en"],
    }
    cleaned: dict[str, Any] = _clean(strip_internal(raw))
    # Added after stripping: "prompt" is an internal key elsewhere but a public version here.
    versions = response.versions
    cleaned["versions"] = _clean(
        {
            "api": api_version,
            "agent": versions.agent,
            "risk_model": versions.risk_model,
            "prompt": versions.prompt,
        }
    )
    return cleaned


def assess(
    response: AgentRunResponse,
    *,
    now: datetime,
    language: str,
    policy: StalenessPolicy,
    emergency_fallback: Mapping[str, Any] | None,
    low_confidence_below: float,
    api_version: str,
) -> Assessment:
    """Apply R-07, R-01..R-05 and R-06. Raises SafetyGateRejection."""
    report = assess_freshness(_freshness_inputs(response), now=now, policy=policy)
    risk = response.risk
    agent_action = response.recommendation
    gate = apply_safety_gate(
        GateInput(
            status=RecommendationStatus(response.status.value),
            risk_level=risk.level if risk else None,
            risk_confidence=risk.confidence if risk else None,
            recommendation_type=agent_action.type if agent_action else None,
            summary=agent_action.summary if agent_action else None,
            has_clarification=response.clarification is not None,
            emergency_instructions=_dump(response.emergency_instructions),
            service_status=response.service_status,
            freshness=report,
        ),
        language=language,
        emergency_fallback=emergency_fallback,
        low_confidence_below=low_confidence_below,
    )
    valid_until = compute_valid_until(response.valid_until, report, policy=policy, now=now)
    payload = _payload(
        response, gate, report, valid_until=valid_until, language=language, api_version=api_version
    )
    return Assessment(
        status=gate.status,
        risk_level=risk.level if risk else None,
        risk_score=risk.score if risk else None,
        risk_confidence=risk.confidence if risk else None,
        recommendation_type=gate.recommendation_type,
        summary=payload["recommendation"]["summary"] if payload["recommendation"] else None,
        warning_codes=tuple(w.code.value for w in gate.warnings),
        applied_rules=gate.applied_rules,
        overall_is_stale=report.overall_is_stale,
        valid_until=valid_until,
        payload=payload,
    )


def refresh_freshness(
    payload: Mapping[str, Any], *, now: datetime, policy: StalenessPolicy
) -> dict[str, Any] | None:
    """Recompute data age for a cached payload; None when any source became stale."""
    items = payload.get("data_freshness", {}).get("items", [])
    try:
        inputs = [
            FreshnessInput(
                DataCategory(item["category"]),
                datetime.fromisoformat(item["updated_at"]) if item["updated_at"] else None,
            )
            for item in items
        ]
    except (KeyError, TypeError, ValueError):
        return None
    report = assess_freshness(inputs, now=now, policy=policy)
    if report.overall_is_stale:
        return None
    refreshed = copy.deepcopy(dict(payload))
    refreshed["data_freshness"] = _freshness_payload(report)
    return refreshed
