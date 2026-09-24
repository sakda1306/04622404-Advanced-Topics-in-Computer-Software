"""
Validation of emergency contacts before a recommendation is served.

01_env.txt: "Emergency text and contact numbers must match the user's
location and have a valid effective date."  07 generates the emergency
text and contact list (team decision); 08 only validates and displays it.

Rules applied to every EmergencyContact:
  * effective_date must not be in the future (not yet in force);
  * phone must look like a phone number;
  * region must match the traveler's region when it is known.
    If the region is unknown the contact is kept but the response says so
    (`strict_region=True` withholds it instead).

A contact that fails is WITHHELD, never "fixed". The response then carries
a limitation and a DEGRADED `emergency_contacts` entry so the UI/operators
can see something was removed. The input object is never mutated (the mock
fixtures are module-level singletons).

Not covered yet (needs the team): a per-contact directory version from 07,
so EMERGENCY_CONTACT_DIRECTORY_VERSION cannot be enforced today, and an
authoritative source for "which region is the traveler in".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.schema import (
    DegradedService,
    EmergencyContact,
    RecommendationResponse,
    ServiceStatus,
)

logger = structlog.get_logger("emergency")

_PHONE_RE = re.compile(r"^\+?[\d(][\d\s\-()]{1,19}$")

SERVICE_NAME = "emergency_contacts"

REGION_UNVERIFIED_NOTE = (
    "Emergency contact numbers could not be checked against your location; "
    "confirm they apply where you are."
)
NO_VERIFIED_CONTACTS_NOTE = (
    "No verified official emergency contact is available for your location. "
    "Follow the instructions above and contact local authorities."
)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def check_contact(
    contact: EmergencyContact,
    traveler_region: Optional[str],
    now: datetime,
    *,
    strict_region: bool = False,
) -> Optional[str]:
    """Return None when the contact may be shown, otherwise a reason code."""
    if _as_utc(contact.effective_date) > now:
        return "effective_date_in_future"
    if not _PHONE_RE.match(contact.phone.strip()):
        return "invalid_phone_format"
    if traveler_region is None or not traveler_region.strip():
        return "traveler_region_unknown" if strict_region else None
    if contact.region.strip().upper() != traveler_region.strip().upper():
        return "region_mismatch"
    return None


def validate_emergency_content(
    response: RecommendationResponse,
    traveler_region: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    strict_region: bool = False,
) -> RecommendationResponse:
    """Return a response whose official_contacts are all safe to display."""
    now = now or datetime.now(timezone.utc)

    kept: list[EmergencyContact] = []
    rejected: list[tuple[EmergencyContact, str]] = []
    for contact in response.official_contacts:
        reason = check_contact(contact, traveler_region, now, strict_region=strict_region)
        if reason is None:
            kept.append(contact)
        else:
            rejected.append((contact, reason))
            logger.warning(
                "emergency_contact_withheld",
                request_id=response.request_id,
                contact=contact.name,
                reason=reason,
            )

    limitations = list(response.limitations)
    degraded = list(response.degraded_services)

    if rejected:
        reasons = sorted({r for _, r in rejected})
        degraded.append(
            DegradedService(
                service_name=SERVICE_NAME,
                status=ServiceStatus.DEGRADED,
                detail=f"{len(rejected)} contact(s) withheld: {', '.join(reasons)}",
            )
        )

    region_unknown = traveler_region is None or not traveler_region.strip()
    if kept and region_unknown and REGION_UNVERIFIED_NOTE not in limitations:
        limitations.append(REGION_UNVERIFIED_NOTE)

    # Instructions without any usable contact must say so explicitly.
    if response.emergency_instructions and not kept and NO_VERIFIED_CONTACTS_NOTE not in limitations:
        limitations.append(NO_VERIFIED_CONTACTS_NOTE)

    if not rejected and limitations == response.limitations:
        return response

    return response.model_copy(
        update={
            "official_contacts": kept,
            "limitations": limitations,
            "degraded_services": degraded,
        }
    )
