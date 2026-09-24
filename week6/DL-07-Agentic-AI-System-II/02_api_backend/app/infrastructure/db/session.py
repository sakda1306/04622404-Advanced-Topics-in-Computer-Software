"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import DatabaseSettings
from app.core.telemetry import instrument_engine


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        # Exception messages are logged; bound values may be questions or exact locations.
        hide_parameters=True,
        # Every timestamp is stored and compared in UTC.
        connect_args={"server_settings": {"timezone": "UTC", "application_name": "tsa-api"}},
    )
    instrument_engine(engine)  # no-op unless tracing is on
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session that commits on success and rolls back on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
