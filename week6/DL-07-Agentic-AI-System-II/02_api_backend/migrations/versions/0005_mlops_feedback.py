"""prediction_records, feedback

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def upgrade() -> None:
    op.create_table(
        "prediction_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("origin_geohash", sa.String(12), nullable=False),
        sa.Column("destination_geohash", sa.String(12), nullable=False),
        sa.Column("region_code", sa.String(10), nullable=True),
        sa.Column("departure_bucket", TZ, nullable=False),
        sa.Column("lead_time_hours", sa.Integer(), nullable=False),
        sa.Column("travel_modes", TEXT_ARRAY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(8), nullable=True),
        sa.Column("risk_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("risk_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("recommendation_type", sa.String(24), nullable=True),
        sa.Column("hazard_types", TEXT_ARRAY, nullable=False),
        sa.Column("data_freshness", postgresql.JSONB(), nullable=False),
        sa.Column("service_status", postgresql.JSONB(), nullable=False),
        sa.Column("safety_gate_rules", TEXT_ARRAY, nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=True),
        sa.Column("risk_model_version", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prediction_records"),
        sa.UniqueConstraint("recommendation_id", name="uq_prediction_records_recommendation_id"),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'partial_result', "
            "'needs_clarification', 'failed', 'cancelled')",
            name=op.f("ck_prediction_records_status"),
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name=op.f("ck_prediction_records_risk_level"),
        ),
        sa.CheckConstraint(
            "recommendation_type IS NULL OR recommendation_type IN "
            "('TRAVEL_NORMALLY', 'CHANGE_ROUTE', 'DELAY_TRAVEL', 'AVOID_TRAVEL')",
            name=op.f("ck_prediction_records_recommendation_type"),
        ),
    )
    op.create_index("ix_prediction_records_created_at", "prediction_records", ["created_at"])
    op.create_index(
        "ix_prediction_records_model_version",
        "prediction_records",
        ["risk_model_version", "created_at"],
    )
    op.create_index("ix_prediction_records_expires_at", "prediction_records", ["expires_at"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("pseudonymous_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("helpful", sa.Boolean(), nullable=True),
        sa.Column("outcome", sa.String(16), server_default=sa.text("'UNKNOWN'"), nullable=False),
        sa.Column("report_type", sa.String(24), nullable=True),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column(
            "review_status",
            sa.String(16),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", TZ, nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.Column(
            "usable_for_training", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
        sa.CheckConstraint(
            "outcome IN ('FOLLOWED', 'IGNORED', 'CHANGED_PLAN', 'UNKNOWN')",
            name=op.f("ck_feedback_outcome"),
        ),
        sa.CheckConstraint(
            "report_type IS NULL OR report_type IN "
            "('UNSAFE_ADVICE', 'INCORRECT_INFO', 'OUTDATED_INFO', 'OTHER')",
            name=op.f("ck_feedback_report_type"),
        ),
        sa.CheckConstraint(
            "review_status IN ('not_required', 'pending', 'approved', 'rejected')",
            name=op.f("ck_feedback_review_status"),
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_feedback_rating_range")
        ),
        sa.CheckConstraint(
            "NOT usable_for_training OR review_status = 'approved'",
            name=op.f("ck_feedback_training_needs_approval"),
        ),
    )
    op.create_index("ix_feedback_recommendation_id", "feedback", ["recommendation_id"])
    op.create_index(
        "ix_feedback_pseudonym_recent",
        "feedback",
        ["pseudonymous_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_feedback_review_queue",
        "feedback",
        ["created_at"],
        postgresql_where=sa.text("review_status = 'pending'"),
    )
    op.create_index("ix_feedback_expires_at", "feedback", ["expires_at"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("prediction_records")
