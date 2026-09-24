"""extensions

Revision ID: 0001
Revises:
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # PostGIS is left installed: other extensions (topology, tiger) and other
    # databases objects may depend on it, and dropping it is never needed to roll back.
    pass
