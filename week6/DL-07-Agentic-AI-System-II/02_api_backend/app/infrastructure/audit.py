"""Append-only audit log (docs/03_data_design.md section 3.12, D-70)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models import AuditLogModel
from app.services.ports import AuditEntry

_ACTION_MAX = 64
_TARGET_TYPE_MAX = 32
_CORRELATION_MAX = 64


class SqlAuditWriter:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def write(self, entry: AuditEntry) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                AuditLogModel(
                    actor_type=entry.actor_type.value,
                    actor_ref=entry.actor_ref,
                    action=entry.action[:_ACTION_MAX],
                    target_type=entry.target_type[:_TARGET_TYPE_MAX] if entry.target_type else None,
                    target_id=entry.target_id,
                    result=entry.result.value,
                    correlation_id=entry.correlation_id[:_CORRELATION_MAX],
                    ip_hash=entry.ip_hash,
                    metadata_=entry.metadata,
                )
            )
