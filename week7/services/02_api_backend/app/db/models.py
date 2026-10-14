"""Tables in schema `app` (User Data / Context + Response / Log)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_id

SCHEMA = "app"

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


def _now_default() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint("language IN ('th', 'en')", name="ck_users_language"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    favorite_team_id: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="th")
    created_at: Mapped[datetime] = _now_default()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index(None, "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = _now_default()
    updated_at: Mapped[datetime] = _now_default()


class Message(Base):
    """One row per chat turn side; answer metadata lives on the assistant row."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        Index(None, "session_id", "created_at"),
        Index(None, "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    # The user message this answer replies to (assistant rows only).
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    sources: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    route: Mapped[str | None] = mapped_column(String(32))
    engines_used: Mapped[list[Any] | None] = mapped_column(JsonType)
    confidence: Mapped[float | None]
    reasoning: Mapped[str | None] = mapped_column(Text)
    trace: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    data_as_of: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating IN (1, -1)", name="ck_feedback_rating"),
        Index(None, "created_at"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RequestLog(Base):
    """One row per /api/chat call, failed ones included (LogItem in CONTRACT §1.1)."""

    __tablename__ = "request_logs"
    __table_args__ = (Index(None, "created_at"), Index(None, "request_id"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    route: Mapped[str | None] = mapped_column(String(32))
    decided_at_layer: Mapped[str | None] = mapped_column(String(16))
    fallback: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index(None, "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[str | None] = mapped_column(String(120))
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
