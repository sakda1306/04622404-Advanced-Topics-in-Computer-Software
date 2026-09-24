"""Expired rows and audit partitions against PostGIS (data design 6.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.retention import add_months, month_start, partition_name
from app.infrastructure.db.models import (
    AuditLogModel,
    ConversationModel,
    DataExportModel,
    TripModel,
    UserModel,
)
from app.infrastructure.db.repositories.retention import SqlRetentionRepository
from tests.integration import factories

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
def retention(session_factory: async_sessionmaker[AsyncSession]) -> SqlRetentionRepository:
    return SqlRetentionRepository(session_factory)


def audit_row(when: datetime) -> AuditLogModel:
    return AuditLogModel(
        occurred_at=when,
        actor_type="system",
        actor_ref="test",
        action="test.event",
        result="success",
        correlation_id="corr",
    )


def test_month_helpers() -> None:
    start = month_start(datetime(2026, 12, 18, 23, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert add_months(start, 1) == datetime(2027, 1, 1, tzinfo=UTC)
    assert add_months(start, -12) == datetime(2025, 12, 1, tzinfo=UTC)
    assert partition_name(start) == "audit_logs_y2026m12"


async def test_purge_deletes_only_expired_rows_in_batches(
    retention: SqlRetentionRepository, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    owner = factories.user()
    old = [factories.conversation(owner, expires_at=NOW - timedelta(days=1)) for _ in range(5)]
    kept = factories.conversation(owner, expires_at=NOW + timedelta(days=1))
    old_trip = factories.trip(owner, expires_at=NOW - timedelta(minutes=1))
    async with session_factory() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add_all([*old, kept, old_trip])

    deleted = await retention.purge_table("conversations", now=NOW, batch=2)
    trips = await retention.purge_table("trips", now=NOW, batch=1000)

    assert deleted >= 5
    assert trips >= 1
    async with session_factory() as session:
        remaining = await session.scalars(
            select(ConversationModel.id).where(ConversationModel.user_id == owner.id)
        )
        assert list(remaining) == [kept.id]
        assert await session.get(TripModel, old_trip.id) is None
        assert await session.get(UserModel, owner.id) is not None


async def test_only_known_tables_can_be_purged(retention: SqlRetentionRepository) -> None:
    with pytest.raises(ValueError, match="purgeable"):
        await retention.purge_table("users; DROP TABLE users", now=NOW, batch=10)


async def test_expired_exports(
    retention: SqlRetentionRepository, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    owner = factories.user()
    expired = DataExportModel(
        id=new_id(),
        user_id=owner.id,
        status="ready",
        object_key="exports/old.zip",
        completed_at=NOW - timedelta(days=8),
        expires_at=NOW - timedelta(days=1),
    )
    fresh = DataExportModel(
        id=new_id(),
        user_id=owner.id,
        status="ready",
        object_key="exports/new.zip",
        completed_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    async with session_factory() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add_all([expired, fresh])

    found = await retention.expired_exports(now=NOW, limit=100)
    await retention.mark_exports_expired([expired.id])

    assert (expired.id, "exports/old.zip") in found
    assert fresh.id not in {row[0] for row in found}
    async with session_factory() as session:
        row = await session.get(DataExportModel, expired.id)
    assert row is not None
    assert row.status == "expired"
    assert row.object_key is None


async def test_partitions_are_created_and_rows_move(
    retention: SqlRetentionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> None:
    # A month far in the future, so no other test writes into it.
    start = datetime(2031, 3, 1, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        session.add(audit_row(start + timedelta(days=2)))

    assert await retention.ensure_audit_partition(start) is True
    assert await retention.ensure_audit_partition(start) is False

    async with session_factory() as session, session.begin():
        session.add(audit_row(start + timedelta(days=3)))
    async with engine.connect() as conn:
        in_partition = await conn.scalar(
            text(f"SELECT count(*) FROM {partition_name(start)}")  # noqa: S608 - fixed name
        )
        in_default = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs_default "
                "WHERE occurred_at >= :start AND occurred_at < :end"
            ),
            {"start": start, "end": add_months(start, 1)},
        )
    assert in_partition == 2
    assert in_default == 0
    async with session_factory() as session:
        total = await session.scalar(select(func.count()).where(AuditLogModel.occurred_at >= start))
    assert total == 2


async def test_old_partitions_and_default_rows_are_dropped(
    retention: SqlRetentionRepository, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    old = datetime(2020, 1, 1, tzinfo=UTC)
    await retention.ensure_audit_partition(old)
    async with session_factory() as session, session.begin():
        session.add(audit_row(datetime(2019, 6, 1, tzinfo=UTC)))

    dropped = await retention.drop_audit_partitions(before=datetime(2020, 6, 1, tzinfo=UTC))

    assert partition_name(old) in dropped
    assert partition_name(old) not in await retention.audit_partitions()
    async with session_factory() as session:
        leftover = await session.scalar(
            select(func.count()).where(AuditLogModel.occurred_at < datetime(2020, 1, 1, tzinfo=UTC))
        )
    assert leftover == 0


async def test_only_export_tables_can_be_expired(retention: SqlRetentionRepository) -> None:
    with pytest.raises(ValueError, match="not an export table"):
        await retention.expired_exports(now=NOW, limit=1, table="users")
    with pytest.raises(ValueError, match="not an export table"):
        await retention.mark_exports_expired([new_id()], table="users; DROP TABLE users")
