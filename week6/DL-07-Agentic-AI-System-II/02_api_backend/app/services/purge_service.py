"""Nightly retention job (docs/03_data_design.md 6.1, D-85).

Deletes expired rows table by table, removes expired export files, keeps monthly audit
partitions ahead of time and drops those older than P-24. One run at a time (Redis
claim); every run is audited with the counts only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.ids import current_correlation_id, new_id
from app.core.logging import get_logger
from app.domain.enums import ActorType, AuditResult
from app.domain.retention import add_months, month_start
from app.services.ports import AuditEntry, AuditPort, CooldownPort, ObjectStorePort

log = get_logger(__name__)

BATCH_SIZE = 1000
LOCK_SECONDS = 600
PARTITIONS_AHEAD = 2
_LOCK = "purge"


class RetentionPort(Protocol):
    async def purge_table(self, table: str, *, now: datetime, batch: int) -> int: ...

    async def expired_exports(
        self, *, now: datetime, limit: int, table: str = ...
    ) -> list[tuple[UUID, str | None]]: ...

    async def mark_exports_expired(self, export_ids: list[UUID], *, table: str = ...) -> None: ...

    async def ensure_audit_partition(self, start: datetime) -> bool: ...

    async def drop_audit_partitions(self, *, before: datetime) -> list[str]: ...


@dataclass
class PurgeResult:
    ran: bool
    deleted: dict[str, int] = field(default_factory=dict)
    exports_expired: int = 0
    partitions_created: int = 0
    partitions_dropped: int = 0


class PurgeService:
    def __init__(
        self,
        *,
        retention: RetentionPort,
        tables: tuple[str, ...],
        store: ObjectStorePort | None,
        export_tables: tuple[str, ...] = ("data_exports",),
        audit: AuditPort,
        lock: CooldownPort,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = retention
        self._tables = tables
        self._export_tables = export_tables
        self._store = store
        self._audit = audit
        self._lock = lock
        self._settings = settings
        self._clock = clock

    async def run(self) -> PurgeResult:
        if await self._lock.claim(_LOCK, seconds=LOCK_SECONDS) is not None:
            log.info("purge_already_running")
            return PurgeResult(ran=False)
        try:
            return await self._run()
        finally:
            await self._lock.release(_LOCK)

    async def _run(self) -> PurgeResult:
        now = self._clock.now()
        result = PurgeResult(ran=True)
        for table in self._tables:
            result.deleted[table] = await self._repo.purge_table(table, now=now, batch=BATCH_SIZE)
        for table in self._export_tables:
            result.exports_expired += await self._expire_exports(now, table)

        this_month = month_start(now)
        for offset in range(PARTITIONS_AHEAD + 1):
            if await self._repo.ensure_audit_partition(add_months(this_month, offset)):
                result.partitions_created += 1
        cutoff = now - timedelta(days=self._settings.retention.retention_audit_days)
        result.partitions_dropped = len(await self._repo.drop_audit_partitions(before=cutoff))

        await self._audit.write(
            AuditEntry(
                actor_type=ActorType.SYSTEM,
                actor_ref="purge",
                action="retention.purge",
                target_type=None,
                target_id=None,
                result=AuditResult.SUCCESS,
                correlation_id=current_correlation_id() or str(new_id()),
                ip_hash=None,
                metadata={
                    "deleted": result.deleted,
                    "exports_expired": result.exports_expired,
                    "partitions_created": result.partitions_created,
                    "partitions_dropped": result.partitions_dropped,
                },
            )
        )
        log.info("purge_finished", deleted=sum(result.deleted.values()))
        return result

    async def _expire_exports(self, now: datetime, table: str) -> int:
        expired = await self._repo.expired_exports(now=now, limit=BATCH_SIZE, table=table)
        done: list[UUID] = []
        for export_id, key in expired:
            if key and self._store is not None:
                try:
                    await self._store.delete(key)
                except Exception as exc:  # the next run tries again
                    log.warning("export_file_delete_failed", error_type=type(exc).__name__)
                    continue
            done.append(export_id)
        await self._repo.mark_exports_expired(done, table=table)
        return len(done)
