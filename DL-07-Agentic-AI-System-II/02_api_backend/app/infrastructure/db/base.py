"""Declarative base, naming convention and shared column helpers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_id

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# WGS84 (EPSG:4326). Spatial indexes are declared explicitly so they follow the
# naming convention instead of geoalchemy2's automatic "idx_" names.
POINT = Geography(geometry_type="POINT", srid=4326, spatial_index=False)
MULTIPOLYGON = Geography(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False)


# Python None must become SQL NULL, not the JSON value null; otherwise NOT NULL and
# "IS NOT NULL" checks silently accept missing documents.
JSON_DOC = JSONB(none_as_null=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id, sort_order=-100)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def tz_datetime() -> DateTime:
    return DateTime(timezone=True)


def check_in(
    name: str, column: str, values: type[StrEnum], *, nullable: bool = False
) -> CheckConstraint:
    """CHECK constraint that limits a text column to the values of an enum."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    condition = f"{column} IN ({allowed})"
    if nullable:
        condition = f"{column} IS NULL OR {condition}"
    return CheckConstraint(condition, name=name)
