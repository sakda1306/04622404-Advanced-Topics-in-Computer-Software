"""Anonymized copy of a result for the Data Feedback Loop (docs/03_data_design.md 3.9, D-75).

No user id, no exact coordinates (geohash only), no names and no text from the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.geo import geohash_encode
from app.domain.enums import RecommendationStatus, RecommendationType, RiskLevel
from app.domain.normalization import NormalizedTravelRequest


class ResultLike(Protocol):
    @property
    def status(self) -> RecommendationStatus: ...
    @property
    def risk_level(self) -> RiskLevel | None: ...
    @property
    def risk_score(self) -> float | None: ...
    @property
    def risk_confidence(self) -> float | None: ...
    @property
    def recommendation_type(self) -> RecommendationType | None: ...
    @property
    def payload(self) -> dict[str, Any]: ...
    @property
    def applied_rules(self) -> tuple[str, ...]: ...
    @property
    def agent_version(self) -> str | None: ...
    @property
    def risk_model_version(self) -> str | None: ...
    @property
    def prompt_version(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class PredictionData:
    origin_geohash: str
    destination_geohash: str
    region_code: str | None
    departure_bucket: datetime
    lead_time_hours: int
    travel_modes: tuple[str, ...]
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    hazard_types: tuple[str, ...]
    data_freshness: dict[str, Any]
    service_status: dict[str, Any]
    safety_gate_rules: tuple[str, ...]
    agent_version: str | None
    risk_model_version: str | None
    prompt_version: str | None


def _hazard_types(payload: dict[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    for hazard in payload.get("hazards") or []:
        kind = hazard.get("type") if isinstance(hazard, dict) else None
        if isinstance(kind, str) and kind not in found:
            found.append(kind)
    return tuple(found)


def build_prediction(
    request: NormalizedTravelRequest,
    result: ResultLike,
    *,
    now: datetime,
    region_code: str | None,
    precision: int,
) -> PredictionData:
    departure = request.departure_time.astimezone(UTC)
    lead_seconds = (departure - now).total_seconds()
    payload = result.payload
    return PredictionData(
        origin_geohash=geohash_encode(request.origin.lat, request.origin.lon, precision),
        destination_geohash=geohash_encode(
            request.destination.lat, request.destination.lon, precision
        ),
        region_code=region_code,
        departure_bucket=departure.replace(minute=0, second=0, microsecond=0),
        lead_time_hours=max(0, int(lead_seconds // 3600)),
        travel_modes=tuple(mode.value for mode in request.preferences.travel_modes),
        status=result.status,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        risk_confidence=result.risk_confidence,
        recommendation_type=result.recommendation_type,
        hazard_types=_hazard_types(payload),
        data_freshness=dict(payload.get("data_freshness") or {}),
        service_status=dict(payload.get("service_status") or {}),
        safety_gate_rules=tuple(result.applied_rules),
        agent_version=result.agent_version,
        risk_model_version=result.risk_model_version,
        prompt_version=result.prompt_version,
    )
