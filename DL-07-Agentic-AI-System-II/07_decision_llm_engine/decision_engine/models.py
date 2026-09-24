from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")]
EvidenceIds = Annotated[list[Identifier], Field(min_length=1, max_length=32)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Level(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def reject_non_numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Confidence must be a JSON number")
    return value


Score = Annotated[
    float, Field(ge=0, le=1, allow_inf_nan=False), BeforeValidator(reject_non_numeric)
]
# Legacy input is accepted at the boundary; output is always numeric.
InputConfidence = Score | Level


class Action(StrEnum):
    NORMAL = "NORMAL"
    CHANGE_ROUTE = "CHANGE_ROUTE"
    DELAY = "DELAY"
    AVOID = "AVOID"


BACKEND_ACTIONS = {
    Action.NORMAL: "TRAVEL_NORMALLY",
    Action.CHANGE_ROUTE: "CHANGE_ROUTE",
    Action.DELAY: "DELAY_TRAVEL",
    Action.AVOID: "AVOID_TRAVEL",
}


class Context(Contract):
    request_id: UUID
    route_id: Identifier
    departure_time: AwareDatetime


class Scoped(Contract):
    context: Context


class Evidence(Scoped):
    evidence_id: Identifier
    source_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    kind: Literal["weather", "transport", "risk", "knowledge", "route", "official", "time"]
    official_source: bool = False
    observed_at: AwareDatetime
    fetched_at: AwareDatetime
    expires_at: AwareDatetime
    # Untrusted reference text: never interpolated into instructions or the fallback.
    excerpt: str = Field(default="", max_length=4000)
    # Hash of the passage content, computed by the module that holds the source
    # (decision_engine/hashing.py). Absent for evidence whose owner has not adopted it.
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("url")
    @classmethod
    def https_without_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password:
            raise ValueError("Evidence URL must be HTTPS without credentials")
        return value

    @model_validator(mode="after")
    def timestamp_order(self):
        if not self.observed_at <= self.fetched_at < self.expires_at:
            raise ValueError("Require observed_at <= fetched_at < expires_at")
        return self


class RiskAssessment(Scoped):
    level: Level
    # Accept upstream ordinal values or numeric policy confidence, not probability.
    confidence: InputConfidence
    model_version: Identifier
    evidence_ids: EvidenceIds


class Summary(Scoped):
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: EvidenceIds


class RouteOption(Contract):
    route_id: Identifier
    risk_level: Level
    usable: bool
    clearly_safer: bool
    evidence_ids: EvidenceIds


class RouteAssessment(Scoped):
    no_safe_route: bool = False
    alternatives: list[RouteOption] = Field(default_factory=list, max_length=10)
    evidence_ids: EvidenceIds


class OfficialAlert(Scoped):
    level: Literal["CAUTION", "AVOID", "CLOSURE"]
    active: bool
    evidence_ids: EvidenceIds


class TimeAssessment(Scoped):
    safer_later: bool
    suggested_departure_time: AwareDatetime | None = None
    evidence_ids: EvidenceIds

    @model_validator(mode="after")
    def supported_later_time(self):
        if self.safer_later and (
            self.suggested_departure_time is None
            or self.suggested_departure_time <= self.context.departure_time
        ):
            raise ValueError("A safer-later assessment needs a later departure time")
        return self


class DataQuality(Scoped):
    confidence: InputConfidence
    flags: list[
        Literal[
            "missing",
            "stale",
            "conflicting",
            "incomplete",
            "inferred",
            "partial",
            "freshness_unknown",
        ]
    ] = Field(default_factory=list, max_length=7)
    # None means unknown, never equivalent to 'no restriction'.
    active_restriction: bool | None
    data_version: Identifier
    schema_version: Literal["07-draft-v1", "07-draft-v2", "07-draft-v3"] = "07-draft-v1"


class EmergencyContext(Scoped):
    region: Identifier
    hazard: Identifier


class EmergencyContactMetadata(Contract):
    """Proposed handoff metadata; supplied by a reviewed source, never inferred."""

    contact_type: Identifier
    region: Identifier
    effective_date: AwareDatetime
    expires_at: AwareDatetime
    directory_version: Identifier
    source_url: HttpUrl

    @field_validator("source_url")
    @classmethod
    def verified_url_shape(cls, value: HttpUrl) -> HttpUrl:
        return Evidence.https_without_credentials(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.effective_date >= self.expires_at:
            raise ValueError("Contact expiry must follow its effective date")
        return self


class EmergencyContact(Contract):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=80)
    url: HttpUrl | None = None
    available_hours: str | None = Field(default=None, max_length=200)
    # Local reviewed catalog input only. Public metadata is carried separately
    # because 02 rejects additional keys inside EmergencyInstructions.contacts.
    metadata: EmergencyContactMetadata | None = Field(default=None, exclude=True)


class EmergencyInstructions(Contract):
    what_to_do_now: str = Field(min_length=1, max_length=2000)
    safety_steps: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=16
    )
    contacts: list[EmergencyContact] = Field(default_factory=list, max_length=10)
    # No location/ranking source yet: never invent a nearest support place.
    nearest_support: list[dict] = Field(default_factory=list, max_length=0)


class EmergencyAssessment(Contract):
    status: Literal["not_required", "grounded", "fallback"]
    procedure_id: Identifier | None = None
    evidence_ids: list[Identifier] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    # ID -> rejection reasons; never include raw source text.
    rejected_evidence: dict[str, list[str]] = Field(default_factory=dict)


class DecisionRequest(Contract):
    context: Context
    locale: Literal["th-TH", "en-US"] = "th-TH"
    emergency_context: EmergencyContext | None = None
    risk: RiskAssessment | None = None
    weather: Summary | None = None
    transport: Summary | None = None
    routes: RouteAssessment | None = None
    alerts: list[OfficialAlert] = Field(default_factory=list, max_length=20)
    time_assessment: TimeAssessment | None = None
    quality: DataQuality
    evidence: list[Evidence] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def linked_evidence_and_context(self):
        scoped = [
            self.emergency_context,
            self.risk,
            self.weather,
            self.transport,
            self.routes,
            self.time_assessment,
            self.quality,
            *self.alerts,
            *self.evidence,
        ]
        for item in scoped:
            if item is not None and item.context != self.context:
                raise ValueError("All inputs must match request_id, route_id and departure_time")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate evidence IDs")
        refs = []
        for item in scoped:
            refs.extend(getattr(item, "evidence_ids", []))
        if self.routes:
            routes = [item.route_id for item in self.routes.alternatives]
            if len(routes) != len(set(routes)) or self.context.route_id in routes:
                raise ValueError("Alternative route IDs must be unique and differ from primary")
            for item in self.routes.alternatives:
                refs.extend(item.evidence_ids)
        if set(refs) - set(ids):
            raise ValueError("Referenced evidence IDs must exist in the evidence package")
        return self


class Citation(Contract):
    evidence_id: Identifier
    source_name: str
    url: HttpUrl
    observed_at: datetime
    fetched_at: datetime
    expires_at: datetime


class Explanation(Contract):
    summary: str
    reasons: list[str]
    instructions: list[str]
    uncertainty: list[str]
    mode: Literal["template", "provider"]


class EvidenceStatus(Contract):
    evidence_id: Identifier
    used_by_decision: bool
    used_by_emergency: bool = False
    cited: bool
    validation_issues: list[str]


class Versions(Contract):
    policy: str
    policy_sha256: str
    policy_status: Literal["prototype"] = "prototype"
    prompt: str
    model: str
    risk_model: str | None
    data: str
    schema_version: str = "07-draft-v3"
    emergency_catalog: str
    emergency_catalog_sha256: str


class DecisionResponse(Contract):
    request_id: UUID
    action_code: Action
    backend_action_code: str
    risk_level: Level | None
    confidence: Score
    confidence_kind: Literal["heuristic_policy_score"] = "heuristic_policy_score"
    confidence_details: dict[str, float]
    emergency_instructions: EmergencyInstructions | None = None
    emergency_contact_metadata: dict[str, EmergencyContactMetadata] = Field(default_factory=dict)
    emergency_assessment: EmergencyAssessment
    escalation_required: bool
    escalation_reasons: list[str]
    selected_route_id: str | None
    suggested_departure_time: datetime | None
    explanation: Explanation
    citations: list[Citation]
    evidence_status: list[EvidenceStatus]
    rules_fired: list[str]
    degraded_services: list[str]
    validation_results: list[str]
    versions: Versions
    evaluated_at: datetime
    valid_until: datetime | None
    prototype_only: Literal[True] = True
