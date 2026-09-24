"""conversations and messages (docs/03_data_design.md sections 3.2-3.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import MessageRole
from app.infrastructure.db.base import (
    Base,
    CreatedAt,
    Timestamps,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)
from app.infrastructure.db.types import EncryptedText


class ConversationModel(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_recent", "user_id", text("updated_at DESC"), text("id DESC")),
        Index("ix_conversations_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(35))
    # Both FKs close a cycle with travel_requests/recommendations, so they are added
    # after all three tables exist.
    last_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("travel_requests.id", ondelete="SET NULL", use_alter=True)
    )
    last_recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL", use_alter=True)
    )
    message_count: Mapped[int] = mapped_column(server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())


class MessageModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "messages"
    __table_args__ = (
        check_in("role", "role", MessageRole),
        Index(
            "ix_messages_conversation_recent",
            "conversation_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    # Encrypted (D-81); the 4,000-character limit is enforced by the application.
    content: Mapped[str] = mapped_column(EncryptedText("messages.content"))
    recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL")
    )
