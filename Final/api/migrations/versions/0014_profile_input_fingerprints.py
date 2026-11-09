"""input hashes at generation, to tell the user which inputs changed since

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column("profiles", sa.Column("input_fingerprints", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "input_fingerprints")
