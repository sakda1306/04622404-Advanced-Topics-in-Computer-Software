"""recommendations: index for trip assessments (D-71)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_recommendations_trip_recent",
        "recommendations",
        ["trip_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("trip_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_trip_recent", table_name="recommendations")
