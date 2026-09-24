"""E-23 GET /v1/service-status (docs/02_api_spec.md section 8.1): public, no login.

Shows states only: no provider names, hosts or error text.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_ops_service
from app.domain.normalization import negotiate_language
from app.domain.service_status import ComponentState, status_message
from app.services.ops_service import OpsService

router = APIRouter(tags=["service-status"])


class ServiceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ComponentState
    updated_at: datetime
    components: dict[str, ComponentState]
    message: str


@router.get("/service-status", response_model=ServiceStatusResponse, summary="Service status")
async def service_status(
    response: Response,
    accept_language: str | None = Header(default=None, max_length=200),
    ops: OpsService = Depends(get_ops_service),
) -> ServiceStatusResponse:
    summary = await ops.service_status()
    seconds = ops.cache_seconds
    response.headers["Cache-Control"] = f"public, max-age={seconds}"
    response.headers["Vary"] = "Accept-Language"
    return ServiceStatusResponse(
        status=summary.status,
        updated_at=summary.updated_at,
        components=summary.components,
        message=status_message(summary.status, negotiate_language(None, accept_language)),
    )
