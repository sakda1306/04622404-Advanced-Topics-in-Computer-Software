"""Migrations: upgrade/downgrade work and the result matches the ORM models."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.db.migration_filters import include_object
from app.infrastructure.db.models import Base
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

APP_TABLES = set(Base.metadata.tables)


def _run(url: str, fn: Any) -> Any:
    async def _inner() -> Any:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _public_tables(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).scalars()
    return set(rows)


def _current_revision(conn: Connection) -> str | None:
    return MigrationContext.configure(conn).get_current_revision()


def _schema_diff(conn: Connection) -> list[Any]:
    context = MigrationContext.configure(
        conn,
        opts={
            "include_object": include_object,
            "compare_type": True,
            "compare_server_default": True,
        },
    )
    return list(compare_metadata(context, Base.metadata))


def test_revisions_form_a_single_linear_chain() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+asyncpg://unused"))
    revisions = [rev.revision for rev in script.walk_revisions("base", "heads")]

    assert script.get_heads() == ["0010"]
    assert sorted(revisions) == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
    ]


def test_upgrade_head_creates_every_model_table(empty_db_url: str) -> None:
    command.upgrade(alembic_config(empty_db_url), "head")

    tables = _run(empty_db_url, _public_tables)
    assert tables >= APP_TABLES
    assert "audit_logs_default" in tables
    assert _run(empty_db_url, _current_revision) == "0010"


def test_models_match_migrations(empty_db_url: str) -> None:
    command.upgrade(alembic_config(empty_db_url), "head")

    diff = _run(empty_db_url, _schema_diff)

    assert diff == []


def _db_object_names(conn: Connection) -> tuple[set[str], set[str]]:
    constraints = conn.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = 'public' AND t.relname = ANY(:tables) AND c.contype <> 'n'"
        ),
        {"tables": sorted(APP_TABLES)},
    ).scalars()
    indexes = conn.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = ANY(:tables)"
        ),
        {"tables": sorted(APP_TABLES)},
    ).scalars()
    return set(constraints), set(indexes)


def _model_object_names() -> tuple[set[str], set[str]]:
    constraints: set[str] = set()
    indexes: set[str] = set()
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            assert isinstance(constraint.name, str), f"unnamed constraint on {table.name}"
            constraints.add(constraint.name)
        for column in table.columns:
            if column.unique:
                constraints.add(f"uq_{table.name}_{column.name}")
        for index in table.indexes:
            assert isinstance(index.name, str)
            indexes.add(index.name)
    return constraints, indexes


def test_constraint_and_index_names_match_models(empty_db_url: str) -> None:
    # Autogenerate does not compare CHECK constraints, so compare every name directly.
    command.upgrade(alembic_config(empty_db_url), "head")

    db_constraints, db_indexes = _run(empty_db_url, _db_object_names)
    model_constraints, model_indexes = _model_object_names()

    assert db_constraints == model_constraints
    # Primary keys and unique constraints are backed by indexes of the same name.
    assert db_indexes - db_constraints == model_indexes


def test_downgrade_to_base_and_upgrade_again(empty_db_url: str) -> None:
    config = alembic_config(empty_db_url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")
    assert _run(empty_db_url, _public_tables) & APP_TABLES == set()
    assert _run(empty_db_url, _current_revision) is None

    command.upgrade(config, "head")
    assert _run(empty_db_url, _public_tables) >= APP_TABLES


def test_each_revision_can_be_rolled_back(empty_db_url: str) -> None:
    config = alembic_config(empty_db_url)
    command.downgrade(config, "base")
    script = ScriptDirectory.from_config(config)
    revisions = [rev.revision for rev in reversed(list(script.walk_revisions("base", "heads")))]

    for revision in revisions:
        command.upgrade(config, revision)
        command.downgrade(config, "-1")
        command.upgrade(config, revision)

    assert _run(empty_db_url, _current_revision) == "0010"


def test_offline_sql_can_be_generated(capsys: pytest.CaptureFixture[str]) -> None:
    command.upgrade(alembic_config("postgresql+asyncpg://u:p@h/db"), "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql
    assert "PARTITION BY RANGE (occurred_at)" in sql
    assert "ck_recommendations_no_travel_normally_on_high_risk" in sql
