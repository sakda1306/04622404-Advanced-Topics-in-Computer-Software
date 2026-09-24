"""trips (docs/03_data_design.md section 3.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import TripStatus
from app.infrastructure.db.base import (
    JSON_DOC,
    POINT,
    Base,
    Timestamps,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)


class TripModel(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "trips"
    __table_args__ = (
        check_in("status", "status", TripStatus),
        CheckConstraint(
            "alerts_enabled = false OR alerts_consent_at IS NOT NULL", name="alerts_need_consent"
        ),
        Index("ix_trips_user_departure", "user_id", text("departure_time DESC")),
        Index(
            "ix_trips_alert_schedule",
            "departure_time",
            postgresql_where=text("alerts_enabled AND status IN ('PLANNED', 'ACTIVE')"),
        ),
        Index("ix_trips_origin", "origin", postgresql_using="gist"),
        Index("ix_trips_destination", "destination", postgresql_using="gist"),
        Index("ix_trips_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    origin: Mapped[Any] = mapped_column(POINT)
    origin_name: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[Any] = mapped_column(POINT)
    destination_name: Mapped[str | None] = mapped_column(String(200))
    waypoints: Mapped[list[Any]] = mapped_column(JSON_DOC, server_default=text("'[]'::jsonb"))
    departure_time: Mapped[datetime] = mapped_column(tz_datetime())
    timezone: Mapped[str] = mapped_column(String(64))
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOC, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PLANNED'"))
    alerts_enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    alerts_consent_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    alert_channels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{IN_APP}'::text[]")
    )
    last_recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL", use_alter=True)
    )
    assessment_outdated: Mapped[bool] = mapped_column(server_default=text("false"))
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())
