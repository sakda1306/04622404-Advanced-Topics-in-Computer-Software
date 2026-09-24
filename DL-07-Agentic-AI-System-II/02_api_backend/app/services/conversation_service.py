"""Conversations and follow-up questions (docs/02_api_spec.md section 7.1).

A follow-up is a normal recommendation request: the conversation's last request plus
the overrides, with the message as the question. It goes through RecommendationService,
so validation, the job queue, the Safety Gate and SSE are the same as for E-01.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.logging import get_logger
from app.domain.enums import RequestMode, RequestSource
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.follow_up import RequestOverrides, merge_overrides
from app.domain.normalization import negotiate_language
from app.domain.sanitizer import clean_text, truncate
from app.services.pagination import Cursor, Page, build_page, decode_cursor, page_limit
from app.services.ports import (
    ConversationRecord,
    ConversationRepository,
    MessageRecord,
    UserRef,
)
from app.services.recommendation_service import (
    Accepted,
    CreateRecommendation,
    RecommendationService,
)

log = get_logger(__name__)

TITLE_MAX_CHARS = 200


@dataclass(frozen=True, slots=True)
class MessageReply:
    message: MessageRecord


def _message_field(issue: FieldIssue) -> FieldIssue:
    # Normalization speaks about the travel request; here the user sent a message.
    if issue.field == "question":
        return FieldIssue("content", issue.code, issue.message)
    if issue.field == "overrides":
        return issue
    return FieldIssue(f"overrides.{issue.field}", issue.code, issue.message)


class ConversationService:
    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        recommendations: RecommendationService,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = conversations
        self._recommendations = recommendations
        self._settings = settings
        self._clock = clock

    async def create(
        self,
        user: UserRef,
        *,
        title: str | None,
        language: str | None,
        accept_language: str | None,
    ) -> ConversationRecord:
        cleaned = clean_text(title)
        return await self._repo.create(
            user.id,
            title=truncate(cleaned, TITLE_MAX_CHARS) if cleaned else None,
            language=negotiate_language(language, accept_language),
            now=self._clock.now(),
            retention_days=self._settings.retention.retention_conversation_days,
        )

    async def get(self, user: UserRef, conversation_id: UUID) -> ConversationRecord:
        found = await self._repo.get(user.id, conversation_id)
        if found is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return found

    async def list(
        self, user: UserRef, *, limit: int | None, cursor: str | None
    ) -> Page[ConversationRecord]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.list_conversations(
            user.id, limit=size, cursor=decode_cursor(cursor)
        )
        return build_page(rows, size, key=lambda row: Cursor(row.updated_at, row.id))

    async def delete(self, user: UserRef, conversation_id: UUID) -> None:
        if not await self._repo.delete(user.id, conversation_id):
            raise AppError(ErrorCode.NOT_FOUND)
        log.info("conversation_deleted", conversation_id=str(conversation_id))

    async def messages(
        self, user: UserRef, conversation_id: UUID, *, limit: int | None, cursor: str | None
    ) -> Page[MessageRecord]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.messages(
            user.id, conversation_id, limit=size, cursor=decode_cursor(cursor)
        )
        if rows is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return build_page(rows, size, key=lambda row: Cursor(row.created_at, row.id))

    async def post_message(
        self,
        user: UserRef,
        conversation_id: UUID,
        *,
        content: str,
        overrides: RequestOverrides,
        stream: bool,
        accept_language: str | None,
        correlation_id: str,
    ) -> MessageReply | Accepted:
        conversation = await self.get(user, conversation_id)
        question = clean_text(content)
        if question is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                errors=[FieldError("content", "a message is required", "required")],
            )
        base = await self._repo.last_request(user.id, conversation_id)
        try:
            request = merge_overrides(
                base,
                overrides,
                question=question,
                accept_language=accept_language,
                default_language=conversation.language,
            )
            outcome = await self._recommendations.create(
                user,
                CreateRecommendation(
                    input=request,
                    mode=RequestMode.ASYNC if stream else RequestMode.AUTO,
                    conversation_id=conversation_id,
                    trip_id=None,
                    correlation_id=correlation_id,
                    source=RequestSource.MESSAGE,
                ),
            )
        except InvalidInput as exc:
            raise InvalidInput([_message_field(issue) for issue in exc.issues]) from None
        if isinstance(outcome, Accepted):
            return outcome
        reply = await self._repo.reply_for(user.id, outcome.record.id)
        if reply is None:
            # The conversation was deleted while the job ran, so the reply was not stored.
            if await self._repo.get(user.id, conversation_id) is None:
                raise AppError(ErrorCode.NOT_FOUND)
            # Otherwise every finished job stores a reply (D-55); a missing one is our bug.
            log.error("reply_missing", recommendation_id=str(outcome.record.id))
            raise AppError(ErrorCode.INTERNAL_ERROR)
        return MessageReply(reply)
