"""Retention: delete expired rows and manage monthly audit partitions (data design 6, 6.1).

Rows are deleted in batches so no table is locked for long. Table names come from the
fixed list below, never from input. Partitions are created ahead of time; a month that
already has rows in the default partition is moved into its own partition first.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.retention import add_months, partition_name

# Order from data design 6.1: children before the rows they depend on.
PURGE_ORDER = (
    "recommendations",
    "travel_requests",
    "jobs",
    "conversations",
    "trips",
    "feedback",
    "prediction_records",
)
_PARTITION = re.compile(r"^audit_logs_y(\d{4})m(\d{2})$")
DEFAULT_PARTITION = "audit_logs_default"


# Tables that hold files in object storage (user data exports, training exports).
EXPORT_TABLES = ("data_exports", "training_exports")


def _check_export_table(table: str) -> None:
    if table not in EXPORT_TABLES:
        raise ValueError(f"not an export table: {table}")


class SqlRetentionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def purge_table(self, table: str, *, now: datetime, batch: int) -> int:
        if table not in PURGE_ORDER:
            raise ValueError(f"not a purgeable table: {table}")
        statement = text(
            f"DELETE FROM {table} WHERE id IN "  # noqa: S608 - table is from PURGE_ORDER
            f"(SELECT id FROM {table} WHERE expires_at < :now LIMIT :batch)"
        )
        total = 0
        while True:
            async with self._sessions() as session, session.begin():
                result = await session.execute(statement, {"now": now, "batch": batch})
            deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
            total += deleted
            if deleted < batch:
                return total

    async def expired_exports(
        self, *, now: datetime, limit: int, table: str = "data_exports"
    ) -> list[tuple[UUID, str | None]]:
        _check_export_table(table)
        async with self._sessions() as session:
            rows = await session.execute(
                text(
                    f"SELECT id, object_key FROM {table} "  # noqa: S608 - whitelisted name
                    "WHERE status = 'ready' AND expires_at < :now ORDER BY expires_at LIMIT :limit"
                ),
                {"now": now, "limit": limit},
            )
            return [(row[0], row[1]) for row in rows]

    async def mark_exports_expired(
        self, export_ids: list[UUID], *, table: str = "data_exports"
    ) -> None:
        _check_export_table(table)
        if not export_ids:
            return
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(
                    f"UPDATE {table} SET status = 'expired', object_key = NULL "  # noqa: S608
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": export_ids},
            )

    async def audit_partitions(self) -> list[str]:
        async with self._sessions() as session:
            rows = await session.scalars(
                text(
                    "SELECT child.relname FROM pg_inherits "
                    "JOIN pg_class parent ON parent.oid = pg_inherits.inhparent "
                    "JOIN pg_class child ON child.oid = pg_inherits.inhrelid "
                    "WHERE parent.relname = 'audit_logs' ORDER BY child.relname"
                )
            )
            return list(rows.all())

    async def ensure_audit_partition(self, start: datetime) -> bool:
        """Create the partition of the month starting at `start`; False if it exists."""
        name = partition_name(start)
        if name in await self.audit_partitions():
            return False
        end = add_months(start, 1)
        bounds = {"start": start, "end": end}
        async with self._sessions() as session, session.begin():
            # Serialize with other writers of the partition layout.
            await session.execute(text("LOCK TABLE audit_logs IN SHARE ROW EXCLUSIVE MODE"))
            await session.execute(
                text(
                    f"CREATE TABLE {name} "
                    "(LIKE audit_logs INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
                )
            )
            # Rows of this month already in the default partition move with it.
            await session.execute(
                text(
                    f"INSERT INTO {name} SELECT * FROM {DEFAULT_PARTITION} "  # noqa: S608
                    "WHERE occurred_at >= :start AND occurred_at < :end"
                ),
                bounds,
            )
            await session.execute(
                text(
                    f"DELETE FROM {DEFAULT_PARTITION} "  # noqa: S608
                    "WHERE occurred_at >= :start AND occurred_at < :end"
                ),
                bounds,
            )
            await session.execute(
                text(
                    f"ALTER TABLE audit_logs ATTACH PARTITION {name} "
                    f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                )
            )
        return True

    async def drop_audit_partitions(self, *, before: datetime) -> list[str]:
        """Drop monthly partitions that end on or before `before`; purge old default rows."""
        dropped = []
        for name in await self.audit_partitions():
            match = _PARTITION.match(name)
            if match is None:
                continue
            start = datetime(int(match[1]), int(match[2]), 1, tzinfo=UTC)
            if add_months(start, 1) <= before:
                async with self._sessions() as session, session.begin():
                    await session.execute(text(f"DROP TABLE {name}"))
                dropped.append(name)
        async with self._sessions() as session, session.begin():
            await session.execute(
                text(f"DELETE FROM {DEFAULT_PARTITION} WHERE occurred_at < :before"),  # noqa: S608
                {"before": before},
            )
        return dropped
