"""Deterministic, locally reviewed guidance. Retrieved text is never executed or rendered."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from .handoff import contact_issues
from .models import (
    Action,
    Contract,
    DecisionRequest,
    EmergencyAssessment,
    EmergencyInstructions,
    Evidence,
    Identifier,
)
from .policy import Decision


class Procedure(Contract):
    procedure_id: Identifier
    status: Literal["reviewed"]
    region: Identifier
    hazard: Identifier
    locale: Literal["th-TH", "en-US"]
    source_url: HttpUrl
    # Legacy: hash of Module 06's composed excerpt string, tied to its formatting.
    excerpt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Preferred: hash of the passage content (decision_engine/hashing.py), independent
    # of how 06 lays the excerpt out.
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reviewed_at: AwareDatetime
    expires_at: AwareDatetime
    instructions: EmergencyInstructions

    @model_validator(mode="after")
    def valid_review(self):
        if self.reviewed_at >= self.expires_at:
            raise ValueError("Review must expire after it was recorded")
        if not self.excerpt_sha256 and not self.content_sha256:
            raise ValueError("A reviewed procedure needs excerpt_sha256 or content_sha256")
        if (
            self.source_url.scheme != "https"
            or self.source_url.username
            or self.source_url.password
        ):
            raise ValueError("Catalog source must be credential-free HTTPS")
        for contact in self.instructions.contacts:
            if contact.metadata and (
                contact.metadata.region.casefold() != self.region.casefold()
                or contact.metadata.source_url != self.source_url
            ):
                raise ValueError("Contact metadata must match the reviewed procedure scope/source")
            if contact.url and (
                contact.url.scheme != "https" or contact.url.username or contact.url.password
            ):
                raise ValueError("Contact URL must be credential-free HTTPS")
        return self


class Catalog(Contract):
    version: Identifier
    procedures: list[Procedure] = Field(max_length=100)
    fallback: dict[str, EmergencyInstructions]

    @model_validator(mode="after")
    def unique_scopes(self):
        ids = [p.procedure_id for p in self.procedures]
        scopes = [(p.region, p.hazard, p.locale) for p in self.procedures]
        if len(ids) != len(set(ids)) or len(scopes) != len(set(scopes)):
            raise ValueError("Duplicate catalog ID or scope; resolve conflicting guidance first")
        if set(self.fallback) != {"th-TH", "en-US"}:
            raise ValueError("Both fallback locales are required")
        if any(f.contacts or f.nearest_support for f in self.fallback.values()):
            raise ValueError("Fallback cannot assert local contacts or support locations")
        return self


@dataclass(frozen=True)
class EmergencyCatalog:
    content: Catalog
    digest: str

    @classmethod
    def load(cls, path: Path | None = None):
        path = path or Path(__file__).parent / "templates" / "emergency-v1.json"
        raw = path.read_bytes()
        return cls(Catalog.model_validate_json(raw), hashlib.sha256(raw).hexdigest())


def _identity_and_integrity(evidence: Evidence, procedure: "Procedure") -> list[str]:
    """Is this the reviewed passage, and does its content still match the review?

    Identity is the source the review covers. Integrity is a hash comparison, kept
    separate so that content drift is reported as drift instead of looking like a
    passage that was never reviewed. A procedure that carries the content hash is
    matched on it; `excerpt_sha256` remains for catalogs reviewed before that existed.
    """
    if evidence.url != procedure.source_url:
        return ["emergency_source_not_matched"]
    if procedure.content_sha256:
        if evidence.content_sha256 is None:
            # The producer has not adopted the content hash: we cannot prove the text
            # is the reviewed one, and guessing from the display string is what this
            # replaces.
            return ["emergency_content_hash_missing"]
        if evidence.content_sha256 != procedure.content_sha256:
            return ["emergency_source_changed"]
        return []
    if hashlib.sha256(evidence.excerpt.encode("utf-8")).hexdigest() != procedure.excerpt_sha256:
        return ["emergency_source_changed"]
    return []


def build_emergency(
    request: DecisionRequest, decision: Decision, now: datetime, catalog: EmergencyCatalog
):
    if decision.action != Action.AVOID:
        return None, EmergencyAssessment(status="not_required"), None
    ctx = request.emergency_context
    procedure = next(
        (
            p
            for p in catalog.content.procedures
            if ctx and (p.region, p.hazard, p.locale) == (ctx.region, ctx.hazard, request.locale)
        ),
        None,
    )
    rejected = {}
    eligible = []
    for evidence in request.evidence:
        if evidence.kind != "knowledge":
            continue
        reasons = []
        if not evidence.official_source:
            reasons.append("emergency_unverified_source")
        if not evidence.fetched_at <= now < evidence.expires_at:
            reasons.append("emergency_source_not_current")
        if procedure is None:
            reasons.append("emergency_scope_not_reviewed")
        else:
            if not procedure.reviewed_at <= now < procedure.expires_at:
                reasons.append("emergency_review_not_current")
            reasons.extend(_identity_and_integrity(evidence, procedure))
        if reasons:
            rejected[evidence.evidence_id] = reasons
        else:
            eligible.append(evidence)
    # Conflicting source facts require human review, not automatic advice selection.
    blocked = "conflicting" in decision.issues or "unverified_warning" in decision.issues
    if procedure and eligible and not blocked:
        selected = min(eligible, key=lambda e: e.evidence_id)
        contacts = []
        contact_errors = []
        expiry = min(selected.expires_at, procedure.expires_at)
        for contact in procedure.instructions.contacts:
            # Legacy reviewed catalogs remain readable. The optional 08 helper
            # withholds their contacts until metadata has been supplied.
            errors = contact_issues(contact, procedure.region, now) if contact.metadata else []
            if errors:
                contact_errors.extend(errors)
                continue
            contacts.append(contact)
            if contact.metadata:
                expiry = min(expiry, contact.metadata.expires_at)
        return (
            procedure.instructions.model_copy(update={"contacts": contacts}),
            EmergencyAssessment(
                status="grounded",
                procedure_id=procedure.procedure_id,
                evidence_ids=[selected.evidence_id],
                issues=sorted(set(contact_errors)),
                rejected_evidence=rejected,
            ),
            expiry,
        )
    issues = ["emergency_guidance_unavailable"]
    if ctx is None:
        issues.append("emergency_context_missing")
    if blocked:
        issues.append("emergency_conflict_requires_review")
    return (
        catalog.content.fallback[request.locale],
        EmergencyAssessment(
            status="fallback",
            issues=issues,
            rejected_evidence=rejected,
        ),
        None,
    )
