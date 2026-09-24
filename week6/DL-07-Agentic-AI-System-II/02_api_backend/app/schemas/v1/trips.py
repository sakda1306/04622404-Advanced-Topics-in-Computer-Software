"""API contract for trips (docs/02_api_spec.md section 7.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AlertChannel,
    RecommendationStatus,
    RecommendationType,
    RequestMode,
    RiskLevel,
    TripStatus,
)
from app.domain.normalization import GeoPoint, TravelPreferences
from app.domain.trips import AlertChanges, AlertSettings, TripChanges, TripDraft
from app.schemas.v1.travel import Location, PreferenceChanges, Preferences
from app.services.ports import TripRecord


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nulls(model: BaseModel, prefix: str = "") -> set[str]:
    """Fields the client sent as `null` (JSON Merge Patch: remove or reject)."""
    return {f"{prefix}{name}" for name in model.model_fields_set if getattr(model, name) is None}


# ------------------------------------------------------------------ request


class AlertsBody(_Strict):
    enabled: bool = False
    # Required to turn alerts on; the stored consent time is the server's (D-62).
    consent_at: datetime | None = None
    channels: list[AlertChannel] = Field(
        default_factory=lambda: [AlertChannel.IN_APP], max_length=10
    )

    def to_domain(self) -> AlertSettings:
        return AlertSettings(
            enabled=self.enabled, consent_at=self.consent_at, channels=tuple(self.channels)
        )


class TripCreate(_Strict):
    # Hard caps for parsing; the business limits are checked in the domain.
    name: str = Field(max_length=1000)
    origin: Location
    destination: Location
    waypoints: list[Location] = Field(default_factory=list, max_length=50)
    departure_time: datetime
    timezone: str = Field(max_length=64)
    preferences: Preferences = Field(default_factory=Preferences)
    alerts: AlertsBody = Field(default_factory=AlertsBody)

    def to_domain(self) -> TripDraft:
        prefs = self.preferences
        return TripDraft(
            name=self.name,
            origin=self.origin.to_domain(),
            destination=self.destination.to_domain(),
            departure_time=self.departure_time,
            timezone=self.timezone,
            waypoints=tuple(p.to_domain() for p in self.waypoints),
            preferences=TravelPreferences(
                travel_modes=tuple(prefs.travel_modes),
                avoid=tuple(prefs.avoid),
                max_travel_hours=prefs.max_travel_hours,
                mobility_needs=tuple(prefs.mobility_needs),
                traveler_count=prefs.traveler_count,
            ),
            alerts=self.alerts.to_domain(),
        )


class AlertsPatch(_Strict):
    enabled: bool | None = None
    consent_at: datetime | None = None
    channels: list[AlertChannel] | None = Field(default=None, max_length=10)

    def to_domain(self) -> AlertChanges:
        return AlertChanges(
            enabled=self.enabled,
            consent_at=self.consent_at,
            channels=tuple(self.channels) if self.channels is not None else None,
        )


class TripPatch(_Strict):
    """JSON Merge Patch (RFC 7396) of a trip; `null` removes or is rejected (D-60)."""

    name: str | None = Field(default=None, max_length=1000)
    origin: Location | None = None
    destination: Location | None = None
    waypoints: list[Location] | None = Field(default=None, max_length=50)
    departure_time: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)
    preferences: PreferenceChanges | None = None
    alerts: AlertsPatch | None = None
    status: TripStatus | None = None

    def to_domain(self) -> TripChanges:
        nulls = _nulls(self)
        if self.preferences is not None:
            nulls |= _nulls(self.preferences, "preferences.")
        if self.alerts is not None:
            nulls |= _nulls(self.alerts, "alerts.")
        return TripChanges(
            name=self.name,
            origin=self.origin.to_domain() if self.origin else None,
            destination=self.destination.to_domain() if self.destination else None,
            waypoints=(
                tuple(p.to_domain() for p in self.waypoints) if self.waypoints is not None else None
            ),
            departure_time=self.departure_time,
            timezone=self.timezone,
            preferences=self.preferences.to_domain() if self.preferences else None,
            alerts=self.alerts.to_domain() if self.alerts else None,
            status=self.status,
            explicit_nulls=frozenset(nulls),
        )


class AssessmentCreate(_Strict):
    mode: RequestMode = RequestMode.AUTO
    language: str | None = Field(default=None, max_length=35)


# ------------------------------------------------------------------ response


def _location(point: GeoPoint) -> Location:
    return Location(lat=point.lat, lon=point.lon, name=point.name, place_id=point.place_id)


class AlertsView(_Strict):
    enabled: bool
    consent_at: datetime | None
    channels: list[AlertChannel]


class LastAssessment(_Strict):
    recommendation_id: UUID
    status: RecommendationStatus
    risk_level: RiskLevel | None
    recommendation_type: RecommendationType | None
    created_at: datetime
    outdated: bool


class TripResponse(_Strict):
    trip_id: UUID
    name: str
    origin: Location
    destination: Location
    waypoints: list[Location]
    departure_time: datetime
    timezone: str
    preferences: Preferences
    alerts: AlertsView
    status: TripStatus
    last_assessment: LastAssessment | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: TripRecord) -> TripResponse:
        draft = record.draft
        prefs = draft.preferences
        last = record.last_assessment
        return cls(
            trip_id=record.id,
            name=draft.name,
            origin=_location(draft.origin),
            destination=_location(draft.destination),
            waypoints=[_location(p) for p in draft.waypoints],
            departure_time=draft.departure_time,
            timezone=draft.timezone,
            preferences=Preferences(
                travel_modes=list(prefs.travel_modes),
                avoid=list(prefs.avoid),
                max_travel_hours=prefs.max_travel_hours,
                mobility_needs=list(prefs.mobility_needs),
                traveler_count=prefs.traveler_count,
            ),
            alerts=AlertsView(
                enabled=draft.alerts.enabled,
                consent_at=draft.alerts.consent_at,
                channels=list(draft.alerts.channels),
            ),
            status=draft.status,
            last_assessment=(
                LastAssessment(
                    recommendation_id=last.recommendation_id,
                    status=last.status,
                    risk_level=last.risk_level,
                    recommendation_type=last.recommendation_type,
                    created_at=last.created_at,
                    outdated=record.assessment_outdated,
                )
                if last is not None
                else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class TripPage(_Strict):
    items: list[TripResponse]
    next_cursor: str | None
