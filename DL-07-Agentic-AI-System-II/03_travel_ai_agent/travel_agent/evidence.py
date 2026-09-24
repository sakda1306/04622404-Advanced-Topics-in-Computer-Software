"""Build Module 07's DecisionRequest (decision_engine/models.py) from tool results.

07 rejects the whole package if any part disagrees on request/route/time or cites an
evidence ID that is not in the package, so everything here shares one `context` and
only references records that were collected in this run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from travel_agent.contracts import RiskLevel
from travel_agent.tools.schemas import QUALITY_FLAGS, Record

if TYPE_CHECKING:
    from travel_agent.pipeline import AgentState

MAX_EVIDENCE_IDS = 12  # per item, within 07's EvidenceIds limit (1..32)
MAX_EVIDENCE_PACKAGE = 64  # 07's DecisionRequest.evidence limit


def _ids(records: list[Record]) -> list[str]:
    return [r.id for r in records if r.id][:MAX_EVIDENCE_IDS]


def locale_for(language: str) -> str:
    return "th-TH" if language.lower().startswith("th") else "en-US"


def primary_route_id(state: AgentState) -> str:
    if state.routes:
        return state.routes.primary.route_id
    if state.context:
        return state.context.resolved_primary_route_id
    return "primary"


def build_decision_request(state: AgentState) -> dict[str, Any]:
    departure = state.run.request.departure_time
    context = {
        "request_id": str(state.run.run_id),
        "route_id": primary_route_id(state),
        "departure_time": departure.isoformat(),
    }
    payload: dict[str, Any] = {
        "context": context,
        "locale": locale_for(state.run.request.language),
        "emergency_context": {
            "context": context,
            "region": "TH",
            "hazard": "GENERAL",
        },
        "quality": _quality(state, context),
        "alerts": [],
    }

    if state.risk:
        payload["risk"] = {
            "context": context,
            "level": state.risk.level,
            "confidence": state.risk.confidence,
            "model_version": state.risk.model_version,
            "evidence_ids": _ids(state.risk.records),
        }
    for name, result in (("weather", state.weather), ("transport", state.transport)):
        if result:
            payload[name] = {
                "context": context,
                "text": result.summary,
                "evidence_ids": _ids(result.records),
            }
    if state.disasters:
        payload["alerts"] = [
            {
                "context": context,
                "level": alert.level,
                "active": alert.active,
                "evidence_ids": _ids([alert.record]),
            }
            for alert in state.disasters.alerts
        ]
    if routes := state.routes:
        # 07 checks that each claim cites evidence of its own kind (route vs time).
        route_ids = _ids([r for r in routes.records if r.kind == "route"])
        time_ids = _ids([r for r in routes.records if r.kind == "time"])
        seen = {routes.primary.route_id}
        alternatives = []
        for option in routes.alternatives:
            if option.route_id in seen:
                continue  # 07 requires unique alternatives that differ from the primary
            seen.add(option.route_id)
            alternatives.append(
                {
                    "route_id": option.route_id,
                    "risk_level": option.risk_level,
                    "usable": option.usable,
                    "clearly_safer": option.clearly_safer,
                    "evidence_ids": route_ids,
                }
            )
        if route_ids:
            payload["routes"] = {
                "context": context,
                "no_safe_route": routes.no_safe_route,
                "alternatives": alternatives,
                "evidence_ids": route_ids,
            }
        later = routes.suggested_departure_time
        # A "safer later" claim without a later time is not usable evidence.
        safer_later = routes.safer_later and later is not None and later > departure
        if time_ids:
            payload["time_assessment"] = {
                "context": context,
                "safer_later": safer_later,
                "suggested_departure_time": later.isoformat() if safer_later else None,
                "evidence_ids": time_ids,
            }

    referenced: set[str] = set()
    if "risk" in payload:
        referenced.update(payload["risk"]["evidence_ids"])
    for key in ("weather", "transport"):
        if key in payload:
            referenced.update(payload[key]["evidence_ids"])
    for alert in payload.get("alerts", []):
        referenced.update(alert["evidence_ids"])
    if "routes" in payload:
        referenced.update(payload["routes"]["evidence_ids"])
        for alt in payload["routes"].get("alternatives", []):
            referenced.update(alt["evidence_ids"])
    if "time_assessment" in payload:
        referenced.update(payload["time_assessment"]["evidence_ids"])

    all_records = {r.id: r for r in state.records() if r.id}
    selected_ids = list(dict.fromkeys([*referenced, *all_records.keys()]))[:MAX_EVIDENCE_PACKAGE]
    payload["evidence"] = [
        {
            "context": context,
            "evidence_id": r_id,
            **all_records[r_id].model_dump(mode="json", exclude={"id"}),
        }
        for r_id in selected_ids
        if r_id in all_records
    ]
    return payload


def _quality(state: AgentState, context: dict[str, Any]) -> dict[str, Any]:
    integrated = state.context
    # 05 reports coverage in its own words. Keep the ones 07 defines and drop the rest
    # instead of translating them into a stronger or weaker claim.
    flags = (
        {flag for flag in integrated.all_flags if flag in QUALITY_FLAGS}
        if integrated
        else {"incomplete"}
    )
    if integrated and integrated.degraded and not flags:
        flags.add("incomplete")
    required = (
        state.weather,
        state.transport,
        state.disasters,
        state.candidates,
        state.risk,
        state.routes,
    )
    if any(result is None for result in required):
        flags.add("missing")
    return {
        "context": context,
        "confidence": (
            integrated.confidence if integrated and integrated.confidence else RiskLevel.LOW
        ),
        "flags": sorted(flags),
        # Unknown restriction status stays None; it must never read as "no restriction".
        "active_restriction": integrated.active_restriction if integrated else None,
        "data_version": (
            integrated.data_version or integrated.feature_schema_version or "unversioned"
            if integrated
            else "unintegrated"
        ),
        "schema_version": "07-draft-v3",
    }
