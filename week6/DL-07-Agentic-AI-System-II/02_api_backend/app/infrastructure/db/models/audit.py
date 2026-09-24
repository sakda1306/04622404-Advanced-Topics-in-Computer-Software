"""audit_logs, append-only and partitioned by month (docs/03_data_design.md section 3.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, Identity, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ActorType, AuditResult
from app.infrastructure.db.base import JSON_DOC, Base, check_in, tz_datetime

# Rows that fall outside every monthly partition land here; the maintenance job
# (step 5.9) creates monthly partitions ahead of time and drops expired ones.
DEFAULT_PARTITION = "audit_logs_default"


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        check_in("actor_type", "actor_type", ActorType),
        check_in("result", "result", AuditResult),
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    # A partitioned table's primary key must include the partition key.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        tz_datetime(), primary_key=True, server_default=text("now()")
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_ref: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(16))
    correlation_id: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str | None] = mapped_column(CHAR(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOC, server_default=text("'{}'::jsonb")
    )
