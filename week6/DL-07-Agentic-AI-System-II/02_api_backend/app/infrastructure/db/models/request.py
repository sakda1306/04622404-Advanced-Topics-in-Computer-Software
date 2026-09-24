"""travel_requests (docs/03_data_design.md section 3.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RequestMode, RequestSource
from app.infrastructure.db.base import (
    JSON_DOC,
    POINT,
    Base,
    CreatedAt,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)


class TravelRequestModel(UUIDPrimaryKey, CreatedAt, Base):
    """A normalized request; `id` is the request_id. The question text lives in messages."""

    __tablename__ = "travel_requests"
    __table_args__ = (
        check_in("source", "source", RequestSource),
        check_in("mode", "mode", RequestMode),
        Index("ix_travel_requests_user_recent", "user_id", text("created_at DESC")),
        Index("ix_travel_requests_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    trip_id: Mapped[UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(24))
    origin: Mapped[Any] = mapped_column(POINT)
    origin_name: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[Any] = mapped_column(POINT)
    destination_name: Mapped[str | None] = mapped_column(String(200))
    waypoints: Mapped[list[Any]] = mapped_column(JSON_DOC, server_default=text("'[]'::jsonb"))
    departure_time: Mapped[datetime] = mapped_column(tz_datetime())
    timezone: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(35))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON_DOC)
    has_question: Mapped[bool]
    mode: Mapped[str] = mapped_column(String(8))
    cache_key: Mapped[str | None] = mapped_column(CHAR(64))
    correlation_id: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())
