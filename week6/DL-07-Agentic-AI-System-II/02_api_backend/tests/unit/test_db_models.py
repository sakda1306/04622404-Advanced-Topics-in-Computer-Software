"""Model metadata rules that do not need a database."""

from __future__ import annotations

import pytest
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB

from app.domain.enums import RiskLevel
from app.infrastructure.db.base import check_in
from app.infrastructure.db.models import Base

TABLES = Base.metadata.tables

# Tables holding user data must expire (docs/03_data_design.md section 6).
EXPIRING_TABLES = {
    "conversations",
    "trips",
    "travel_requests",
    "recommendations",
    "jobs",
    "data_exports",
    "prediction_records",
    "feedback",
}


def test_all_designed_tables_exist() -> None:
    assert set(TABLES) == EXPIRING_TABLES | {
        "users",
        "messages",
        "agent_runs",
        "audit_logs",
        "coverage_areas",
        "emergency_defaults",
        # No user data: the file it points to expires, the row stays as history (D-92).
        "training_exports",
    }


@pytest.mark.parametrize("table", sorted(EXPIRING_TABLES))
def test_user_data_tables_have_expiry_index(table: str) -> None:
    assert "expires_at" in TABLES[table].columns
    indexed = {col.name for index in TABLES[table].indexes for col in index.columns}
    assert "expires_at" in indexed


def test_mlops_tables_do_not_reference_users() -> None:
    for table in ("prediction_records", "feedback"):
        assert "user_id" not in TABLES[table].columns
        assert TABLES[table].foreign_keys == set()


def test_every_json_column_stores_none_as_sql_null() -> None:
    for table in TABLES.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                assert column.type.none_as_null, f"{table.name}.{column.name}"


def test_every_timestamp_is_timezone_aware() -> None:
    for table in TABLES.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone, f"{table.name}.{column.name}"


def test_foreign_keys_to_users_cascade() -> None:
    for table in TABLES.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == "users":
                assert fk.ondelete == "CASCADE", table.name


def test_check_in_builds_enum_condition() -> None:
    required = check_in("risk", "risk_level", RiskLevel)
    optional = check_in("risk", "risk_level", RiskLevel, nullable=True)

    assert str(required.sqltext) == "risk_level IN ('LOW', 'MEDIUM', 'HIGH')"
    assert str(optional.sqltext) == (
        "risk_level IS NULL OR risk_level IN ('LOW', 'MEDIUM', 'HIGH')"
    )
