"""Store and load travel requests (shared by the recommendation and conversation repositories)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.infrastructure.db.models import TravelRequestModel


def point_value(point: GeoPoint) -> WKTElement:
    return WKTElement(f"POINT({point.lon!r} {point.lat!r})", srid=4326)


def point_json(point: GeoPoint) -> dict[str, Any]:
    return {"lat": point.lat, "lon": point.lon, "name": point.name, "place_id": point.place_id}


def preferences_json(prefs: TravelPreferences) -> dict[str, Any]:
    return {
        "travel_modes": list(prefs.travel_modes),
        "avoid": list(prefs.avoid),
        "max_travel_hours": prefs.max_travel_hours,
        "mobility_needs": list(prefs.mobility_needs),
        "traveler_count": prefs.traveler_count,
    }


def parse_preferences(data: dict[str, Any]) -> TravelPreferences:
    return TravelPreferences(
        travel_modes=tuple(TravelMode(v) for v in data.get("travel_modes", [])),
        avoid=tuple(AvoidOption(v) for v in data.get("avoid", [])),
        max_travel_hours=data.get("max_travel_hours"),
        mobility_needs=tuple(MobilityNeed(v) for v in data.get("mobility_needs", [])),
        traveler_count=data.get("traveler_count", 1),
    )


async def load_request(
    session: AsyncSession, request_id: UUID, *, question: str | None
) -> tuple[NormalizedTravelRequest, TravelRequestModel]:
    """The stored request as the domain type, plus its row for the other columns."""
    origin = cast(TravelRequestModel.origin, Geometry)
    destination = cast(TravelRequestModel.destination, Geometry)
    row = (
        await session.execute(
            select(
                TravelRequestModel,
                func.ST_Y(origin),
                func.ST_X(origin),
                func.ST_Y(destination),
                func.ST_X(destination),
            ).where(TravelRequestModel.id == request_id)
        )
    ).one()
    travel: TravelRequestModel = row[0]
    request = NormalizedTravelRequest(
        origin=GeoPoint(row[1], row[2], name=travel.origin_name),
        destination=GeoPoint(row[3], row[4], name=travel.destination_name),
        waypoints=tuple(
            GeoPoint(p["lat"], p["lon"], name=p.get("name"), place_id=p.get("place_id"))
            for p in travel.waypoints
        ),
        departure_time=travel.departure_time,
        timezone=travel.timezone,
        language=travel.language,
        preferences=parse_preferences(travel.preferences),
        question=question,
    )
    return request, travel
