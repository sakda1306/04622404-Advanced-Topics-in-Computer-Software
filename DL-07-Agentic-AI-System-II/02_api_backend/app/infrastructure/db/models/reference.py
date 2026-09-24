"""coverage_areas and emergency_defaults (docs/03_data_design.md section 3.13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import JSON_DOC, MULTIPOLYGON, Base, Timestamps, tz_datetime


class CoverageAreaModel(Timestamps, Base):
    __tablename__ = "coverage_areas"
    __table_args__ = (Index("ix_coverage_areas_area", "area", postgresql_using="gist"),)

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    area: Mapped[Any] = mapped_column(MULTIPOLYGON)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    source: Mapped[str] = mapped_column(Text)


class EmergencyDefaultModel(Timestamps, Base):
    __tablename__ = "emergency_defaults"

    region_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    language: Mapped[str] = mapped_column(String(35), primary_key=True)
    instructions: Mapped[dict[str, Any]] = mapped_column(JSON_DOC)
    source: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(tz_datetime())
