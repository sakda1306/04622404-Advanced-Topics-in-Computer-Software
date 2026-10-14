"""/api/admin/* — every path requires role=admin, checked here on each call (CONTRACT §1.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.api.routes.admin import audit, dashboard, kb, pipeline, reports, users

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
for module in (dashboard, pipeline, reports, audit, users, kb):
    router.include_router(module.router)
