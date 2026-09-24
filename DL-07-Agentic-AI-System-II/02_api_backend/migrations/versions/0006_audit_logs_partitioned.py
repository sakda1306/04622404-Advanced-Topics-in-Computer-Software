"""audit_logs (partitioned by month)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("occurred_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_ref", sa.Text(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("ip_hash", sa.CHAR(64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", "occurred_at", name="pk_audit_logs"),
        sa.CheckConstraint(
            "actor_type IN ('user', 'admin', 'system')", name=op.f("ck_audit_logs_actor_type")
        ),
        sa.CheckConstraint(
            "result IN ('success', 'denied', 'error')", name=op.f("ck_audit_logs_result")
        ),
        postgresql_partition_by="RANGE (occurred_at)",
    )
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])
    op.create_index("ix_audit_logs_target", "audit_logs", ["target_type", "target_id"])
    # Catch-all partition; monthly partitions are managed by the maintenance job (step 5.9).
    op.execute("CREATE TABLE audit_logs_default PARTITION OF audit_logs DEFAULT")


def downgrade() -> None:
    op.drop_table("audit_logs")  # drops its partitions as well
