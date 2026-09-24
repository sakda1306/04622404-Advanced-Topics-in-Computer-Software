"""E-21 POST and E-22 GET /v1/me/data-export (docs/02_api_spec.md section 7.4)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.audit import correlation_id
from app.api.auth import require_scopes
from app.api.deps import get_current_user, get_export_service
from app.api.idempotency import IdempotentRoute
from app.api.v1.responses import json_response
from app.core.security import Scope
from app.domain.enums import ExportStatus
from app.services.export_service import ExportService, ExportView
from app.services.ports import UserRef

router = APIRouter(prefix="/me/data-export", tags=["me"], route_class=IdempotentRoute)

_OWN_DATA = [Depends(require_scopes(Scope.PROFILE_READ))]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportAccepted(_Strict):
    export_id: UUID
    status: ExportStatus


class ExportResponse(_Strict):
    export_id: UUID
    status: ExportStatus
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    # Short-lived signed link (P-62); only while the file exists.
    download_url: str | None

    @classmethod
    def from_view(cls, view: ExportView) -> ExportResponse:
        record = view.record
        return cls(
            export_id=record.id,
            status=record.status,
            created_at=record.created_at,
            completed_at=record.completed_at,
            expires_at=record.expires_at,
            download_url=view.download_url,
        )


@router.post(
    "",
    summary="Export all my data (once a day)",
    status_code=202,
    response_model=ExportAccepted,
    dependencies=_OWN_DATA,
)
async def request_export(
    response: Response,
    user: UserRef = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> JSONResponse:
    record = await service.request(user, correlation_id=correlation_id())
    return json_response(
        ExportAccepted(export_id=record.id, status=record.status),
        202,
        response,
        location=f"/v1/me/data-export/{record.id}",
    )


@router.get(
    "/{export_id}",
    summary="Export status and download link",
    response_model=ExportResponse,
    dependencies=_OWN_DATA,
)
async def get_export(
    export_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> ExportResponse:
    return ExportResponse.from_view(await service.get(user, export_id))
