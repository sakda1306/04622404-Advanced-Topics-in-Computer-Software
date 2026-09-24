"""users

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("oidc_issuer", sa.Text(), nullable=False),
        sa.Column("oidc_subject", sa.Text(), nullable=False),
        sa.Column("pseudonymous_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("language", sa.String(35), server_default=sa.text("'th'"), nullable=False),
        sa.Column(
            "timezone", sa.String(64), server_default=sa.text("'Asia/Bangkok'"), nullable=False
        ),
        sa.Column("home_region", sa.String(10), nullable=True),
        sa.Column(
            "consent_live_alerts", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("consent_live_alerts_at", TZ, nullable=True),
        sa.Column(
            "consent_analytics", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("consent_analytics_at", TZ, nullable=True),
        sa.Column("last_seen_at", TZ, nullable=True),
        sa.Column("deleted_at", TZ, nullable=True),
        sa.Column("created_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_users_oidc_identity"),
        sa.UniqueConstraint("pseudonymous_id", name="uq_users_pseudonymous_id"),
    )


def downgrade() -> None:
    op.drop_table("users")
