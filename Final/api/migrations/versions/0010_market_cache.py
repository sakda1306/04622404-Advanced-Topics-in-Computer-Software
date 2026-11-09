"""job market cache

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "role_cache",
        sa.Column("role_id", sa.String(60), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshing", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.String(40), nullable=True),
        sa.Column("demand", _JSON, nullable=True),
        sa.Column("salary_advertised", _JSON, nullable=True),
    )
    op.create_table(
        "job_postings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role_id", sa.String(60), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("salary_text", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_period", sa.String(10), nullable=True),
        sa.Column("posted_at", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_postings_role_id", "job_postings", ["role_id"])
    op.create_table(
        "refresh_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("role_id", sa.String(60), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_log_day", "refresh_log", ["day"])


def downgrade() -> None:
    op.drop_index("ix_refresh_log_day", table_name="refresh_log")
    op.drop_table("refresh_log")
    op.drop_index("ix_job_postings_role_id", table_name="job_postings")
    op.drop_table("job_postings")
    op.drop_table("role_cache")
