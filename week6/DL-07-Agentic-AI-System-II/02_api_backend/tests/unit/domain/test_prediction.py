from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.enums import RecommendationStatus, RecommendationType, RiskLevel, TravelMode
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.domain.prediction import build_prediction

NOW = datetime(2026, 9, 18, 8, 20, tzinfo=UTC)


@dataclass
class Result:
    status: RecommendationStatus = RecommendationStatus.COMPLETED
    risk_level: RiskLevel | None = RiskLevel.MEDIUM
    risk_score: float | None = 0.42
    risk_confidence: float | None = 0.8
    recommendation_type: RecommendationType | None = RecommendationType.CHANGE_ROUTE
    payload: dict[str, Any] = field(
        default_factory=lambda: {
            "hazards": [{"type": "FLOOD"}, {"type": "STORM"}, {"type": "FLOOD"}],
            "data_freshness": {"overall_is_stale": False, "items": []},
            "service_status": {"weather": "ok"},
        }
    )
    applied_rules: tuple[str, ...] = ("R-03",)
    agent_version: str | None = "a-1"
    risk_model_version: str | None = "r-1"
    prompt_version: str | None = "p-1"


def request(departure: datetime) -> NormalizedTravelRequest:
    return NormalizedTravelRequest(
        origin=GeoPoint(13.756331, 100.501765, name="Bangkok"),
        destination=GeoPoint(18.788343, 98.985300, name="Chiang Mai"),
        waypoints=(),
        departure_time=departure,
        timezone="Asia/Bangkok",
        language="th",
        preferences=TravelPreferences(travel_modes=(TravelMode.TRAIN, TravelMode.BUS)),
        question="private question",
    )


def test_prediction_is_anonymized() -> None:
    departure = NOW + timedelta(hours=26, minutes=50)

    data = build_prediction(request(departure), Result(), now=NOW, region_code="TH", precision=5)

    assert len(data.origin_geohash) == 5
    assert len(data.destination_geohash) == 5
    assert data.origin_geohash != data.destination_geohash
    assert data.departure_bucket == departure.replace(minute=0, second=0, microsecond=0)
    assert data.lead_time_hours == 26
    assert data.travel_modes == ("TRAIN", "BUS")
    assert data.hazard_types == ("FLOOD", "STORM")
    assert data.region_code == "TH"
    assert data.status is RecommendationStatus.COMPLETED
    assert data.risk_level is RiskLevel.MEDIUM
    assert data.safety_gate_rules == ("R-03",)
    assert (data.agent_version, data.risk_model_version, data.prompt_version) == (
        "a-1",
        "r-1",
        "p-1",
    )
    text = repr(data)
    assert "13.75" not in text
    assert "100.50" not in text
    assert "private question" not in text
    assert "Bangkok" not in text


def test_departure_in_the_past_has_zero_lead_time() -> None:
    data = build_prediction(
        request(NOW - timedelta(minutes=30)), Result(), now=NOW, region_code=None, precision=4
    )
    assert data.lead_time_hours == 0
    assert len(data.origin_geohash) == 4


def test_missing_payload_parts_become_empty() -> None:
    data = build_prediction(
        request(NOW + timedelta(hours=3)),
        Result(payload={}, risk_level=None, recommendation_type=None),
        now=NOW,
        region_code=None,
        precision=5,
    )
    assert data.hazard_types == ()
    assert data.data_freshness == {}
    assert data.service_status == {}
    assert data.risk_level is None
