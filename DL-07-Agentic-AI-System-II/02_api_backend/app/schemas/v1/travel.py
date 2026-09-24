"""API contract for travel recommendations (docs/02_api_spec.md sections 5.1 and 5.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ERROR_SPECS, ErrorCode
from app.domain.enums import (
    AvoidOption,
    DataCategory,
    MobilityNeed,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    ServiceState,
    TravelMode,
)
from app.domain.follow_up import PreferenceOverrides, RequestOverrides
from app.domain.normalization import GeoPoint, TravelPreferences, TravelRequestInput
from app.services.ports import RecommendationRecord, RecommendationSummaryRecord


class _Strict(BaseModel):
    # Unknown fields are rejected in requests and would expose drift in responses.
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ request


class Location(_Strict):
    lat: float
    lon: float
    name: str | None = Field(default=None, max_length=1000)
    place_id: str | None = Field(default=None, max_length=1000)

    def to_domain(self) -> GeoPoint:
        return GeoPoint(lat=self.lat, lon=self.lon, name=self.name, place_id=self.place_id)


class Preferences(_Strict):
    travel_modes: list[TravelMode] = Field(default_factory=list, max_length=len(TravelMode))
    avoid: list[AvoidOption] = Field(default_factory=list, max_length=len(AvoidOption))
    max_travel_hours: int | None = None
    mobility_needs: list[MobilityNeed] = Field(default_factory=list, max_length=len(MobilityNeed))
    traveler_count: int = 1


class TravelRequest(_Strict):
    origin: Location
    destination: Location
    # Hard cap for parsing; the business limit (P-42) is checked during normalization.
    waypoints: list[Location] = Field(default_factory=list, max_length=50)
    departure_time: datetime
    timezone: str = Field(max_length=64)
    language: str | None = Field(default=None, max_length=35)
    preferences: Preferences = Field(default_factory=Preferences)
    question: str | None = Field(default=None, max_length=20_000)
    conversation_id: UUID | None = None
    trip_id: UUID | None = None

    def to_domain(self, accept_language: str | None) -> TravelRequestInput:
        prefs = self.preferences
        return TravelRequestInput(
            origin=self.origin.to_domain(),
            destination=self.destination.to_domain(),
            waypoints=tuple(p.to_domain() for p in self.waypoints),
            departure_time=self.departure_time,
            timezone=self.timezone,
            language=self.language,
            accept_language=accept_language[:200] if accept_language else None,
            preferences=TravelPreferences(
                travel_modes=tuple(prefs.travel_modes),
                avoid=tuple(prefs.avoid),
                max_travel_hours=prefs.max_travel_hours,
                mobility_needs=tuple(prefs.mobility_needs),
                traveler_count=prefs.traveler_count,
            ),
            question=self.question,
        )


# ------------------------------------------------------------------ response


class RiskFactor(_Strict):
    type: str
    level: RiskLevel
    description: str


class Risk(_Strict):
    level: RiskLevel
    score: float | None
    confidence: float | None
    factors: list[RiskFactor]


class RecommendationBody(_Strict):
    type: RecommendationType | None
    summary: str | None
    reasons: list[str]
    suggested_departure_time: datetime | None


class RouteLeg(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    mode: str
    from_: str | None = Field(alias="from")
    to: str | None
    departure_at: datetime | None
    arrival_at: datetime | None
    operator: str | None
    service_status: str | None


class RouteOption(_Strict):
    route_id: str
    label: str | None
    travel_modes: list[str]
    distance_km: float | None
    duration_minutes: float | None
    risk_level: RiskLevel | None
    geometry: dict[str, Any] | None
    legs: list[RouteLeg]
    restrictions: list[str]
    tips: list[str]


class Routes(_Strict):
    primary: RouteOption | None
    alternatives: list[RouteOption]


class Hazard(_Strict):
    hazard_id: str
    type: str
    severity: RiskLevel
    title: str
    area: dict[str, Any] | None
    starts_at: datetime | None
    ends_at: datetime | None
    source_id: str | None


class EmergencyContact(_Strict):
    name: str
    phone: str
    url: str | None = None
    available_hours: str | None = None
    metadata: dict[str, Any] | None = None


class SupportPlace(_Strict):
    name: str
    type: str
    location: dict[str, Any] | None = None


class EmergencyInstructions(_Strict):
    what_to_do_now: str
    safety_steps: list[str] = Field(default_factory=list)
    contacts: list[EmergencyContact] = Field(default_factory=list)
    nearest_support: list[SupportPlace] = Field(default_factory=list)


class SourceItem(_Strict):
    source_id: str
    name: str
    category: DataCategory
    url: str | None
    retrieved_at: datetime | None


class FreshnessItem(_Strict):
    category: DataCategory
    updated_at: datetime | None
    age_seconds: int | None
    is_stale: bool


class DataFreshness(_Strict):
    overall_is_stale: bool
    items: list[FreshnessItem]


class Clarification(_Strict):
    question: str
    missing_fields: list[str]
    options: list[str] | None


class WarningItem(_Strict):
    code: str
    message: str


class Versions(_Strict):
    api: str
    agent: str | None
    risk_model: str | None
    prompt: str | None


class ErrorInfo(_Strict):
    code: str
    message: str


class RecommendationResponse(_Strict):
    recommendation_id: UUID
    conversation_id: UUID | None
    request_id: UUID
    status: RecommendationStatus
    created_at: datetime
    valid_until: datetime | None = None
    language: str | None = None
    risk: Risk | None = None
    recommendation: RecommendationBody | None = None
    routes: Routes | None = None
    hazards: list[Hazard] = Field(default_factory=list)
    emergency_instructions: EmergencyInstructions | None = None
    sources: list[SourceItem] = Field(default_factory=list)
    data_freshness: DataFreshness | None = None
    service_status: dict[str, ServiceState] = Field(default_factory=dict)
    clarification: Clarification | None = None
    warnings: list[WarningItem] = Field(default_factory=list)
    versions: Versions | None = None
    disclaimer: str | None = None
    # Only while processing: follow the job for progress.
    job_id: UUID | None = None
    # Only when failed.
    error: ErrorInfo | None = None

    @classmethod
    def from_record(cls, record: RecommendationRecord) -> RecommendationResponse:
        payload = dict(record.payload or {})
        payload.pop("status", None)
        error = None
        if record.error_code is not None:
            known = {code.value for code in ErrorCode}
            code = ErrorCode(record.error_code) if record.error_code in known else None
            message = ERROR_SPECS[code].detail if code else "The request could not be completed."
            error = {"code": record.error_code, "message": message}
        return cls.model_validate(
            {
                **payload,
                "recommendation_id": record.id,
                "conversation_id": record.conversation_id,
                "request_id": record.request_id,
                "status": record.status,
                "created_at": record.created_at,
                "job_id": record.job_id,
                "error": error,
            }
        )


ESTIMATED_SECONDS = 20


class JobAccepted(_Strict):
    job_id: UUID
    status: Literal["queued"] = "queued"
    recommendation_id: UUID
    conversation_id: UUID
    events_url: str
    status_url: str
    estimated_seconds: int = ESTIMATED_SECONDS

    @classmethod
    def build(cls, job_id: UUID, recommendation_id: UUID, conversation_id: UUID) -> JobAccepted:
        return cls(
            job_id=job_id,
            recommendation_id=recommendation_id,
            conversation_id=conversation_id,
            events_url=f"/v1/jobs/{job_id}/events",
            status_url=f"/v1/jobs/{job_id}",
        )


# ------------------------------------------------------------------ follow-up overrides


class PreferenceChanges(_Strict):
    travel_modes: list[TravelMode] | None = Field(default=None, max_length=len(TravelMode))
    avoid: list[AvoidOption] | None = Field(default=None, max_length=len(AvoidOption))
    max_travel_hours: int | None = None
    mobility_needs: list[MobilityNeed] | None = Field(default=None, max_length=len(MobilityNeed))
    traveler_count: int | None = None

    def to_domain(self) -> PreferenceOverrides:
        return PreferenceOverrides(
            travel_modes=_tuple(self.travel_modes),
            avoid=_tuple(self.avoid),
            max_travel_hours=self.max_travel_hours,
            mobility_needs=_tuple(self.mobility_needs),
            traveler_count=self.traveler_count,
        )


class TravelOverrides(_Strict):
    """Partial TravelRequest for follow-ups; omitted or null fields keep the earlier value."""

    origin: Location | None = None
    destination: Location | None = None
    waypoints: list[Location] | None = Field(default=None, max_length=50)
    departure_time: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=35)
    preferences: PreferenceChanges | None = None

    def to_domain(self) -> RequestOverrides:
        return RequestOverrides(
            origin=self.origin.to_domain() if self.origin else None,
            destination=self.destination.to_domain() if self.destination else None,
            waypoints=(
                tuple(p.to_domain() for p in self.waypoints) if self.waypoints is not None else None
            ),
            departure_time=self.departure_time,
            timezone=self.timezone,
            language=self.language,
            preferences=self.preferences.to_domain() if self.preferences else None,
        )


def _tuple[T](values: list[T] | None) -> tuple[T, ...] | None:
    return tuple(values) if values is not None else None


# ------------------------------------------------------------------ history


class RecommendationSummary(_Strict):
    recommendation_id: UUID
    created_at: datetime
    status: RecommendationStatus
    risk_level: RiskLevel | None
    recommendation_type: RecommendationType | None
    origin_name: str | None
    destination_name: str | None
    departure_time: datetime

    @classmethod
    def from_record(cls, record: RecommendationSummaryRecord) -> RecommendationSummary:
        return cls(
            recommendation_id=record.id,
            created_at=record.created_at,
            status=record.status,
            risk_level=record.risk_level,
            recommendation_type=record.recommendation_type,
            origin_name=record.origin_name,
            destination_name=record.destination_name,
            departure_time=record.departure_time,
        )


class RecommendationPage(_Strict):
    items: list[RecommendationSummary]
    next_cursor: str | None
