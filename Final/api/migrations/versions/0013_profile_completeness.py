"""completeness when the profile was generated, for the admin funnel

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("completeness_at_generate", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "completeness_at_generate")
