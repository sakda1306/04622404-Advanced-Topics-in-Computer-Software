"""training_exports and an index for the admin job listing (D-92, D-93)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "training_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("range_from", TZ, nullable=False),
        sa.Column("range_to", TZ, nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("completed_at", TZ, nullable=True),
        sa.Column("expires_at", TZ, nullable=True),
        sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_training_exports"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'expired')",
            name=op.f("ck_training_exports_status"),
        ),
        sa.CheckConstraint("range_from < range_to", name=op.f("ck_training_exports_range_order")),
    )
    op.create_index("ix_training_exports_created_at", "training_exports", ["created_at"])
    op.create_index("ix_training_exports_expires_at", "training_exports", ["expires_at"])
    op.create_index("ix_jobs_recent", "jobs", [sa.text("created_at DESC"), sa.text("id DESC")])


def downgrade() -> None:
    op.drop_index("ix_jobs_recent", table_name="jobs")
    op.drop_table("training_exports")
