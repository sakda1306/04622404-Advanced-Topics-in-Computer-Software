"""GET /v1/admin/audit-logs (docs/02_api_spec.md section 8.2): newest first."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_admin_service
from app.api.v1.admin.access import admin_actor
from app.core.security import Scope
from app.domain.admin import AuditFilter
from app.domain.enums import ActorType, AuditResult
from app.schemas.v1.admin import AuditLogItem, AuditLogPage
from app.services.admin_service import Actor, AdminService

router = APIRouter(prefix="/admin/audit-logs", tags=["admin"])


@router.get(
    "",
    summary="Audit log in a time range (default: the last 24 hours)",
    response_model=AuditLogPage,
)
async def list_audit_logs(
    action: str | None = Query(default=None, max_length=64),
    actor_type: ActorType | None = Query(default=None),
    result: AuditResult | None = Query(default=None),
    target_type: str | None = Query(default=None, max_length=32),
    target_id: str | None = Query(default=None, max_length=128),
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=200),
    actor: Actor = Depends(admin_actor(Scope.ADMIN_READ, "admin.audit_logs_list")),
    service: AdminService = Depends(get_admin_service),
) -> AuditLogPage:
    page = await service.audit_logs(
        actor,
        start=start,
        end=end,
        where=AuditFilter(
            action=action,
            actor_type=actor_type.value if actor_type else None,
            result=result.value if result else None,
            target_type=target_type,
            target_id=target_id,
        ),
        limit=limit,
        cursor=cursor,
    )
    return AuditLogPage(
        items=[AuditLogItem.from_record(item) for item in page.items],
        next_cursor=page.next_cursor,
    )
