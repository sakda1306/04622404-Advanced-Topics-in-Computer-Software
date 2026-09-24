"""prediction_records, feedback and training_exports (docs/03_data_design.md 3.9-3.10, 3.14).

Neither table links to users or has a foreign key to recommendations, so the rows can
outlive the personal data they were derived from.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    ExportStatus,
    FeedbackOutcome,
    RecommendationStatus,
    RecommendationType,
    ReportType,
    ReviewStatus,
    RiskLevel,
)
from app.infrastructure.db.base import (
    JSON_DOC,
    Base,
    CreatedAt,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)
from app.infrastructure.db.types import EncryptedText


class PredictionRecordModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "prediction_records"
    __table_args__ = (
        check_in("status", "status", RecommendationStatus),
        check_in("risk_level", "risk_level", RiskLevel, nullable=True),
        check_in("recommendation_type", "recommendation_type", RecommendationType, nullable=True),
        Index("ix_prediction_records_created_at", "created_at"),
        Index("ix_prediction_records_model_version", "risk_model_version", "created_at"),
        Index("ix_prediction_records_expires_at", "expires_at"),
    )

    recommendation_id: Mapped[UUID] = mapped_column(unique=True)
    origin_geohash: Mapped[str] = mapped_column(String(12))
    destination_geohash: Mapped[str] = mapped_column(String(12))
    region_code: Mapped[str | None] = mapped_column(String(10))
    departure_bucket: Mapped[datetime] = mapped_column(tz_datetime())
    lead_time_hours: Mapped[int] = mapped_column(Integer)
    travel_modes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(String(24))
    risk_level: Mapped[str | None] = mapped_column(String(8))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    risk_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    recommendation_type: Mapped[str | None] = mapped_column(String(24))
    hazard_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    data_freshness: Mapped[dict[str, Any]] = mapped_column(JSON_DOC)
    service_status: Mapped[dict[str, Any]] = mapped_column(JSON_DOC)
    safety_gate_rules: Mapped[list[str]] = mapped_column(ARRAY(Text))
    agent_version: Mapped[str | None] = mapped_column(String(64))
    risk_model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())


class FeedbackModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        check_in("outcome", "outcome", FeedbackOutcome),
        check_in("report_type", "report_type", ReportType, nullable=True),
        check_in("review_status", "review_status", ReviewStatus),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint(
            "NOT usable_for_training OR review_status = 'approved'",
            name="training_needs_approval",
        ),
        Index("ix_feedback_recommendation_id", "recommendation_id"),
        Index("ix_feedback_pseudonym_recent", "pseudonymous_id", text("created_at DESC")),
        Index(
            "ix_feedback_review_queue",
            "created_at",
            postgresql_where=text("review_status = 'pending'"),
        ),
        Index("ix_feedback_expires_at", "expires_at"),
    )

    recommendation_id: Mapped[UUID]
    pseudonymous_id: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    helpful: Mapped[bool | None]
    outcome: Mapped[str] = mapped_column(String(16), server_default=text("'UNKNOWN'"))
    report_type: Mapped[str | None] = mapped_column(String(24))
    # Encrypted (D-81); the 1,000-character limit is enforced by the application.
    comment: Mapped[str | None] = mapped_column(EncryptedText("feedback.comment"))
    review_status: Mapped[str] = mapped_column(String(16), server_default=text("'not_required'"))
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    review_note: Mapped[str | None] = mapped_column(String(1000))
    usable_for_training: Mapped[bool] = mapped_column(server_default=text("false"))
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())


class TrainingExportModel(UUIDPrimaryKey, CreatedAt, Base):
    """An anonymized training data file requested by an admin (D-92). No user link."""

    __tablename__ = "training_exports"
    __table_args__ = (
        check_in("status", "status", ExportStatus),
        CheckConstraint("range_from < range_to", name="range_order"),
        Index("ix_training_exports_created_at", "created_at"),
        Index("ix_training_exports_expires_at", "expires_at"),
    )

    requested_by: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    range_from: Mapped[datetime] = mapped_column(tz_datetime())
    range_to: Mapped[datetime] = mapped_column(tz_datetime())
    row_count: Mapped[int | None] = mapped_column(Integer)
    object_key: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    expires_at: Mapped[datetime | None] = mapped_column(tz_datetime())
