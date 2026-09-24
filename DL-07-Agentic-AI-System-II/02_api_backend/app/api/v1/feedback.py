"""E-19 POST /v1/recommendations/{recommendation_id}/feedback (docs/02_api_spec.md 7.3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.audit import client_ip_hash, correlation_id
from app.api.auth import require_scopes
from app.api.deps import get_current_user, get_feedback_service
from app.api.idempotency import IdempotentRoute
from app.api.v1.responses import json_response
from app.core.security import Scope
from app.schemas.v1.feedback import FeedbackCreate, FeedbackCreated
from app.services.feedback_service import FeedbackService
from app.services.ports import UserRef

router = APIRouter(prefix="/recommendations", tags=["feedback"], route_class=IdempotentRoute)


@router.post(
    "/{recommendation_id}/feedback",
    summary="Rate a recommendation or report a problem",
    status_code=201,
    response_model=FeedbackCreated,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_WRITE))],
)
async def submit_feedback(
    recommendation_id: UUID,
    body: FeedbackCreate,
    request: Request,
    response: Response,
    user: UserRef = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
) -> JSONResponse:
    record = await service.submit(
        user,
        recommendation_id,
        body.to_domain(),
        correlation_id=correlation_id(),
        ip_hash=client_ip_hash(request),
    )
    return json_response(FeedbackCreated.from_record(record), 201, response)
