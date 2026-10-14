"""Audit log of admin actions (CONTRACT §1.1).

Every non-GET admin call writes an entry before it answers. If the entry cannot be
written, the call answers 500: an action nobody can trace counts as failed.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, utcnow
from app.core.errors import AppError, ErrorCode
from app.core.ids import current_request_id
from app.core.logging import get_logger
from app.db.models import AuditEntry, User
from app.response_log.cursor import before_cursor, encode_cursor
from app.schemas.admin import AuditEntryOut, UserRef
from app.schemas.common import Page

log = get_logger(__name__)

ACTIONS = frozenset(
    {
        "pipeline.ingest",
        "report.generate",
        "report.edit",
        "report.publish",
        "report.unpublish",
        "user.update",
        "kb.delete",
        "kb.reindex",
    }
)


async def write_audit(
    db: AsyncSession,
    actor: User,
    action: str,
    target: str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    assert action in ACTIONS, action
    try:
        db.add(
            AuditEntry(
                actor_id=actor.id,
                action=action,
                target=target,
                detail={"before": before or {}, "after": after or {}},
                request_id=current_request_id(),
                created_at=utcnow(),
            )
        )
        await db.commit()
    except Exception as exc:
        log.exception("audit_write_failed", action=action)
        await db.rollback()
        raise AppError(ErrorCode.INTERNAL_ERROR, detail="บันทึก audit ไม่สำเร็จ") from exc


async def list_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str | None,
    days: int,
    limit: int,
    cursor: str | None,
) -> Page[AuditEntryOut]:
    query = (
        select(AuditEntry, User)
        .join(User, User.id == AuditEntry.actor_id)
        .where(AuditEntry.created_at >= utcnow() - timedelta(days=days))
        .order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
        .limit(limit + 1)
    )
    if actor_id:
        query = query.where(AuditEntry.actor_id == actor_id)
    if action:
        query = query.where(AuditEntry.action == action)
    after = before_cursor(cursor, AuditEntry.created_at, AuditEntry.id, uuid.UUID)
    if after is not None:
        query = query.where(after)

    rows = (await db.execute(query)).all()
    items = [
        AuditEntryOut(
            audit_id=entry.id,
            actor=UserRef(id=user.id, username=user.username),
            action=entry.action,
            target=entry.target,
            detail=entry.detail or {},
            request_id=entry.request_id,
            created_at=iso(entry.created_at) or "",
        )
        for entry, user in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = encode_cursor(last.created_at, last.id)
    return Page[AuditEntryOut](items=items, next_cursor=next_cursor)
