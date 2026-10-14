"""Async engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import SCHEMA


def create_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        # SQLite has no schemas; tests and local runs put the tables in the main database.
        return create_async_engine(
            database_url, execution_options={"schema_translate_map": {SCHEMA: None}}
        )
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
