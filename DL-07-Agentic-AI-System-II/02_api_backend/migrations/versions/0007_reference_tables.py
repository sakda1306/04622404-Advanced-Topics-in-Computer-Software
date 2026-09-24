"""coverage_areas, emergency_defaults

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "coverage_areas",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "area",
            Geography(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_coverage_areas"),
    )
    op.create_index("ix_coverage_areas_area", "coverage_areas", ["area"], postgresql_using="gist")

    op.create_table(
        "emergency_defaults",
        sa.Column("region_code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("instructions", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("verified_at", TZ, nullable=True),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("region_code", "language", name="pk_emergency_defaults"),
    )


def downgrade() -> None:
    op.drop_table("emergency_defaults")
    op.drop_table("coverage_areas")
