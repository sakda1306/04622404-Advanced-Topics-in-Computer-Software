"""
Response schema — the contract this module exposes to 07_decision_llm_engine
(producer) and 01_web_app (consumer).

RECOMMENDATION_SCHEMA_VERSION must be bumped on any breaking field change.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings

RECOMMENDATION_SCHEMA_VERSION = settings.recommendation_schema_version


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ActionCode(str, Enum):
    """Same four values as 02's backend action names (07 sends them as
    `backend_action_code`). Emergency guidance is NOT a fifth action: it is
    carried by `emergency_instructions` / `official_contacts` on top of one of
    these four (see Contract Register v3)."""
    TRAVEL_NORMALLY = "TRAVEL_NORMALLY"
    CHANGE_ROUTE = "CHANGE_ROUTE"
    DELAY_TRAVEL = "DELAY_TRAVEL"
    AVOID_TRAVEL = "AVOID_TRAVEL"


class RiskLevel(str, Enum):
    """Three levels, identical to 02 / 06 / 07. There is intentionally no
    CRITICAL and no MODERATE."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceType(str, Enum):
    OFFICIAL = "OFFICIAL"
    WEATHER = "WEATHER"
    TRANSPORT = "TRANSPORT"
    DISASTER_RAG = "DISASTER_RAG"
    ROUTE_MODEL = "ROUTE_MODEL"


class ServiceStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ConfidenceLevel(str, Enum):
    """
    Module 07 currently emits confidence as a category (LOW/MEDIUM/HIGH),
    not a 0-1 probability — see 03_travel_ai_agent/README.md, "ข้อมูลที่ต้อง
    ตกลงกับทีม". Until the team settles on a numeric scale, this is the
    field that actually carries a value end-to-end; `confidence` (below)
    stays optional and is populated only once/if a numeric score exists.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FeedbackCategory(str, Enum):
    HELPFUL = "HELPFUL"
    INCORRECT = "INCORRECT"
    STALE = "STALE"
    UNSAFE = "UNSAFE"
    ROUTE_ISSUE = "ROUTE_ISSUE"
    SOURCE_ISSUE = "SOURCE_ISSUE"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class Waypoint(BaseModel):
    """A single point for map rendering on the Web App."""
    lat: float
    lng: float
    label: Optional[str] = None


class RouteOption(BaseModel):
    route_id: str
    description: str
    mode: str = Field(description="e.g. car, walk, transit, flight")
    estimated_duration_min: Optional[int] = None
    risk_level: RiskLevel
    trade_offs: List[str] = Field(default_factory=list)
    waypoints: List[Waypoint] = Field(default_factory=list)


class EmergencyContact(BaseModel):
    name: str
    phone: str
    contact_type: str = Field(description="e.g. police, embassy, hospital, hotline")
    region: str
    effective_date: datetime


class SourceCitation(BaseModel):
    name: str
    source_type: SourceType
    url: Optional[str] = None
    published_at: Optional[datetime] = None


class DegradedService(BaseModel):
    service_name: str
    status: ServiceStatus
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class RecommendationResponse(BaseModel):
    schema_version: str = RECOMMENDATION_SCHEMA_VERSION
    request_id: str

    action_code: ActionCode
    risk_level: RiskLevel

    # Module 07 sends confidence as LOW/MEDIUM/HIGH today, and upstream
    # (03) currently forwards `null` for the numeric field because of that
    # mismatch with 02's expected 0-1 float. Both are optional so a payload
    # missing either one is still valid; at least one SHOULD be present in
    # practice, but that's a display-layer concern, not a schema one — see
    # README "Open questions with upstream" for the team decision to track.
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_level: Optional[ConfidenceLevel] = None

    short_summary: str
    immediate_actions: List[str] = Field(default_factory=list)

    primary_route: Optional[RouteOption] = None
    alternative_routes: List[RouteOption] = Field(default_factory=list)

    emergency_instructions: List[str] = Field(default_factory=list)
    official_contacts: List[EmergencyContact] = Field(default_factory=list)

    reasons: List[str] = Field(default_factory=list)
    sources: List[SourceCitation] = Field(default_factory=list)

    observed_at: datetime
    fetched_at: datetime
    expires_at: datetime

    limitations: List[str] = Field(default_factory=list)
    degraded_services: List[DegradedService] = Field(default_factory=list)

    @field_validator("emergency_instructions", "official_contacts", mode="before")
    @classmethod
    def null_list_means_empty(cls, v):
        """Module 07 now produces verified emergency instructions and contacts
        (emergency.py, handoff.py) that strictly match 08's EmergencyContact schema
        (Contract Register v4). We continue to accept null as an empty list for
        backwards-compatibility with upstream 03 while it finishes forwarding."""
        return [] if v is None else v

    @field_validator("expires_at")
    @classmethod
    def expires_after_fetched(cls, v: datetime, info):
        fetched = info.data.get("fetched_at")
        if fetched and v <= fetched:
            raise ValueError("expires_at must be after fetched_at")
        return v


class FeedbackSubmission(BaseModel):
    """Explicit, user-submitted feedback — stored separately from telemetry."""

    request_id: str
    pseudonymous_user_id: str
    category: FeedbackCategory
    comment: Optional[str] = None
    submitted_at: datetime
