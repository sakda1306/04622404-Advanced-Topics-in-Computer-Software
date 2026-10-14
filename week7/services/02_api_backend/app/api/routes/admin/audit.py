"""Audit log page (Should)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.admin import AuditEntryOut
from app.schemas.common import Page, Text
from app.services import audit as audit_service

router = APIRouter()


@router.get("/audit")
async def audit(
    db: DbDep,
    actor_id: UUID | None = None,
    action: Annotated[Text | None, Query(max_length=40)] = None,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[AuditEntryOut]:
    return await audit_service.list_audit(
        db, actor_id=actor_id, action=action, days=days, limit=limit, cursor=cursor
    )
