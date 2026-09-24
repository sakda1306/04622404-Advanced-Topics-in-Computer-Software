"""API contract for conversations and messages (docs/02_api_spec.md section 7.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MessageRole
from app.schemas.v1.travel import TravelOverrides
from app.services.ports import ConversationRecord, MessageRecord


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationCreate(_Strict):
    # Hard caps for parsing; the title is cleaned and shortened to 200 characters.
    title: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=35)


class ConversationResponse(_Strict):
    conversation_id: UUID
    title: str | None
    language: str
    created_at: datetime
    updated_at: datetime
    last_recommendation_id: UUID | None
    message_count: int

    @classmethod
    def from_record(cls, record: ConversationRecord) -> ConversationResponse:
        return cls(
            conversation_id=record.id,
            title=record.title,
            language=record.language,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_recommendation_id=record.last_recommendation_id,
            message_count=record.message_count,
        )


class ConversationPage(_Strict):
    items: list[ConversationResponse]
    next_cursor: str | None


class MessageCreate(_Strict):
    # The business limit (P-41) is checked after cleaning; this only bounds parsing.
    content: str = Field(max_length=20_000)
    overrides: TravelOverrides = Field(default_factory=TravelOverrides)
    stream: bool = False


class MessageResponse(_Strict):
    message_id: UUID
    role: MessageRole
    content: str
    recommendation_id: UUID | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: MessageRecord) -> MessageResponse:
        return cls(
            message_id=record.id,
            role=record.role,
            content=record.content,
            recommendation_id=record.recommendation_id,
            created_at=record.created_at,
        )


class MessagePage(_Strict):
    items: list[MessageResponse]
    next_cursor: str | None
