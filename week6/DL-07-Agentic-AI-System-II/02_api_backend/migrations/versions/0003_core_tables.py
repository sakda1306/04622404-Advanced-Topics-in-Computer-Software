"""conversations, trips, travel_requests, recommendations, messages

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def point() -> Geography:
    return Geography(geometry_type="POINT", srid=4326, spatial_index=False)


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("last_request_id", sa.Uuid(), nullable=True),
        sa.Column("last_recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversations_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_conversations_user_recent",
        "conversations",
        ["user_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_conversations_expires_at", "conversations", ["expires_at"])

    op.create_table(
        "trips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("origin", point(), nullable=False),
        sa.Column("origin_name", sa.String(200), nullable=True),
        sa.Column("destination", point(), nullable=False),
        sa.Column("destination_name", sa.String(200), nullable=True),
        sa.Column(
            "waypoints",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("departure_time", TZ, nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "preferences",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default=sa.text("'PLANNED'"), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("alerts_consent_at", TZ, nullable=True),
        sa.Column(
            "alert_channels",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{IN_APP}'::text[]"),
            nullable=False,
        ),
        sa.Column("last_recommendation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "assessment_outdated", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_trips"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_trips_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')",
            name=op.f("ck_trips_status"),
        ),
        sa.CheckConstraint(
            "alerts_enabled = false OR alerts_consent_at IS NOT NULL",
            name=op.f("ck_trips_alerts_need_consent"),
        ),
    )
    op.create_index("ix_trips_user_departure", "trips", ["user_id", sa.text("departure_time DESC")])
    op.create_index(
        "ix_trips_alert_schedule",
        "trips",
        ["departure_time"],
        postgresql_where=sa.text("alerts_enabled AND status IN ('PLANNED', 'ACTIVE')"),
    )
    op.create_index("ix_trips_origin", "trips", ["origin"], postgresql_using="gist")
    op.create_index("ix_trips_destination", "trips", ["destination"], postgresql_using="gist")
    op.create_index("ix_trips_expires_at", "trips", ["expires_at"])

    op.create_table(
        "travel_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("trip_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("origin", point(), nullable=False),
        sa.Column("origin_name", sa.String(200), nullable=True),
        sa.Column("destination", point(), nullable=False),
        sa.Column("destination_name", sa.String(200), nullable=True),
        sa.Column(
            "waypoints",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("departure_time", TZ, nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.Column("has_question", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("cache_key", sa.CHAR(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_travel_requests"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_travel_requests_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_travel_requests_conversation_id_conversations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_travel_requests_trip_id_trips",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "source IN ('RECOMMENDATION', 'MESSAGE', 'TRIP_ASSESSMENT', 'TRIP_ALERT')",
            name=op.f("ck_travel_requests_source"),
        ),
        sa.CheckConstraint(
            "mode IN ('auto', 'sync', 'async')", name=op.f("ck_travel_requests_mode")
        ),
    )
    op.create_index(
        "ix_travel_requests_user_recent",
        "travel_requests",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_travel_requests_expires_at", "travel_requests", ["expires_at"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("trip_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(8), nullable=True),
        sa.Column("risk_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("risk_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("recommendation_type", sa.String(24), nullable=True),
        sa.Column("origin_name", sa.String(200), nullable=True),
        sa.Column("destination_name", sa.String(200), nullable=True),
        sa.Column("departure_time", TZ, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "warning_codes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "safety_gate_rules",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("overall_is_stale", sa.Boolean(), nullable=True),
        sa.Column("valid_until", TZ, nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("api_version", sa.String(64), nullable=True),
        sa.Column("agent_version", sa.String(64), nullable=True),
        sa.Column("risk_model_version", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("completed_at", TZ, nullable=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_recommendations"),
        sa.UniqueConstraint("request_id", name="uq_recommendations_request_id"),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["travel_requests.id"],
            name="fk_recommendations_request_id_travel_requests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_recommendations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_recommendations_conversation_id_conversations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_recommendations_trip_id_trips",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'partial_result', "
            "'needs_clarification', 'failed', 'cancelled')",
            name=op.f("ck_recommendations_status"),
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name=op.f("ck_recommendations_risk_level"),
        ),
        sa.CheckConstraint(
            "recommendation_type IS NULL OR recommendation_type IN "
            "('TRAVEL_NORMALLY', 'CHANGE_ROUTE', 'DELAY_TRAVEL', 'AVOID_TRAVEL')",
            name=op.f("ck_recommendations_recommendation_type"),
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR risk_score BETWEEN 0 AND 1",
            name=op.f("ck_recommendations_risk_score_range"),
        ),
        sa.CheckConstraint(
            "risk_confidence IS NULL OR risk_confidence BETWEEN 0 AND 1",
            name=op.f("ck_recommendations_risk_confidence_range"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR payload IS NOT NULL",
            name=op.f("ck_recommendations_completed_has_payload"),
        ),
        sa.CheckConstraint(
            "NOT (risk_level = 'HIGH' AND recommendation_type = 'TRAVEL_NORMALLY')",
            name=op.f("ck_recommendations_no_travel_normally_on_high_risk"),
        ),
    )
    op.create_index(
        "ix_recommendations_user_recent",
        "recommendations",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_recommendations_user_risk",
        "recommendations",
        ["user_id", "risk_level", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_recommendations_processing",
        "recommendations",
        ["status"],
        postgresql_where=sa.text("status = 'processing'"),
    )
    op.create_index("ix_recommendations_expires_at", "recommendations", ["expires_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name="fk_messages_recommendation_id_recommendations",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_messages_role")),
        sa.CheckConstraint("char_length(content) <= 4000", name=op.f("ck_messages_content_length")),
    )
    op.create_index(
        "ix_messages_conversation_recent",
        "messages",
        ["conversation_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    # Foreign keys that close cycles between the tables above.
    op.create_foreign_key(
        "fk_conversations_last_request_id_travel_requests",
        "conversations",
        "travel_requests",
        ["last_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_conversations_last_recommendation_id_recommendations",
        "conversations",
        "recommendations",
        ["last_recommendation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_trips_last_recommendation_id_recommendations",
        "trips",
        "recommendations",
        ["last_recommendation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_trips_last_recommendation_id_recommendations", "trips", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_conversations_last_recommendation_id_recommendations",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_conversations_last_request_id_travel_requests", "conversations", type_="foreignkey"
    )
    op.drop_table("messages")
    op.drop_table("recommendations")
    op.drop_table("travel_requests")
    op.drop_table("trips")
    op.drop_table("conversations")
