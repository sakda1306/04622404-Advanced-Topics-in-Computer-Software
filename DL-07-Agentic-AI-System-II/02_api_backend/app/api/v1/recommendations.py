"""E-01 POST and E-03 GET /v1/travel/recommendations (docs/02_api_spec.md section 5)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.api.auth import recommend_rate_limit, require_scopes
from app.api.deps import get_current_user, get_recommendation_service
from app.api.idempotency import IdempotentRoute
from app.api.v1.responses import accepted_response, json_response
from app.core.ids import current_correlation_id, current_request_id, new_id
from app.core.security import Scope
from app.domain.enums import RequestMode, RiskLevel
from app.schemas.v1.travel import (
    JobAccepted,
    RecommendationPage,
    RecommendationResponse,
    RecommendationSummary,
    TravelRequest,
)
from app.services.ports import UserRef
from app.services.recommendation_service import (
    Accepted,
    CreateRecommendation,
    RecommendationService,
)

router = APIRouter(
    prefix="/travel/recommendations", tags=["recommendations"], route_class=IdempotentRoute
)


@router.post(
    "",
    summary="Ask for a travel safety recommendation",
    status_code=200,
    response_model=RecommendationResponse,
    responses={202: {"model": JobAccepted, "description": "Still running; follow the job"}},
    dependencies=[Depends(require_scopes(Scope.TRAVEL_WRITE)), Depends(recommend_rate_limit)],
)
async def create_recommendation(
    body: TravelRequest,
    request: Request,
    response: Response,
    mode: RequestMode = Query(default=RequestMode.AUTO),
    accept_language: str | None = Header(default=None),
    user: UserRef = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> JSONResponse:
    command = CreateRecommendation(
        input=body.to_domain(accept_language),
        mode=mode,
        conversation_id=body.conversation_id,
        trip_id=body.trip_id,
        correlation_id=current_correlation_id() or current_request_id() or str(new_id()),
    )
    outcome = await service.create(user, command)
    if isinstance(outcome, Accepted):
        return accepted_response(outcome, response)
    return json_response(RecommendationResponse.from_record(outcome.record), 200, response)


@router.get(
    "",
    summary="Recommendation history, newest first",
    response_model=RecommendationPage,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_READ))],
)
async def list_recommendations(
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=200),
    created_from: AwareDatetime | None = Query(default=None, alias="from"),
    created_to: AwareDatetime | None = Query(default=None, alias="to"),
    risk_level: RiskLevel | None = Query(default=None),
    user: UserRef = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationPage:
    page = await service.list(
        user,
        limit=limit,
        cursor=cursor,
        created_from=created_from,
        created_to=created_to,
        risk_level=risk_level,
    )
    return RecommendationPage(
        items=[RecommendationSummary.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{recommendation_id}",
    summary="Get a recommendation",
    response_model=RecommendationResponse,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_READ))],
)
async def get_recommendation(
    recommendation_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    return RecommendationResponse.from_record(await service.get(user, recommendation_id))
