"""Admin tools (FR-18, docs/02_api_spec.md section 8.2): jobs, recommendation diagnostics
and the audit log.

Every call is written to the audit log, including refused ones (D-95). Admins see
diagnostics only: no user ids, places, questions or answers (D-94).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.domain.admin import AuditFilter, TimeRange, check_audit_filter, resolve_range
from app.domain.enums import ActorType, AuditResult, JobStatus, JobType
from app.services.pagination import (
    Cursor,
    Page,
    build_page,
    decode_cursor,
    page_limit,
)
from app.services.ports import (
    AdminJobRecord,
    AdminRecommendationRecord,
    AdminRepository,
    AuditEntry,
    AuditLogRecord,
    AuditPort,
)

DEFAULT_WINDOW = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is acting: the token subject plus request details for the audit log."""

    subject: str
    correlation_id: str
    ip_hash: str | None


async def write_admin_audit(
    audit: AuditPort,
    actor: Actor,
    action: str,
    result: AuditResult,
    *,
    target: tuple[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await audit.write(
        AuditEntry(
            actor_type=ActorType.ADMIN,
            actor_ref=actor.subject,
            action=action,
            target_type=target[0] if target else None,
            target_id=target[1] if target else None,
            result=result,
            correlation_id=actor.correlation_id,
            ip_hash=actor.ip_hash,
            metadata=metadata or {},
        )
    )


def iso_range(period: TimeRange) -> dict[str, str]:
    return {"from": period.start.isoformat(), "to": period.end.isoformat()}


class AdminService:
    def __init__(
        self,
        *,
        repository: AdminRepository,
        audit: AuditPort,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._audit = audit
        self._settings = settings
        self._clock = clock

    def _range(self, start: datetime | None, end: datetime | None) -> TimeRange:
        return resolve_range(
            start,
            end,
            now=self._clock.now(),
            default=DEFAULT_WINDOW,
            max_days=self._settings.admin.admin_max_range_days,
        )

    async def jobs(
        self,
        actor: Actor,
        *,
        start: datetime | None,
        end: datetime | None,
        status: JobStatus | None,
        job_type: JobType | None,
        limit: int | None,
        cursor: str | None,
    ) -> Page[AdminJobRecord]:
        period = self._range(start, end)
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.jobs(
            period=period,
            status=status,
            job_type=job_type,
            limit=size,
            cursor=decode_cursor(cursor),
        )
        page = build_page(rows, size, key=lambda row: Cursor(row.created_at, row.id))
        await write_admin_audit(
            self._audit,
            actor,
            "admin.jobs_list",
            AuditResult.SUCCESS,
            metadata={
                **iso_range(period),
                "status": status.value if status else None,
                "type": job_type.value if job_type else None,
                "count": len(page.items),
            },
        )
        return page

    async def recommendation(
        self, actor: Actor, recommendation_id: UUID
    ) -> AdminRecommendationRecord:
        record = await self._repo.recommendation(recommendation_id)
        await write_admin_audit(
            self._audit,
            actor,
            "admin.recommendation_read",
            AuditResult.SUCCESS if record is not None else AuditResult.ERROR,
            target=("recommendation", str(recommendation_id)),
        )
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return record

    async def audit_logs(
        self,
        actor: Actor,
        *,
        start: datetime | None,
        end: datetime | None,
        where: AuditFilter,
        limit: int | None,
        cursor: str | None,
    ) -> Page[AuditLogRecord]:
        period = self._range(start, end)
        checked = check_audit_filter(where)
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.audit_logs(
            period=period,
            where=checked,
            limit=size,
            cursor=decode_cursor(cursor, numeric_id=True),
        )
        page = build_page(rows, size, key=lambda row: Cursor(row.occurred_at, row.id))
        await write_admin_audit(
            self._audit,
            actor,
            "admin.audit_logs_list",
            AuditResult.SUCCESS,
            metadata={
                **iso_range(period),
                "action": checked.action,
                "target_type": checked.target_type,
                "count": len(page.items),
            },
        )
        return page
