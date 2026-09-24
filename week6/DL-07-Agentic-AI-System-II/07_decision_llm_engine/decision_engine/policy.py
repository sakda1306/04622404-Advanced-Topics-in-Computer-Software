import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Action, DecisionRequest, Level

LEVEL_RANK = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2}


@dataclass(frozen=True)
class Policy:
    version: str
    digest: str
    rules: tuple[tuple[str, Action], ...]
    confidence_config: dict
    quality_flag_issues: dict[str, str]

    @classmethod
    def load(cls, version: str) -> "Policy":
        if version != "prototype-v3":
            raise ValueError("Unsupported policy version")
        raw = (Path(__file__).parent / "policies" / f"{version}.json").read_bytes()
        manifest = json.loads(raw)
        if manifest["version"] != version or manifest["status"] != "prototype":
            raise ValueError("Policy manifest does not match its declared version/status")
        return cls(
            version=version,
            digest=hashlib.sha256(raw).hexdigest(),
            confidence_config=manifest["confidence"],
            quality_flag_issues=manifest["quality_flag_issues"],
            rules=tuple((rule["id"], Action(rule["action"])) for rule in manifest["rules"]),
        )


@dataclass(frozen=True)
class Decision:
    action: Action
    rule_id: str
    confidence: float
    confidence_details: dict[str, float]
    issues: tuple[str, ...]
    escalation_required: bool
    selected_route_id: str | None = None
    suggested_departure_time: datetime | None = None


def normalize_confidence(value, policy: Policy) -> float:
    if isinstance(value, Level):
        return policy.confidence_config["ordinal_mapping"][value.value]
    return float(value)


def score_confidence(request: DecisionRequest, now: datetime, policy: Policy, issues: set[str]):
    base = min(
        normalize_confidence(request.quality.confidence, policy),
        normalize_confidence(request.risk.confidence, policy) if request.risk else 0.0,
    )
    completeness = (
        sum(
            p is not None
            for p in (request.risk, request.weather, request.transport, request.routes)
        )
        / 4
    )
    freshness = sum(e.fetched_at <= now < e.expires_at for e in request.evidence) / max(
        len(request.evidence), 1
    )
    cap = 1.0
    if issues:
        cap = policy.confidence_config["issue_cap"]
    if "conflicting" in issues:
        cap = policy.confidence_config["conflict_cap"]
    # Do not round across the escalation threshold.
    score = min(base * completeness * freshness, cap)
    return score, {
        "base": base,
        "completeness": completeness,
        "freshness": freshness,
        "issue_cap": cap,
    }


def evaluate(request: DecisionRequest, now: datetime, policy: Policy) -> Decision:
    issues = set(request.quality.flags)
    # Preserve the received flags and add their policy meaning for reviewers.
    issues.update(
        policy.quality_flag_issues[flag]
        for flag in request.quality.flags
        if flag in policy.quality_flag_issues
    )
    required = (request.risk, request.weather, request.transport, request.routes)
    if any(part is None for part in required) or not request.evidence:
        issues.add("missing")
    if request.quality.active_restriction is None:
        issues.add("restriction_unknown")
    threshold = policy.confidence_config["escalation_threshold"]
    if normalize_confidence(request.quality.confidence, policy) < threshold or (
        request.risk and normalize_confidence(request.risk.confidence, policy) < threshold
    ):
        issues.add("low_confidence")
    if any(item.expires_at <= now for item in request.evidence):
        issues.add("stale")
    if any(item.fetched_at > now for item in request.evidence):
        issues.add("future_data")
    if request.context.departure_time < now:
        issues.add("departure_in_past")

    by_id = {item.evidence_id: item for item in request.evidence}
    active_alerts = [alert for alert in request.alerts if alert.active]
    if request.quality.active_restriction and not any(
        alert.level in {"AVOID", "CLOSURE"} for alert in active_alerts
    ):
        issues.add("restriction_requires_review")
    if active_alerts and request.quality.active_restriction is False:
        issues.add("conflicting")
    if (
        request.routes
        and request.routes.no_safe_route
        and any(
            route.usable and route.risk_level == Level.LOW for route in request.routes.alternatives
        )
    ):
        issues.add("conflicting")
    for alert in active_alerts:
        if any(
            by_id[eid].kind != "official" or not by_id[eid].official_source
            for eid in alert.evidence_ids
        ):
            issues.add("unverified_warning")
        if alert.level == "CAUTION":
            # The guide does not define warning-level mapping: request review.
            issues.add("caution_requires_review")

    # An assertion must refer to the matching evidence category, not arbitrary IDs.
    typed_parts = (
        (request.risk, "risk"),
        (request.weather, "weather"),
        (request.transport, "transport"),
        (request.routes, "route"),
        (request.time_assessment, "time"),
    )
    for part, kind in typed_parts:
        if part and any(by_id[eid].kind != kind for eid in part.evidence_ids):
            issues.add("evidence_kind_mismatch")
    if request.routes:
        for route in request.routes.alternatives:
            if any(by_id[eid].kind != "route" for eid in route.evidence_ids):
                issues.add("evidence_kind_mismatch")

    if (
        score_confidence(request, now, policy, issues)[0]
        < policy.confidence_config["escalation_threshold"]
    ):
        issues.add("low_confidence")

    # Deterministic tie-breaking; HIGH never yields a weaker action via an alternative.
    alternatives = sorted(
        (
            option
            for option in (request.routes.alternatives if request.routes else [])
            if option.usable
            and option.clearly_safer
            and request.risk
            and LEVEL_RANK[option.risk_level] < LEVEL_RANK[request.risk.level]
        ),
        key=lambda option: (LEVEL_RANK[option.risk_level], option.route_id),
    )
    later = request.time_assessment
    conditions = {
        "OFFICIAL_RESTRICTION": any(a.level in {"AVOID", "CLOSURE"} for a in active_alerts),
        "HIGH_RISK": request.risk is not None and request.risk.level == Level.HIGH,
        "NO_SAFE_ROUTE": request.routes is not None and request.routes.no_safe_route,
        "INSUFFICIENT_EVIDENCE": bool(issues),
        "SAFER_ROUTE": bool(alternatives),
        "SAFER_TIME": later is not None and later.safer_later,
        "LOW_RISK_CLEAR": request.risk is not None
        and request.risk.level == Level.LOW
        and request.quality.active_restriction is False
        and not active_alerts,
        "UNRESOLVED": True,
    }
    for rule_id, action in policy.rules:
        if not conditions[rule_id]:
            continue
        if rule_id == "UNRESOLVED":
            issues.add("unresolved_policy")
        confidence, details = score_confidence(request, now, policy, issues)
        return Decision(
            action=action,
            rule_id=rule_id,
            confidence=confidence,
            confidence_details=details,
            issues=tuple(sorted(issues)),
            escalation_required=bool(issues),
            selected_route_id=alternatives[0].route_id if action == Action.CHANGE_ROUTE else None,
            suggested_departure_time=(
                later.suggested_departure_time if action == Action.DELAY and later else None
            ),
        )
    raise RuntimeError("Policy must contain a terminal rule")
