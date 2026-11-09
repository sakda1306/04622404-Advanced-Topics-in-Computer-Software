"""Today's quota (Contract.md §2.8, PRD FR-25)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import QuotaOut
from app.core.clock import iso
from app.services.quota_service import get_quota

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/quota")
async def quota(user: CurrentUser, container: ContainerDep, db: DbDep) -> QuotaOut:
    status = await get_quota(db, user.id, container.settings)
    return QuotaOut(
        day=status.day.isoformat(),
        requests_used=status.requests_used,
        requests_limit=status.requests_limit,
        tokens_used=status.tokens_used,
        tokens_limit=status.tokens_limit,
        reset_at=iso(status.reset_at),
        exhausted=status.exhausted,
    )
