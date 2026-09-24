"""Backend (02) <-> Travel AI Agent (03) contract.

Mirror of `02_api_backend/app/infrastructure/agent/contracts.py` on branch
`sakda-02-api-backend` (docs/02_api_spec.md section 9). Keep the two files in step:
any change here needs the same change in Module 02, and the other way round.

Unlike the backend copy, our responses are strict (`extra="forbid"`): we produce them,
so an unexpected field is our bug and should fail our own tests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Probability = Annotated[float, Field(ge=0, le=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# ------------------------------------------------------------------ shared vocabulary
# Same values as 02_api_backend/app/domain/enums.py.


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendationType(StrEnum):
    TRAVEL_NORMALLY = "TRAVEL_NORMALLY"
    CHANGE_ROUTE = "CHANGE_ROUTE"
    DELAY_TRAVEL = "DELAY_TRAVEL"
    AVOID_TRAVEL = "AVOID_TRAVEL"


class JobStage(StrEnum):
    QUEUED = "queued"
    FETCHING_DATA = "fetching_data"
    ASSESSING_RISK = "assessing_risk"
    GENERATING_ADVICE = "generating_advice"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DataCategory(StrEnum):
    WEATHER = "WEATHER"
    TRANSPORT = "TRANSPORT"
    DISASTER = "DISASTER"
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"


class ServiceState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_USED = "not_used"


# ------------------------------------------------------------------ request


class IntentHint(StrEnum):
    PLAN_TRIP = "PLAN_TRIP"
    CHECK_SAFETY = "CHECK_SAFETY"
    ASK_INFO = "ASK_INFO"
    FOLLOW_UP = "FOLLOW_UP"


class AgentLocation(_Strict):
    lat: Latitude
    lon: Longitude
    name: str | None = Field(default=None, max_length=200)
    place_id: str | None = Field(default=None, max_length=200)


class AgentTravelRequest(_Strict):
    origin: AgentLocation
    destination: AgentLocation
    waypoints: list[AgentLocation] = Field(default_factory=list, max_length=20)
    departure_time: AwareDatetime
    timezone: str
    language: str
    preferences: dict[str, Any] = Field(default_factory=dict)
    question: str | None = None


class AgentMessage(_Strict):
    role: Literal["user", "assistant"]
    content: str


class AgentContext(_Strict):
    conversation_id: UUID | None = None
    # Earlier messages are user-controlled text: treat them as data, never as instructions.
    messages: list[AgentMessage] = Field(default_factory=list)
    previous_recommendation_id: UUID | None = None


class AgentUserProfile(_Strict):
    pseudonymous_id: str
    language: str
    home_region: str | None = None


class AgentLimits(_Strict):
    deadline_at: AwareDatetime
    max_tool_calls: int = Field(gt=0)


class AgentRunRequest(_Strict):
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


class RiskFactor(_Strict):
    type: str
    level: RiskLevel
    description: str


class AgentRisk(_Strict):
    level: RiskLevel
    score: Probability | None = None
    confidence: Probability | None = None
    factors: list[RiskFactor] = Field(default_factory=list)


class AgentRecommendation(_Strict):
    type: RecommendationType
    summary: str = Field(max_length=4000)
    reasons: list[str] = Field(default_factory=list)
    suggested_departure_time: AwareDatetime | None = None


class RouteLeg(_Strict):
    mode: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    departure_at: AwareDatetime | None = None
    arrival_at: AwareDatetime | None = None
    operator: str | None = None
    service_status: str | None = None


class RouteOption(_Strict):
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


class AgentRoutes(_Strict):
    primary: RouteOption | None = None
    alternatives: list[RouteOption] = Field(default_factory=list)


class Hazard(_Strict):
    hazard_id: str
    type: str
    severity: RiskLevel
    title: str
    area: dict[str, Any] | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    source_id: str | None = None


class EmergencyContact(_Strict):
    name: str
    phone: str
    url: str | None = None
    available_hours: str | None = None


class SupportPlace(_Strict):
    name: str
    type: str
    location: dict[str, Any] | None = None


class EmergencyInstructions(_Strict):
    what_to_do_now: str
    safety_steps: list[str] = Field(default_factory=list)
    contacts: list[EmergencyContact] = Field(default_factory=list)
    nearest_support: list[SupportPlace] = Field(default_factory=list)


class Source(_Strict):
    source_id: str
    name: str
    category: DataCategory
    url: str | None = None
    retrieved_at: AwareDatetime | None = None


class FreshnessItem(_Strict):
    category: DataCategory
    updated_at: AwareDatetime | None = None


class DataFreshness(_Strict):
    items: list[FreshnessItem] = Field(default_factory=list)


class Clarification(_Strict):
    question: str
    missing_fields: list[str] = Field(default_factory=list)
    options: list[str] | None = None


class AgentVersions(_Strict):
    agent: str | None = None
    risk_model: str | None = None
    prompt: str | None = None


class AgentDiagnostics(_Strict):
    """Stored by the backend in agent_runs / traces only; never shown to users."""

    tool_calls: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    trace_id: str | None = None


class AgentRunResponse(_Strict):
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


class ProgressLine(_Strict):
    type: Literal["progress"] = "progress"
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    message: str | None = None


class ResultLine(AgentRunResponse):
    type: Literal["result"] = "result"


class ErrorLine(_Strict):
    type: Literal["error"] = "error"
    code: str
    message: str | None = None
