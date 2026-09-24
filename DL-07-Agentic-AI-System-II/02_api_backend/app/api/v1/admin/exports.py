"""POST/GET /v1/admin/exports/training-data (FR-19, D-92)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.api.deps import get_training_export_service
from app.api.idempotency import IdempotentRoute
from app.api.v1.admin.access import admin_actor
from app.api.v1.responses import json_response
from app.core.security import Scope
from app.schemas.v1.admin import (
    TrainingExportAccepted,
    TrainingExportRequest,
    TrainingExportResponse,
)
from app.services.admin_service import Actor
from app.services.training_export_service import TrainingExportService

router = APIRouter(
    prefix="/admin/exports/training-data", tags=["admin"], route_class=IdempotentRoute
)


@router.post(
    "",
    summary="Export anonymized training data for a time range",
    status_code=202,
    response_model=TrainingExportAccepted,
)
async def request_training_export(
    body: TrainingExportRequest,
    response: Response,
    actor: Actor = Depends(admin_actor(Scope.ADMIN_WRITE, "export.training_data")),
    service: TrainingExportService = Depends(get_training_export_service),
) -> JSONResponse:
    record = await service.request(actor, start=body.range_from, end=body.range_to)
    return json_response(
        TrainingExportAccepted(export_id=record.id, status=record.status),
        202,
        response,
        location=f"/v1/admin/exports/training-data/{record.id}",
    )


@router.get(
    "/{export_id}",
    summary="Training export status and download link",
    response_model=TrainingExportResponse,
)
async def get_training_export(
    export_id: UUID,
    actor: Actor = Depends(admin_actor(Scope.ADMIN_WRITE, "export.training_data_read")),
    service: TrainingExportService = Depends(get_training_export_service),
) -> TrainingExportResponse:
    return TrainingExportResponse.from_view(await service.get(actor, export_id))
