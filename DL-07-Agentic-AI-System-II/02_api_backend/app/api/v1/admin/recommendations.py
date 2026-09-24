"""GET /v1/admin/recommendations/{id}: diagnostics, versions and trace ids (section 8.2)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_admin_service
from app.api.v1.admin.access import admin_actor
from app.core.security import Scope
from app.schemas.v1.admin import AdminRecommendation
from app.services.admin_service import Actor, AdminService

router = APIRouter(prefix="/admin/recommendations", tags=["admin"])


@router.get(
    "/{recommendation_id}",
    summary="Recommendation diagnostics (no places, questions or answers)",
    response_model=AdminRecommendation,
)
async def get_recommendation(
    recommendation_id: UUID,
    actor: Actor = Depends(admin_actor(Scope.ADMIN_READ, "admin.recommendation_read")),
    service: AdminService = Depends(get_admin_service),
) -> AdminRecommendation:
    return AdminRecommendation.from_record(await service.recommendation(actor, recommendation_id))
