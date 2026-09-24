from dataclasses import replace
from datetime import datetime

from .audit import AuditStore
from .config import Settings
from .emergency import EmergencyCatalog, build_emergency
from .evidence import references
from .explanation import ExplanationProvider, explain
from .models import BACKEND_ACTIONS, DecisionRequest, DecisionResponse, Versions
from .policy import Policy, evaluate


async def decide(
    request: DecisionRequest,
    *,
    now: datetime,
    settings: Settings,
    policy: Policy,
    audit: AuditStore,
    emergency_catalog: EmergencyCatalog | None = None,
    provider: ExplanationProvider | None = None,
) -> DecisionResponse:
    decision = evaluate(request, now, policy)
    catalog = emergency_catalog or EmergencyCatalog.load(settings.emergency_catalog_path)
    emergency, emergency_status, emergency_expiry = build_emergency(request, decision, now, catalog)
    # Missing emergency guidance does not reinterpret the already locked risk/action score.
    decision = replace(
        decision,
        issues=tuple(sorted(set(decision.issues) | set(emergency_status.issues))),
        escalation_required=decision.escalation_required or bool(emergency_status.issues),
    )
    citations, evidence_status = references(request, decision, now, emergency_status)
    explanation, checks = await explain(
        decision, request, settings, provider, [item.evidence_id for item in citations]
    )
    result = DecisionResponse(
        request_id=request.context.request_id,
        action_code=decision.action,
        backend_action_code=BACKEND_ACTIONS[decision.action],
        risk_level=request.risk.level if request.risk else None,
        confidence=decision.confidence,
        confidence_details=decision.confidence_details,
        emergency_instructions=emergency,
        emergency_contact_metadata={
            str(index): contact.metadata
            for index, contact in enumerate(emergency.contacts if emergency else [])
            if contact.metadata is not None
        },
        emergency_assessment=emergency_status,
        escalation_required=decision.escalation_required,
        escalation_reasons=list(decision.issues),
        selected_route_id=decision.selected_route_id,
        suggested_departure_time=decision.suggested_departure_time,
        explanation=explanation,
        citations=citations,
        evidence_status=evidence_status,
        rules_fired=[decision.rule_id],
        degraded_services=["llm"] if explanation.mode == "template" else [],
        validation_results=[
            "INPUT_SCHEMA_VALID",
            "CONTEXT_MATCHED",
            "ACTION_LOCKED",
            "EMERGENCY_" + emergency_status.status.upper(),
            *checks,
        ],
        versions=Versions(
            emergency_catalog=catalog.content.version,
            emergency_catalog_sha256=catalog.digest,
            policy=policy.version,
            policy_sha256=policy.digest,
            prompt=settings.prompt_version,
            model=settings.llm_model_explainer if explanation.mode == "provider" else "template-v1",
            risk_model=request.risk.model_version if request.risk else None,
            data=request.quality.data_version,
        ),
        evaluated_at=now,
        valid_until=min(
            [e.expires_at for e in request.evidence]
            + ([emergency_expiry] if emergency_expiry else []),
            default=None,
        ),
    )
    audit.append(result)
    return result
