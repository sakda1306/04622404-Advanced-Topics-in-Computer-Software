"""Edge cases of ConversationService that need precise timing (fakes, no database)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.domain.follow_up import RequestOverrides
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.services.conversation_service import ConversationService
from app.services.recommendation_service import CreateRecommendation, Finished
from tests.api.fakes import USER, conversation, record

T0 = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


class DeletedDuringTheJob:
    """The conversation exists when the message arrives; `delete` removes it during the job."""

    def __init__(self, *, delete: bool) -> None:
        self.record = conversation()
        self.delete = delete
        self.deleted = False

    async def get(self, user_id: UUID, conversation_id: UUID) -> Any:
        return None if self.deleted else self.record

    async def last_request(self, user_id: UUID, conversation_id: UUID) -> Any:
        return NormalizedTravelRequest(
            origin=GeoPoint(13.7, 100.5),
            destination=GeoPoint(18.7, 98.9),
            waypoints=(),
            departure_time=T0,
            timezone="Asia/Bangkok",
            language="th",
            preferences=TravelPreferences(),
            question=None,
        )

    async def reply_for(self, user_id: UUID, recommendation_id: UUID) -> Any:
        return None


class FinishingRecommendations:
    def __init__(self, conversations: DeletedDuringTheJob) -> None:
        self.conversations = conversations

    async def create(self, user: Any, command: CreateRecommendation) -> Finished:
        self.conversations.deleted = self.conversations.delete
        return Finished(record(conversation_id=None))


@pytest.mark.parametrize("deleted", [True, False])
async def test_missing_reply(settings: Settings, deleted: bool) -> None:
    conversations = DeletedDuringTheJob(delete=deleted)
    recommendations = FinishingRecommendations(conversations)
    service = ConversationService(
        conversations=conversations,  # type: ignore[arg-type]
        recommendations=recommendations,  # type: ignore[arg-type]
        settings=settings,
        clock=SystemClock(),
    )

    with pytest.raises(AppError) as info:
        await service.post_message(
            USER,
            new_id(),
            content="Safe?",
            overrides=RequestOverrides(),
            stream=False,
            accept_language=None,
            correlation_id="c",
        )

    expected = ErrorCode.NOT_FOUND if deleted else ErrorCode.INTERNAL_ERROR
    assert info.value.code is expected
