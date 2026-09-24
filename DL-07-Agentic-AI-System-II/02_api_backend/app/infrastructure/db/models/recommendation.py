"""recommendations (docs/03_data_design.md section 3.6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RecommendationStatus, RecommendationType, RiskLevel
from app.infrastructure.db.base import (
    JSON_DOC,
    Base,
    CreatedAt,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)


class RecommendationModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        check_in("status", "status", RecommendationStatus),
        check_in("risk_level", "risk_level", RiskLevel, nullable=True),
        check_in("recommendation_type", "recommendation_type", RecommendationType, nullable=True),
        CheckConstraint(
            "risk_score IS NULL OR risk_score BETWEEN 0 AND 1", name="risk_score_range"
        ),
        CheckConstraint(
            "risk_confidence IS NULL OR risk_confidence BETWEEN 0 AND 1",
            name="risk_confidence_range",
        ),
        CheckConstraint(
            "status <> 'completed' OR payload IS NOT NULL", name="completed_has_payload"
        ),
        # Safety rule R-04, enforced again at the database level.
        CheckConstraint(
            "NOT (risk_level = 'HIGH' AND recommendation_type = 'TRAVEL_NORMALLY')",
            name="no_travel_normally_on_high_risk",
        ),
        Index(
            "ix_recommendations_user_recent", "user_id", text("created_at DESC"), text("id DESC")
        ),
        Index(
            "ix_recommendations_user_risk",
            "user_id",
            "risk_level",
            text("created_at DESC"),
        ),
        Index(
            "ix_recommendations_processing",
            "status",
            postgresql_where=text("status = 'processing'"),
        ),
        Index(
            "ix_recommendations_trip_recent",
            "trip_id",
            text("created_at DESC"),
            postgresql_where=text("trip_id IS NOT NULL"),
        ),
        Index("ix_recommendations_expires_at", "expires_at"),
    )

    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("travel_requests.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    trip_id: Mapped[UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24))
    risk_level: Mapped[str | None] = mapped_column(String(8))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    risk_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    recommendation_type: Mapped[str | None] = mapped_column(String(24))
    origin_name: Mapped[str | None] = mapped_column(String(200))
    destination_name: Mapped[str | None] = mapped_column(String(200))
    departure_time: Mapped[datetime] = mapped_column(tz_datetime())
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOC)
    warning_codes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    safety_gate_rules: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    overall_is_stale: Mapped[bool | None]
    valid_until: Mapped[datetime | None] = mapped_column(tz_datetime())
    error_code: Mapped[str | None] = mapped_column(String(40))
    api_version: Mapped[str | None] = mapped_column(String(64))
    agent_version: Mapped[str | None] = mapped_column(String(64))
    risk_model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())
