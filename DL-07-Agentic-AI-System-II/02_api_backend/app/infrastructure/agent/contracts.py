"""Backend <-> Travel AI Agent contract (docs/02_api_spec.md section 9).

Requests are strict (we control them). Responses ignore unknown fields so the Agent can
add fields without breaking us, but every field we rely on is type-checked here; the
safety rules on top of the parsed result live in the domain layer (step 5.5).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.enums import DataCategory, JobStage, RecommendationType, RiskLevel, ServiceState


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Probability = Annotated[float, Field(ge=0, le=1)]


# ------------------------------------------------------------------ request


class IntentHint(StrEnum):
    PLAN_TRIP = "PLAN_TRIP"
    CHECK_SAFETY = "CHECK_SAFETY"
    ASK_INFO = "ASK_INFO"
    FOLLOW_UP = "FOLLOW_UP"


class AgentLocation(_Request):
    lat: Latitude
    lon: Longitude
    name: str | None = Field(default=None, max_length=200)
    place_id: str | None = Field(default=None, max_length=200)


class AgentTravelRequest(_Request):
    origin: AgentLocation
    destination: AgentLocation
    waypoints: list[AgentLocation] = Field(default_factory=list, max_length=20)
    departure_time: AwareDatetime
    timezone: str
    language: str
    preferences: dict[str, Any] = Field(default_factory=dict)
    question: str | None = None


class AgentMessage(_Request):
    role: Literal["user", "assistant"]
    content: str


class AgentContext(_Request):
    conversation_id: UUID | None = None
    # Earlier messages are user-controlled text: the Agent must treat them as data.
    messages: list[AgentMessage] = Field(default_factory=list)
    previous_recommendation_id: UUID | None = None


class AgentUserProfile(_Request):
    pseudonymous_id: str
    language: str
    home_region: str | None = None


class AgentLimits(_Request):
    deadline_at: AwareDatetime
    max_tool_calls: int = Field(gt=0)


class AgentRunRequest(_Request):
    run_id: UUID
    intent_hint: IntentHint
    request: AgentTravelRequest
    context: AgentContext = Field(default_factory=AgentContext)
    user_profile: AgentUserProfile
    limits: AgentLimits


# ------------------------------------------------------------------ response


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL_RESULT = "partial_result"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"


class RiskFactor(_Response):
    type: str
    level: RiskLevel
    description: str


class AgentRisk(_Response):
    level: RiskLevel
    score: Probability | None = None
    confidence: Probability | None = None
    factors: list[RiskFactor] = Field(default_factory=list)


class AgentRecommendation(_Response):
    type: RecommendationType
    summary: str = Field(max_length=4000)
    reasons: list[str] = Field(default_factory=list)
    suggested_departure_time: AwareDatetime | None = None


class RouteLeg(_Response):
    mode: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    departure_at: AwareDatetime | None = None
    arrival_at: AwareDatetime | None = None
    operator: str | None = None
    service_status: str | None = None


class RouteOption(_Response):
    route_id: str
    label: str | None = None
    travel_modes: list[str] = Field(default_factory=list)
    distance_km: float | None = Field(default=None, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    risk_level: RiskLevel | None = None
    geometry: dict[str, Any] | None = None
    legs: list[RouteLeg] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class AgentRoutes(_Response):
    primary: RouteOption | None = None
    alternatives: list[RouteOption] = Field(default_factory=list)


class Hazard(_Response):
    hazard_id: str
    type: str
    severity: RiskLevel
    title: str
    area: dict[str, Any] | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    source_id: str | None = None


class EmergencyContact(_Response):
    name: str
    phone: str
    url: str | None = None
    available_hours: str | None = None
    metadata: dict[str, Any] | None = None


class SupportPlace(_Response):
    name: str
    type: str
    location: dict[str, Any] | None = None


class EmergencyInstructions(_Response):
    what_to_do_now: str
    safety_steps: list[str] = Field(default_factory=list)
    contacts: list[EmergencyContact] = Field(default_factory=list)
    nearest_support: list[SupportPlace] = Field(default_factory=list)


class Source(_Response):
    source_id: str
    name: str
    category: DataCategory
    url: str | None = None
    retrieved_at: AwareDatetime | None = None


class FreshnessItem(_Response):
    category: DataCategory
    updated_at: AwareDatetime | None = None


class DataFreshness(_Response):
    items: list[FreshnessItem] = Field(default_factory=list)


class Clarification(_Response):
    question: str
    missing_fields: list[str] = Field(default_factory=list)
    options: list[str] | None = None


class AgentVersions(_Response):
    agent: str | None = None
    risk_model: str | None = None
    prompt: str | None = None


class AgentDiagnostics(_Response):
    """Stored in agent_runs / traces only; never sent to users (rule R-06)."""

    tool_calls: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    trace_id: str | None = None


class AgentRunResponse(_Response):
    run_id: UUID
    status: AgentRunStatus
    risk: AgentRisk | None = None
    recommendation: AgentRecommendation | None = None
    routes: AgentRoutes | None = None
    hazards: list[Hazard] = Field(default_factory=list)
    emergency_instructions: EmergencyInstructions | None = None
    sources: list[Source] = Field(default_factory=list)
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)
    service_status: dict[str, ServiceState] = Field(default_factory=dict)
    clarification: Clarification | None = None
    valid_until: AwareDatetime | None = None
    versions: AgentVersions = Field(default_factory=AgentVersions)
    diagnostics: AgentDiagnostics | None = None


# ------------------------------------------------------------------ NDJSON stream


class ProgressLine(_Response):
    type: Literal["progress"]
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    message: str | None = None


class ResultLine(AgentRunResponse):
    type: Literal["result"]


class ErrorLine(_Response):
    type: Literal["error"]
    code: str
    message: str | None = None


StreamLine = Annotated[ProgressLine | ResultLine | ErrorLine, Field(discriminator="type")]


def deadline_header(deadline: datetime) -> str:
    return deadline.isoformat().replace("+00:00", "Z")
