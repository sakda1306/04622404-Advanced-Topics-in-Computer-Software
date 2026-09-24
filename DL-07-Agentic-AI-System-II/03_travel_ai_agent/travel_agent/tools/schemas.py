"""What the agent expects back from Modules 04, 05 and 06.

These are DRAFT contracts proposed by Module 03 so the pipeline can run on mocks. They
must be agreed with the owners of 04/05/06 before the real adapters replace the mocks.
Tool output is untrusted: it is validated here, and free text (`excerpt`, `summary`)
is only ever passed along as data, never used as instructions.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from travel_agent.contracts import RiskLevel

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")]
RecordKind = Literal["weather", "transport", "risk", "knowledge", "route", "official", "time"]


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PassThroughModel(BaseModel):
    """For payloads the agent forwards to another module: additive fields survive."""

    model_config = ConfigDict(extra="allow", frozen=True)


# Quality flags Module 07 accepts (decision_engine/models.py, DataQuality).
QUALITY_FLAGS = frozenset(
    {"missing", "stale", "conflicting", "incomplete", "inferred", "partial", "freshness_unknown"}
)


class Record(ToolModel):
    """One piece of evidence with provenance, as Module 04 step 9 requires."""

    # Assigned by the agent when the tool returns, so IDs are unique within a run.
    id: Identifier | None = None
    kind: RecordKind
    source_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    official_source: bool = False
    observed_at: AwareDatetime
    fetched_at: AwareDatetime
    expires_at: AwareDatetime
    excerpt: str = Field(default="", max_length=4000)
    # Set by the module that owns the source (06 for knowledge passages). The agent
    # forwards it to 07 and never computes or edits it.
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def provenance_is_usable(self):
        # Module 07 rejects the whole package if one record breaks these rules,
        # so a bad record fails its own tool instead.
        if self.url.scheme != "https" or self.url.username or self.url.password:
            raise ValueError("Record URL must be HTTPS without credentials")
        if not self.observed_at <= self.fetched_at < self.expires_at:
            raise ValueError("Require observed_at <= fetched_at < expires_at")
        return self


class TravelQuery(ToolModel):
    """The only input tools receive: no user identity and no free-text question."""

    run_id: str
    origin: tuple[float, float]
    destination: tuple[float, float]
    departure_time: AwareDatetime
    travel_modes: list[str] = Field(default_factory=list)
    # Selects a canned scenario in the mock tools; ignored by real services.
    mock_scenario: str | None = None


# ------------------------------------------------------------------ Module 04


class WeatherResult(ToolModel):
    summary: str = Field(min_length=1, max_length=2000)
    records: list[Record] = Field(min_length=1)
    canonical_records: list[dict[str, Any]] = Field(default_factory=list, exclude=True)


class TransportResult(ToolModel):
    summary: str = Field(min_length=1, max_length=2000)
    records: list[Record] = Field(min_length=1)
    # Module 04's canonical payload is kept for Module 05. It is internal plumbing,
    # not evidence sent directly to Module 07 (the validated `records` are).
    canonical_records: list[dict[str, Any]] = Field(default_factory=list, exclude=True)


class Alert(ToolModel):
    hazard_id: Identifier
    hazard_type: str
    severity: RiskLevel
    title: str = Field(max_length=300)
    # Same scale as Module 07's OfficialAlert.level.
    level: Literal["CAUTION", "AVOID", "CLOSURE"]
    active: bool
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    record: Record


class DisasterResult(ToolModel):
    alerts: list[Alert] = Field(default_factory=list, max_length=20)
    # Proof that the check ran even when there are no alerts.
    records: list[Record] = Field(min_length=1)
    canonical_records: list[dict[str, Any]] = Field(default_factory=list, exclude=True)


class RouteLeg(ToolModel):
    """One stretch of a candidate route, as the routing provider splits it."""

    # Indices into the route's GeoJSON LineString coordinates.
    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)
    duration_minutes: float = Field(gt=0)
    mode: str | None = None

    @model_validator(mode="after")
    def indices_move_forward(self):
        if self.end_index <= self.start_index:
            raise ValueError("leg end_index must follow start_index")
        return self


class RouteCandidate(ToolModel):
    """A possible route from Module 04's routing provider (04/02_step.txt).

    04 supplies geometry and how long each leg takes; it does not need the traveller's
    departure time. Module 03 turns the durations into the enter/exit times 05 needs.
    """

    route_id: Identifier
    label: str | None = None
    travel_modes: list[str] = Field(default_factory=list)
    # GeoJSON LineString: {"type": "LineString", "coordinates": [[lon, lat], ...]}
    geometry: dict
    legs: list[RouteLeg] = Field(min_length=1)
    distance_km: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def legs_cover_the_line(self):
        if self.geometry.get("type") != "LineString":
            raise ValueError("route geometry must be a GeoJSON LineString")
        coordinates = self.geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("route geometry needs at least two coordinates")
        expected = 0
        for leg in self.legs:
            if leg.start_index != expected:
                raise ValueError("legs must cover consecutive coordinates")
            expected = leg.end_index
        if expected != len(coordinates) - 1:
            raise ValueError("legs must cover the whole route")
        return self


class RouteCandidatesResult(ToolModel):
    candidates: list[RouteCandidate] = Field(min_length=1, max_length=10)
    records: list[Record] = Field(min_length=1)


# ------------------------------------------------------------------ Module 05


class IntegratedContext(PassThroughModel):
    """Module 05's context, carried to Module 06 without being summarised.

    05 owns `integrated-travel-v0.1-proposed` and 06 already accepts it, so the agent
    keeps every field (matched_record_ids, coverage, evidence) instead of cutting the
    context down. The summary fields also accept 03's older mock shape during the
    changeover; unknown additive fields survive the trip.
    """

    feature_schema_version: str | None = None
    data_version: Identifier | None = None
    run_id: str | None = None
    created_at: AwareDatetime | None = None
    primary_route_id: Identifier | None = None
    confidence: RiskLevel | None = None
    routes: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    # 05 reports coverage words (partial, freshness_unknown, ...); 07 v3 accepts the
    # ones in QUALITY_FLAGS and the agent drops the rest rather than reinterpreting them.
    flags: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    degraded: bool = False
    # None means unknown, never "no restriction".
    active_restriction: bool | None = None
    risk_score: float | None = None

    @model_validator(mode="after")
    def route_identity_exists(self):
        if not self.primary_route_id and not self.routes:
            raise ValueError("context needs primary_route_id or at least one route")
        return self

    @property
    def resolved_primary_route_id(self) -> str:
        if self.primary_route_id:
            return self.primary_route_id
        first = self.routes[0].get("route_id")
        if not isinstance(first, str) or not first:
            raise ValueError("route in integrated context has no route_id")
        return first

    @property
    def all_flags(self) -> set[str]:
        return set(self.flags) | set(self.quality_flags)


# ------------------------------------------------------------------ Module 06


class RiskFactorResult(ToolModel):
    type: str
    level: RiskLevel
    description: str = Field(max_length=500)


class RiskResult(ToolModel):
    level: RiskLevel
    # Model output probability, if the model is calibrated; shown to the backend as score.
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    model_version: Identifier
    factors: list[RiskFactorResult] = Field(default_factory=list)
    records: list[Record] = Field(min_length=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if isinstance(value, RiskLevel):
            return {"LOW": 0.25, "MEDIUM": 0.65, "HIGH": 0.90}[value.value]
        if isinstance(value, str) and value.upper() in {"LOW", "MEDIUM", "HIGH"}:
            return {"LOW": 0.25, "MEDIUM": 0.65, "HIGH": 0.90}[value.upper()]
        return value


class KnowledgeResult(ToolModel):
    records: list[Record] = Field(default_factory=list)


class RouteInfo(ToolModel):
    route_id: Identifier
    label: str | None = None
    travel_modes: list[str] = Field(default_factory=list)
    distance_km: float | None = Field(default=None, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    risk_level: RiskLevel
    usable: bool = True
    clearly_safer: bool = False


class RouteResult(ToolModel):
    primary: RouteInfo
    alternatives: list[RouteInfo] = Field(default_factory=list, max_length=10)
    no_safe_route: bool = False
    safer_later: bool = False
    suggested_departure_time: AwareDatetime | None = None
    records: list[Record] = Field(min_length=1)
