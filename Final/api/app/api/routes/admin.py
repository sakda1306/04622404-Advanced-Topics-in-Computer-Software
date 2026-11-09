"""The admin dashboard's data (Contract.md §2.9, PRD FR-40 – FR-45)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.core.errors import AppError, ErrorCode
from app.services import admin_service
from app.services.users import is_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
async def overview(
    user: CurrentUser,
    container: ContainerDep,
    db: DbDep,
    window: admin_service.Window = "today",
) -> dict[str, Any]:
    settings = container.settings
    if not is_admin(user, settings.admin_emails):
        raise AppError(ErrorCode.FORBIDDEN)
    return await admin_service.overview(db, settings, window=window)
