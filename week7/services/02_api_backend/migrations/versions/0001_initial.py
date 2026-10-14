"""Schema `app`: users, chat sessions, messages, feedback, request logs, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("favorite_team_id", sa.Integer()),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", TS),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.CheckConstraint("language IN ('th', 'en')", name="ck_users_language"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        schema=SCHEMA,
    )
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.users.id", name="fk_chat_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_chat_sessions_user_id_updated_at",
        "chat_sessions",
        ["user_id", "updated_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey(
                f"{SCHEMA}.chat_sessions.id", name="fk_messages_session_id_chat_sessions"
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.users.id", name="fk_messages_user_id_users"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.Column("reply_to_id", sa.Uuid()),
        sa.Column("sources", JSON, nullable=False),
        sa.Column("route", sa.String(32)),
        sa.Column("engines_used", JSON),
        sa.Column("confidence", sa.Float()),
        sa.Column("reasoning", sa.Text()),
        sa.Column("trace", JSON),
        sa.Column("token_usage", JSON),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("data_as_of", sa.String(40)),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_messages_session_id_created_at", "messages", ["session_id", "created_at"], schema=SCHEMA
    )
    op.create_index("ix_messages_created_at", "messages", ["created_at"], schema=SCHEMA)
    op.create_table(
        "feedback",
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.messages.id", name="fk_feedback_message_id_messages"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.users.id", name="fk_feedback_user_id_users"),
            nullable=False,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("rating IN (1, -1)", name="ck_feedback_rating"),
        schema=SCHEMA,
    )
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"], schema=SCHEMA)
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.Uuid()),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(32)),
        sa.Column("decided_at_layer", sa.String(16)),
        sa.Column("fallback", sa.String(40)),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"], schema=SCHEMA)
    op.create_index("ix_request_logs_request_id", "request_logs", ["request_id"], schema=SCHEMA)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.users.id", name="fk_audit_log_actor_id_users"),
            nullable=False,
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target", sa.String(120)),
        sa.Column("detail", JSON, nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.Column("created_at", TS, nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], schema=SCHEMA)


def downgrade() -> None:
    for table in ("audit_log", "request_logs", "feedback", "messages", "chat_sessions", "users"):
        op.drop_table(table, schema=SCHEMA)
