"""Alembic environment: async engine, schema `app`, version table inside that schema."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.db.models import SCHEMA, Base
from app.db.session import create_engine

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    is_postgres = connection.dialect.name == "postgresql"
    if is_postgres:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=SCHEMA if is_postgres else None,
        compare_type=True,
    )


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_migrations_online())
