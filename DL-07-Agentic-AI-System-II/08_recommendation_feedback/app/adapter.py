"""
Adapter to transform Module 07 (Decision & LLM Engine) DecisionResponse
into Module 08 RecommendationResponse.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog

from app.emergency import validate_emergency_content
from app.schema import (
    ActionCode,
    ConfidenceLevel,
    DegradedService,
    EmergencyContact,
    RecommendationResponse,
    RiskLevel,
    ServiceStatus,
    SourceCitation,
    SourceType,
)

logger = structlog.get_logger("adapter")


def _parse_dt(val: Any, default: Optional[datetime] = None) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return default or datetime.now(timezone.utc)


def decision_to_recommendation(
    decision: dict[str, Any],
    *,
    traveler_region: Optional[str] = None,
    now: Optional[datetime] = None,
) -> RecommendationResponse:
    """
    Transforms a 07 DecisionResponse dictionary into a validated 08 RecommendationResponse,
    validates emergency contacts against the traveler's region, and returns the model.
    """
    current_time = now or datetime.now(timezone.utc)

    # 1. Action code
    action_str = decision.get("backend_action_code") or decision.get("action_code", "AVOID_TRAVEL")
    try:
        action_code = ActionCode(action_str)
    except ValueError:
        logger.warning("unknown_action_code_falling_back", action=action_str)
        action_code = ActionCode.AVOID_TRAVEL

    # 2. Risk level
    risk_str = decision.get("risk_level")
    if risk_str:
        try:
            risk_level = RiskLevel(risk_str)
        except ValueError:
            risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.MEDIUM

    # 3. Confidence & confidence_level
    raw_conf = decision.get("confidence")
    if isinstance(raw_conf, (int, float)):
        conf_float = max(0.0, min(1.0, float(raw_conf)))
    else:
        conf_float = 0.5

    if conf_float >= 0.7:
        confidence_level = ConfidenceLevel.HIGH
    elif conf_float >= 0.4:
        confidence_level = ConfidenceLevel.MEDIUM
    else:
        confidence_level = ConfidenceLevel.LOW

    # 4. Explanation
    explanation = decision.get("explanation", {})
    short_summary = explanation.get("summary", "ไม่มีคำอธิบายสรุป")
    immediate_actions = list(explanation.get("instructions", []))
    reasons = list(explanation.get("reasons", []))

    # 5. Limitations
    uncertainty = list(explanation.get("uncertainty", []))
    escalation = list(decision.get("escalation_reasons", []))
    issues = list(decision.get("emergency_assessment", {}).get("issues", []))
    limitations = sorted(set(uncertainty + escalation + issues))

    # 6. Degraded services
    degraded_list = decision.get("degraded_services", [])
    degraded_services = [
        DegradedService(service_name=str(name), status=ServiceStatus.DEGRADED)
        for name in degraded_list
    ]

    # 7. Sources
    sources: list[SourceCitation] = []
    for cit in decision.get("citations", []):
        try:
            sources.append(
                SourceCitation(
                    name=cit.get("source_name", "official"),
                    source_type=SourceType.OFFICIAL,
                    url=cit.get("url"),
                    published_at=_parse_dt(cit.get("observed_at")),
                )
            )
        except Exception:  # noqa: BLE001
            continue

    # 8. Emergency instructions & contacts
    emergency_instructions: list[str] = []
    official_contacts: list[EmergencyContact] = []

    em_data = decision.get("emergency_instructions")
    if isinstance(em_data, list):
        # 07 handoff fragment format (list of instruction strings)
        emergency_instructions.extend([str(item) for item in em_data if item])
    elif isinstance(em_data, dict):
        # 07 DecisionResponse model format
        what_now = em_data.get("what_to_do_now")
        if what_now:
            emergency_instructions.append(what_now)
        emergency_instructions.extend(em_data.get("safety_steps", []))

        # Contacts mapping from 07 model (contacts + metadata)
        raw_contacts = em_data.get("contacts", [])
        metadata_map = decision.get("emergency_contact_metadata", {})

        for idx, c in enumerate(raw_contacts):
            meta = metadata_map.get(str(idx), {})
            contact_type = meta.get("contact_type") or c.get("contact_type", "hotline")
            region = meta.get("region") or c.get("region", "TH")
            eff_date_raw = meta.get("effective_date") or c.get("effective_date")
            effective_date = _parse_dt(eff_date_raw, default=current_time - timedelta(days=1))

            try:
                official_contacts.append(
                    EmergencyContact(
                        name=c.get("name", "หน่วยงานฉุกเฉิน"),
                        phone=c.get("phone", "191"),
                        contact_type=contact_type,
                        region=region,
                        effective_date=effective_date,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("contact_mapping_skipped", contact=c, error=str(exc))

    # Also handle official_contacts if supplied directly (as in 07 handoff fragment)
    if "official_contacts" in decision and isinstance(decision["official_contacts"], list):
        for c in decision["official_contacts"]:
            try:
                official_contacts.append(
                    EmergencyContact(
                        name=c.get("name", "หน่วยงานฉุกเฉิน"),
                        phone=c.get("phone", "191"),
                        contact_type=c.get("contact_type", "hotline"),
                        region=c.get("region", "TH"),
                        effective_date=_parse_dt(c.get("effective_date"), default=current_time - timedelta(days=1)),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("direct_contact_mapping_skipped", contact=c, error=str(exc))

    # 9. Timestamps
    evaluated_at = _parse_dt(decision.get("evaluated_at"), default=current_time)
    valid_until = _parse_dt(
        decision.get("valid_until"), default=evaluated_at + timedelta(hours=1)
    )

    fetched_at = evaluated_at
    observed_at = evaluated_at - timedelta(minutes=5)
    expires_at = valid_until if valid_until > fetched_at else fetched_at + timedelta(hours=1)

    # 10. Build unvalidated RecommendationResponse
    recommendation = RecommendationResponse(
        request_id=str(decision.get("request_id", "00000000-0000-0000-0000-000000000000")),
        action_code=action_code,
        risk_level=risk_level,
        confidence=conf_float,
        confidence_level=confidence_level,
        short_summary=short_summary,
        immediate_actions=immediate_actions,
        primary_route=None,
        alternative_routes=[],
        emergency_instructions=emergency_instructions,
        official_contacts=official_contacts,
        reasons=reasons,
        sources=sources,
        observed_at=observed_at,
        fetched_at=fetched_at,
        expires_at=expires_at,
        limitations=limitations,
        degraded_services=degraded_services,
    )

    # 11. Run 08 emergency contact validation against traveler_region
    return validate_emergency_content(recommendation, traveler_region, now=current_time)


def apply_emergency_fragment(
    recommendation: RecommendationResponse,
    fragment: dict[str, Any],
    *,
    traveler_region: Optional[str] = None,
    now: Optional[datetime] = None,
) -> RecommendationResponse:
    """
    Applies a 07 emergency handoff fragment (from 07/decision_engine/handoff.py)
    directly onto an existing RecommendationResponse, then validates the contacts
    against traveler_region using app.emergency.validate_emergency_content.
    """
    current_time = now or datetime.now(timezone.utc)
    new_instructions = list(recommendation.emergency_instructions)
    for inst in fragment.get("emergency_instructions", []):
        if inst and inst not in new_instructions:
            new_instructions.append(str(inst))

    new_contacts = list(recommendation.official_contacts)
    for c in fragment.get("official_contacts", []):
        try:
            contact_obj = EmergencyContact(
                name=c["name"],
                phone=c["phone"],
                contact_type=c.get("contact_type", "hotline"),
                region=c.get("region", "TH"),
                effective_date=_parse_dt(c.get("effective_date"), default=current_time - timedelta(days=1)),
            )
            new_contacts.append(contact_obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fragment_contact_skipped", contact=c, error=str(exc))

    new_limitations = sorted(set(recommendation.limitations + fragment.get("limitations", [])))

    updated = recommendation.model_copy(
        update={
            "emergency_instructions": new_instructions,
            "official_contacts": new_contacts,
            "limitations": new_limitations,
        }
    )
    return validate_emergency_content(updated, traveler_region, now=current_time)
