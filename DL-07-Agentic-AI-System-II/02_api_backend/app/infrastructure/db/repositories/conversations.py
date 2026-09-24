"""Conversations and messages (docs/03_data_design.md sections 3.2-3.3).

Every query is scoped to the owner. Deleting a conversation removes its messages
(cascade) and unlinks its requests and recommendations (SET NULL).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import MessageRole
from app.domain.normalization import NormalizedTravelRequest
from app.domain.retention import expires_at
from app.infrastructure.db.models import ConversationModel, MessageModel, RecommendationModel
from app.infrastructure.db.repositories.requests import load_request
from app.services.pagination import Cursor
from app.services.ports import ConversationRecord, MessageRecord


def _conversation(row: ConversationModel) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        language=row.language,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_recommendation_id=row.last_recommendation_id,
        message_count=row.message_count,
    )


def _message(row: MessageModel) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        recommendation_id=row.recommendation_id,
        created_at=row.created_at,
    )


class SqlConversationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _owned(
        self, session: AsyncSession, user_id: UUID, conversation_id: UUID
    ) -> ConversationModel | None:
        row: ConversationModel | None = await session.scalar(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id, ConversationModel.user_id == user_id
            )
        )
        return row

    async def create(
        self,
        user_id: UUID,
        *,
        title: str | None,
        language: str,
        now: datetime,
        retention_days: int,
    ) -> ConversationRecord:
        row = ConversationModel(
            id=new_id(),
            user_id=user_id,
            title=title,
            language=language,
            message_count=0,
            created_at=now,
            updated_at=now,
            expires_at=expires_at(now, retention_days),
        )
        async with self._sessions() as session, session.begin():
            session.add(row)
        return _conversation(row)

    async def get(self, user_id: UUID, conversation_id: UUID) -> ConversationRecord | None:
        async with self._sessions() as session:
            row = await self._owned(session, user_id, conversation_id)
            return _conversation(row) if row is not None else None

    async def list_conversations(
        self, user_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[ConversationRecord]:
        model = ConversationModel
        query = select(model).where(model.user_id == user_id)
        if cursor is not None:
            query = query.where(tuple_(model.updated_at, model.id) < (cursor.at, cursor.id))
        query = query.order_by(model.updated_at.desc(), model.id.desc()).limit(limit + 1)
        async with self._sessions() as session:
            return [_conversation(row) for row in (await session.scalars(query)).all()]

    async def delete(self, user_id: UUID, conversation_id: UUID) -> bool:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                delete(ConversationModel)
                .where(
                    ConversationModel.id == conversation_id,
                    ConversationModel.user_id == user_id,
                )
                .returning(ConversationModel.id)
            )
            return result.scalar_one_or_none() is not None

    async def messages(
        self, user_id: UUID, conversation_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[MessageRecord] | None:
        model = MessageModel
        async with self._sessions() as session:
            if await self._owned(session, user_id, conversation_id) is None:
                return None
            query = select(model).where(model.conversation_id == conversation_id)
            if cursor is not None:
                query = query.where(tuple_(model.created_at, model.id) < (cursor.at, cursor.id))
            query = query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
            return [_message(row) for row in (await session.scalars(query)).all()]

    async def last_request(
        self, user_id: UUID, conversation_id: UUID
    ) -> NormalizedTravelRequest | None:
        async with self._sessions() as session:
            conversation = await self._owned(session, user_id, conversation_id)
            if conversation is None or conversation.last_request_id is None:
                return None
            request, _ = await load_request(session, conversation.last_request_id, question=None)
            return request

    async def reply_for(self, user_id: UUID, recommendation_id: UUID) -> MessageRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(MessageModel)
                .join(RecommendationModel, RecommendationModel.id == MessageModel.recommendation_id)
                .where(
                    MessageModel.recommendation_id == recommendation_id,
                    MessageModel.role == MessageRole.ASSISTANT.value,
                    RecommendationModel.user_id == user_id,
                )
                .order_by(MessageModel.created_at.desc())
                .limit(1)
            )
            return _message(row) if row is not None else None
