"""Small builders for database rows used by integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2 import WKTElement

from app.core.ids import new_id
from app.infrastructure.db.models import (
    ConversationModel,
    RecommendationModel,
    TravelRequestModel,
    TripModel,
    UserModel,
)

BANGKOK = (100.5018, 13.7563)
CHIANG_MAI = (98.9853, 18.7883)
TOKYO = (139.6917, 35.6895)


def point(lon_lat: tuple[float, float]) -> WKTElement:
    lon, lat = lon_lat
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def later(days: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


def user(**overrides: Any) -> UserModel:
    uid = new_id()
    values: dict[str, Any] = {
        "id": uid,
        "oidc_issuer": "http://testserver/dev-issuer",
        "oidc_subject": f"sub-{uid}",
        "pseudonymous_id": f"p-{uid}",
    }
    return UserModel(**(values | overrides))


def conversation(owner: UserModel, **overrides: Any) -> ConversationModel:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": owner.id,
        "language": "th",
        "expires_at": later(),
    }
    return ConversationModel(**(values | overrides))


def trip(owner: UserModel, **overrides: Any) -> TripModel:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": owner.id,
        "name": "Chiang Mai",
        "origin": point(BANGKOK),
        "destination": point(CHIANG_MAI),
        "departure_time": later(3),
        "timezone": "Asia/Bangkok",
        "expires_at": later(33),
    }
    return TripModel(**(values | overrides))


def travel_request(owner: UserModel, **overrides: Any) -> TravelRequestModel:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": owner.id,
        "source": "RECOMMENDATION",
        "origin": point(BANGKOK),
        "destination": point(CHIANG_MAI),
        "departure_time": later(3),
        "timezone": "Asia/Bangkok",
        "language": "th",
        "preferences": {},
        "has_question": False,
        "mode": "auto",
        "correlation_id": "corr-test",
        "expires_at": later(),
    }
    return TravelRequestModel(**(values | overrides))


def recommendation(
    owner: UserModel, request: TravelRequestModel, **overrides: Any
) -> RecommendationModel:
    values: dict[str, Any] = {
        "id": new_id(),
        "request_id": request.id,
        "user_id": owner.id,
        "status": "completed",
        "risk_level": "LOW",
        "recommendation_type": "TRAVEL_NORMALLY",
        "departure_time": request.departure_time,
        "payload": {"summary": "ok"},
        "expires_at": later(),
    }
    return RecommendationModel(**(values | overrides))
