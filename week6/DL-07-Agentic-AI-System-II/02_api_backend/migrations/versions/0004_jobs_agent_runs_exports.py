"""data_exports, jobs, agent_runs

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "data_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("completed_at", TZ, nullable=True),
        sa.Column("expires_at", TZ, nullable=True),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_exports"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_data_exports_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'expired')",
            name=op.f("ck_data_exports_status"),
        ),
    )
    op.create_index("ix_data_exports_user_id", "data_exports", ["user_id"])
    op.create_index("ix_data_exports_expires_at", "data_exports", ["expires_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("export_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("stage", sa.String(24), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("progress", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("celery_task_id", sa.String(64), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("cancel_requested_at", TZ, nullable=True),
        sa.Column("started_at", TZ, nullable=True),
        sa.Column("finished_at", TZ, nullable=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_jobs_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name="fk_jobs_recommendation_id_recommendations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["export_id"],
            ["data_exports.id"],
            name="fk_jobs_export_id_data_exports",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "type IN ('RECOMMENDATION', 'MESSAGE', 'TRIP_ASSESSMENT', 'DATA_EXPORT')",
            name=op.f("ck_jobs_type"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_jobs_status"),
        ),
        sa.CheckConstraint(
            "stage IN ('queued', 'fetching_data', 'assessing_risk', 'generating_advice', "
            "'completed', 'failed', 'cancelled')",
            name=op.f("ck_jobs_stage"),
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name=op.f("ck_jobs_progress_range")),
        sa.CheckConstraint(
            "num_nonnulls(recommendation_id, export_id) = 1", name=op.f("ck_jobs_single_target")
        ),
    )
    op.create_index("ix_jobs_user_recent", "jobs", ["user_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_jobs_active",
        "jobs",
        ["created_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index("ix_jobs_expires_at", "jobs", ["expires_at"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tool_calls", sa.SmallInteger(), nullable=True),
        sa.Column("agent_version", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("started_at", TZ, nullable=False),
        sa.Column("finished_at", TZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_agent_runs_job_id_jobs", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("job_id", "attempt", name="uq_agent_runs_job_attempt"),
        sa.CheckConstraint(
            "status IN ('success', 'bad_response', 'timeout', 'error', 'cancelled', "
            "'circuit_open')",
            name=op.f("ck_agent_runs_status"),
        ),
    )
    op.create_index("ix_agent_runs_started_at", "agent_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("jobs")
    op.drop_table("data_exports")
