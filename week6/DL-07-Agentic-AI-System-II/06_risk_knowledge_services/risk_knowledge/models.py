"""Contracts owned by Module 06.

Input models deliberately accept additive fields while the cross-module contract is
provisional. Output models are strict and mirror the draft tool responses in Module
03; Module 06 does not import or modify another module's implementation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
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


Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")]
RecordKind = Literal["weather", "transport", "risk", "knowledge", "route", "official", "time"]


class Level(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InputModel(BaseModel):
    # Module 05 labels its schema provisional. Additive fields must not break Module 06.
    model_config = ConfigDict(extra="allow", frozen=True)


class Source(InputModel):
    name: str = Field(min_length=1, max_length=200)
    authority: str | None = None
    url: HttpUrl | None = None


class IntegratedEvidence(InputModel):
    schema_version: str | None = None
    record_id: str
    record_kind: str
    status: Literal["available", "unavailable"] = "available"
    source: Source
    source_lineage: str | None = None
    spatial_footprint: dict[str, Any] | None = None
    valid_at: AwareDatetime | None = None
    observed_at: AwareDatetime | None = None
    issued_at: AwareDatetime | None = None
    event_time: AwareDatetime | None = None
    fetched_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    freshness: str | None = None
    severity: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    value: Any = None
    error_code: str | None = None


class RouteSegment(InputModel):
    start_index: int
    end_index: int
    enter_at: AwareDatetime
    exit_at: AwareDatetime
    matched_record_ids: dict[str, list[str]] = Field(default_factory=dict)
    coverage: dict[str, str] = Field(default_factory=dict)


class IntegratedRoute(InputModel):
    route_id: Identifier
    geometry: dict[str, Any] | None = None
    segments: list[RouteSegment] = Field(default_factory=list)
    label: str | None = None
    travel_modes: list[str] = Field(default_factory=list)


class IntegratedTravelContext(InputModel):
    """Accept both Module 05's detailed draft and Module 03's summary mock."""

    feature_schema_version: str | None = None
    data_version: str | None = None
    run_id: str | None = None
    created_at: AwareDatetime | None = None
    primary_route_id: Identifier | None = None
    confidence: Level | None = None
    flags: list[str] = Field(default_factory=list)
    active_restriction: bool | None = None
    routes: list[IntegratedRoute] = Field(default_factory=list)
    evidence: list[IntegratedEvidence] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    degraded: bool = False
    risk_score: float | None = None

    @model_validator(mode="after")
    def route_identity_exists(self):
        if not self.primary_route_id and not self.routes:
            raise ValueError("context requires primary_route_id or at least one detailed route")
        return self

    @property
    def resolved_primary_route_id(self) -> str:
        return self.primary_route_id or self.routes[0].route_id


class TravelQuery(InputModel):
    run_id: str
    origin: tuple[float, float]
    destination: tuple[float, float]
    departure_time: AwareDatetime
    travel_modes: list[str] = Field(default_factory=list)
    language: str = "th-TH"
    geography: str | None = None


class AlertInput(InputModel):
    hazard_id: str
    hazard_type: str
    severity: Level
    title: str = ""
    level: Literal["CAUTION", "AVOID", "CLOSURE"]
    active: bool
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class Record(StrictModel):
    id: Identifier | None = None
    kind: RecordKind
    source_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    official_source: bool = False
    observed_at: AwareDatetime
    fetched_at: AwareDatetime
    expires_at: AwareDatetime
    excerpt: str = Field(default="", max_length=4000)
    # Hash of the passage content (risk_knowledge/hashing.py). Module 07 matches a
    # reviewed emergency procedure on this instead of on the excerpt's layout.
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def provenance_is_usable(self):
        if self.url.scheme != "https" or self.url.username or self.url.password:
            raise ValueError("Record URL must be HTTPS without credentials")
        if not self.observed_at <= self.fetched_at < self.expires_at:
            raise ValueError("Require observed_at <= fetched_at < expires_at")
        return self


class RiskFactorResult(StrictModel):
    type: str
    level: Level
    description: str = Field(max_length=500)


class RiskResult(StrictModel):
    level: Level
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    model_version: Identifier
    factors: list[RiskFactorResult] = Field(default_factory=list)
    records: list[Record] = Field(min_length=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if isinstance(value, Level):
            return {"LOW": 0.25, "MEDIUM": 0.65, "HIGH": 0.90}[value.value]
        if isinstance(value, str) and value.upper() in {"LOW", "MEDIUM", "HIGH"}:
            return {"LOW": 0.25, "MEDIUM": 0.65, "HIGH": 0.90}[value.upper()]
        return value


class KnowledgeResult(StrictModel):
    records: list[Record] = Field(default_factory=list)


class RouteInfo(StrictModel):
    route_id: Identifier
    label: str | None = None
    travel_modes: list[str] = Field(default_factory=list)
    distance_km: float | None = Field(default=None, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    risk_level: Level
    usable: bool = True
    clearly_safer: bool = False


class RouteResult(StrictModel):
    primary: RouteInfo
    alternatives: list[RouteInfo] = Field(default_factory=list, max_length=10)
    no_safe_route: bool = False
    safer_later: bool = False
    suggested_departure_time: AwareDatetime | None = None
    records: list[Record] = Field(min_length=1)


class KnowledgePassage(StrictModel):
    document_id: Identifier
    authority: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    language: str
    geography: list[str] = Field(default_factory=lambda: ["*"])
    hazard_types: list[str] = Field(default_factory=list)
    effective_at: AwareDatetime
    expires_at: AwareDatetime
    page: int | None = Field(default=None, ge=1)
    section: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=3500)
    approved: bool = False

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if self.expires_at <= self.effective_at:
            raise ValueError("knowledge expires_at must follow effective_at")
        return self


def as_mapping(value: Any) -> dict[str, Any]:
    """Convert Pydantic objects or mappings from adjacent modules without importing them."""

    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    raise TypeError(f"expected a mapping or Pydantic model, got {type(value).__name__}")


def parse_time(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
