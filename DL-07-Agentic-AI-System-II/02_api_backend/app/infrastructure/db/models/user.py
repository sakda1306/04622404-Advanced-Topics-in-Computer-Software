"""users (docs/03_data_design.md section 3.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, Timestamps, UUIDPrimaryKey, tz_datetime


class UserModel(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_users_oidc_identity"),
    )

    oidc_issuer: Mapped[str] = mapped_column(Text)
    oidc_subject: Mapped[str] = mapped_column(Text)
    pseudonymous_id: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(35), server_default=text("'th'"))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'Asia/Bangkok'"))
    home_region: Mapped[str | None] = mapped_column(String(10))
    consent_live_alerts: Mapped[bool] = mapped_column(server_default=text("false"))
    consent_live_alerts_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    consent_analytics: Mapped[bool] = mapped_column(server_default=text("false"))
    consent_analytics_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    last_seen_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    deleted_at: Mapped[datetime | None] = mapped_column(tz_datetime())
