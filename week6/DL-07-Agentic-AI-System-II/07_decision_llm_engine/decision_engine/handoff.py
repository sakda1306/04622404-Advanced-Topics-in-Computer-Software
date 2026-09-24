"""Optional emergency-only handoff fragment for 08, not a Recommendation response."""

import re
from datetime import datetime

from .models import DecisionResponse, EmergencyContact


def contact_issues(contact: EmergencyContact, region: str, now: datetime) -> list[str]:
    metadata = contact.metadata
    if metadata is None:
        return ["contact_metadata_missing"]
    issues = []
    if metadata.region.strip().casefold() != region.strip().casefold():
        issues.append("contact_region_mismatch")
    if not metadata.effective_date <= now < metadata.expires_at:
        issues.append("contact_not_current")
    if re.fullmatch(r"\+?[\d(][\d\s\-()]{1,19}", contact.phone) is None:
        issues.append("contact_phone_invalid")
    return issues


def emergency_fragment(response: DecisionResponse, *, traveler_region: str, now: datetime) -> dict:
    """Caller must retain the original decision, citations, versions and limitations.

    This helper performs no source retrieval or authenticity verification. Only a
    grounded response can supply contacts. Legacy contacts need reviewed metadata
    before they can be exported to 08; no date or region is filled in here.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Handoff time must include a timezone")
    if now < response.evaluated_at or (
        response.valid_until is not None and now >= response.valid_until
    ):
        raise ValueError("Decision is not current; request a new decision")
    instructions = response.emergency_instructions
    result = {
        "emergency_instructions": [],
        "official_contacts": [],
        "contact_provenance": [],
        "limitations": list(response.emergency_assessment.issues),
    }
    if instructions is None:
        return result
    result["emergency_instructions"] = list(
        dict.fromkeys([instructions.what_to_do_now, *instructions.safety_steps])
    )
    for index, public_contact in enumerate(instructions.contacts):
        contact = public_contact.model_copy(
            update={"metadata": response.emergency_contact_metadata.get(str(index))}
        )
        issues = contact_issues(contact, traveler_region, now)
        if response.emergency_assessment.status != "grounded":
            issues.append("contact_guidance_not_grounded")
        if issues:
            result["limitations"].extend(issues)
            continue
        metadata = contact.metadata
        result["official_contacts"].append(
            {
                "name": contact.name,
                "phone": contact.phone,
                "contact_type": metadata.contact_type,
                "region": metadata.region,
                "effective_date": metadata.effective_date.isoformat(),
            }
        )
        result["contact_provenance"].append(
            {
                "contact_index": len(result["official_contacts"]) - 1,
                "directory_version": metadata.directory_version,
                "source_url": str(metadata.source_url),
                "expires_at": metadata.expires_at.isoformat(),
            }
        )
    result["limitations"] = sorted(set(result["limitations"]))
    return result
