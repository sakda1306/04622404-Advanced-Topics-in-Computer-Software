"""E-14..E-18 /v1/trips (docs/02_api_spec.md section 7.2)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from app.api.auth import recommend_rate_limit, require_scopes
from app.api.deps import get_current_user, get_trip_service
from app.api.idempotency import IdempotentRoute
from app.api.v1.responses import accepted_response, json_response
from app.core.ids import current_correlation_id, current_request_id, new_id
from app.core.security import Scope
from app.domain.enums import TripStatus
from app.schemas.v1.travel import (
    JobAccepted,
    RecommendationPage,
    RecommendationResponse,
    RecommendationSummary,
)
from app.schemas.v1.trips import AssessmentCreate, TripCreate, TripPage, TripPatch, TripResponse
from app.services.ports import UserRef
from app.services.recommendation_service import Accepted
from app.services.trip_service import TripService

router = APIRouter(prefix="/trips", tags=["trips"], route_class=IdempotentRoute)

_READ = [Depends(require_scopes(Scope.TRAVEL_READ))]
_WRITE = [Depends(require_scopes(Scope.TRAVEL_WRITE))]

CursorQuery = Query(default=None, max_length=200)


@router.post(
    "", summary="Save a trip", status_code=201, response_model=TripResponse, dependencies=_WRITE
)
async def create_trip(
    body: TripCreate,
    response: Response,
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> JSONResponse:
    created = await service.create(user, body.to_domain())
    return json_response(
        TripResponse.from_record(created), 201, response, location=f"/v1/trips/{created.id}"
    )


@router.get(
    "", summary="Saved trips, latest departure first", response_model=TripPage, dependencies=_READ
)
async def list_trips(
    limit: int | None = Query(default=None),
    cursor: str | None = CursorQuery,
    status: TripStatus | None = Query(default=None),
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> TripPage:
    page = await service.list(user, limit=limit, cursor=cursor, status=status)
    return TripPage(
        items=[TripResponse.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{trip_id}", summary="Get a trip", response_model=TripResponse, dependencies=_READ)
async def get_trip(
    trip_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> TripResponse:
    return TripResponse.from_record(await service.get(user, trip_id))


@router.patch(
    "/{trip_id}",
    summary="Change a trip (JSON Merge Patch)",
    response_model=TripResponse,
    dependencies=_WRITE,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/merge-patch+json": {
                    "schema": {"$ref": "#/components/schemas/TripPatch"}
                }
            }
        }
    },
)
async def update_trip(
    trip_id: UUID,
    body: TripPatch,
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> TripResponse:
    return TripResponse.from_record(await service.update(user, trip_id, body.to_domain()))


@router.delete(
    "/{trip_id}",
    summary="Delete a trip (its assessments stay in the history)",
    status_code=204,
    response_class=Response,
    dependencies=_WRITE,
)
async def delete_trip(
    trip_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> Response:
    await service.delete(user, trip_id)
    return Response(status_code=204)


@router.post(
    "/{trip_id}/assessments",
    summary="Assess the trip now",
    response_model=RecommendationResponse,
    responses={202: {"model": JobAccepted, "description": "Still running; follow the job"}},
    dependencies=[*_WRITE, Depends(recommend_rate_limit)],
)
async def assess_trip(
    trip_id: UUID,
    response: Response,
    body: AssessmentCreate | None = None,
    accept_language: str | None = Header(default=None, max_length=200),
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> JSONResponse:
    options = body or AssessmentCreate()
    outcome = await service.assess(
        user,
        trip_id,
        mode=options.mode,
        language=options.language,
        accept_language=accept_language,
        correlation_id=current_correlation_id() or current_request_id() or str(new_id()),
    )
    if isinstance(outcome, Accepted):
        return accepted_response(outcome, response)
    return json_response(RecommendationResponse.from_record(outcome.record), 200, response)


@router.get(
    "/{trip_id}/assessments",
    summary="Assessments of the trip, newest first",
    response_model=RecommendationPage,
    dependencies=_READ,
)
async def list_assessments(
    trip_id: UUID,
    limit: int | None = Query(default=None),
    cursor: str | None = CursorQuery,
    user: UserRef = Depends(get_current_user),
    service: TripService = Depends(get_trip_service),
) -> RecommendationPage:
    page = await service.assessments(user, trip_id, limit=limit, cursor=cursor)
    return RecommendationPage(
        items=[RecommendationSummary.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )
