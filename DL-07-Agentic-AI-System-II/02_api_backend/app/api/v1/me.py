"""E-20 GET / PATCH / DELETE /v1/me (docs/02_api_spec.md section 7.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.audit import client_ip_hash, correlation_id
from app.api.auth import principal_key, require_scopes
from app.api.deps import get_current_user, get_me_service
from app.api.resources import get_resources
from app.api.v1.responses import json_response
from app.core.security import Principal, Scope
from app.schemas.v1.me import DeletionAccepted, MePatch, MeResponse
from app.services.me_service import MeService
from app.services.ports import UserRef

router = APIRouter(prefix="/me", tags=["me"])

_reader = require_scopes(Scope.PROFILE_READ)
_writer = require_scopes(Scope.PROFILE_WRITE)


@router.get("", summary="My profile and consents", response_model=MeResponse)
async def get_me(
    principal: Principal = Depends(_reader),
    user: UserRef = Depends(get_current_user),
    service: MeService = Depends(get_me_service),
) -> MeResponse:
    # The e-mail is only in the token; it is masked and never stored (D-80).
    record, masked = await service.get(user, email=principal.email)
    return MeResponse.from_record(record, masked)


@router.patch(
    "",
    summary="Change my profile or consents (JSON Merge Patch)",
    response_model=MeResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/merge-patch+json": {"schema": {"$ref": "#/components/schemas/MePatch"}}
            }
        }
    },
)
async def update_me(
    body: MePatch,
    request: Request,
    principal: Principal = Depends(_writer),
    user: UserRef = Depends(get_current_user),
    service: MeService = Depends(get_me_service),
) -> MeResponse:
    record = await service.update(
        user,
        body.to_domain(),
        correlation_id=correlation_id(),
        ip_hash=client_ip_hash(request),
    )
    return MeResponse.from_record(record, None)


@router.delete(
    "",
    summary="Delete my account and data",
    status_code=202,
    response_model=DeletionAccepted,
)
async def delete_me(
    request: Request,
    response: Response,
    principal: Principal = Depends(_writer),
    user: UserRef = Depends(get_current_user),
    service: MeService = Depends(get_me_service),
) -> JSONResponse:
    await service.delete(
        user,
        principal_hash=principal_key(get_resources(request), principal),
        correlation_id=correlation_id(),
        ip_hash=client_ip_hash(request),
    )
    return json_response(DeletionAccepted(), 202, response)
