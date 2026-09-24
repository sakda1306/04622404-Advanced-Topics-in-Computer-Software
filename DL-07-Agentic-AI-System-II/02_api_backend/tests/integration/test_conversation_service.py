"""Conversation use cases, including follow-up questions through the real worker path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.enums import JobType, MessageRole, RecommendationStatus, RiskLevel
from app.domain.errors import InvalidInput
from app.domain.follow_up import PreferenceOverrides, RequestOverrides
from app.domain.normalization import GeoPoint
from app.services.conversation_service import ConversationService, MessageReply
from app.services.ports import UserRef
from app.services.recommendation_service import Accepted
from tests.integration.flow import Flow

pytestmark = pytest.mark.integration

BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")


def departure(hours: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(days=2, hours=hours)


def trip(**changes: object) -> RequestOverrides:
    values: dict[str, object] = {
        "origin": BANGKOK,
        "destination": CHIANG_MAI,
        "departure_time": departure(),
        "timezone": "Asia/Bangkok",
    }
    values.update(changes)
    return RequestOverrides(**values)  # type: ignore[arg-type]


async def ask(
    service: ConversationService,
    user: UserRef,
    conversation_id: object,
    content: str,
    overrides: RequestOverrides | None = None,
    *,
    stream: bool = False,
) -> MessageReply | Accepted:
    return await service.post_message(
        user,
        conversation_id,  # type: ignore[arg-type]
        content=content,
        overrides=overrides or RequestOverrides(),
        stream=stream,
        accept_language=None,
        correlation_id="corr-conv",
    )


async def test_create_uses_clean_title_and_language(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()

    created = await service.create(
        user, title="  เที่ยว\x07เชียงใหม่  ", language=None, accept_language="en-US"
    )
    untitled = await service.create(user, title="   ", language="th", accept_language=None)
    long = await service.create(user, title="x" * 300, language="xx", accept_language=None)

    assert (created.title, created.language) == ("เที่ยวเชียงใหม่", "en")
    assert untitled.title is None
    assert long.title is not None
    assert len(long.title) == 200
    assert long.language == "th"
    assert await service.get(user, created.id) == created


async def test_first_message_and_follow_up(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)

    first = await ask(service, user, conversation.id, "Is it safe?", trip())
    later = departure(hours=3)
    second = await ask(
        service,
        user,
        conversation.id,
        "  And three hours later?  ",
        RequestOverrides(departure_time=later),
    )

    assert isinstance(first, MessageReply)
    assert first.message.role is MessageRole.ASSISTANT
    assert first.message.content == "Conditions are safe for your trip."
    assert isinstance(second, MessageReply)
    body = flow.agent_state.runs[-1]["body"]
    assert body["request"]["origin"]["name"] == "Bangkok"
    assert body["request"]["destination"]["name"] == "Chiang Mai"
    assert body["request"]["question"] == "And three hours later?"
    sent = datetime.fromisoformat(body["request"]["departure_time"])
    assert abs(sent - later) < timedelta(seconds=1)
    assert body["intent_hint"] == "FOLLOW_UP"
    assert [m["content"] for m in body["context"]["messages"]] == [
        "Is it safe?",
        "Conditions are safe for your trip.",
    ]
    assert second.message.recommendation_id is not None
    record = await flow.repo.get_recommendation(user.id, second.message.recommendation_id)
    assert record is not None
    assert record.status is RecommendationStatus.COMPLETED
    page = await service.messages(user, conversation.id, limit=None, cursor=None)
    assert [m.role for m in page.items] == [
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert page.next_cursor is None
    refreshed = await service.get(user, conversation.id)
    assert refreshed.message_count == 4
    assert refreshed.last_recommendation_id == second.message.recommendation_id


async def test_follow_up_is_a_message_job_and_never_cached(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)
    await ask(service, user, conversation.id, "Safe?", trip())
    runs = len(flow.agent_state.runs)

    accepted = await ask(service, user, conversation.id, "Safe?", stream=True)

    assert isinstance(accepted, Accepted)
    await flow.queue.drain()
    job = await flow.repo.get_job(user.id, accepted.job_id)
    assert job is not None
    assert job.type is JobType.MESSAGE
    assert len(flow.agent_state.runs) == runs + 1


async def test_preferences_override_is_merged(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)
    await ask(service, user, conversation.id, "Safe?", trip())

    await ask(
        service,
        user,
        conversation.id,
        "With four people?",
        RequestOverrides(preferences=PreferenceOverrides(traveler_count=4)),
    )

    preferences = flow.agent_state.runs[-1]["body"]["request"]["preferences"]
    assert preferences["traveler_count"] == 4


async def test_empty_conversation_needs_a_trip(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)

    with pytest.raises(InvalidInput) as info:
        await ask(
            service, user, conversation.id, "Is it safe?", RequestOverrides(destination=CHIANG_MAI)
        )

    assert [i.field for i in info.value.issues] == ["overrides"]
    assert flow.queue.enqueued == []


async def test_input_errors_name_the_message_fields(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)
    await ask(service, user, conversation.id, "Safe?", trip())

    with pytest.raises(AppError) as blank:
        await ask(service, user, conversation.id, " \x07 ")
    with pytest.raises(InvalidInput) as invalid:
        await ask(
            service,
            user,
            conversation.id,
            "x" * 1001,
            RequestOverrides(timezone="Mars/Olympus"),
        )

    assert blank.value.code is ErrorCode.VALIDATION_ERROR
    assert [e.field for e in blank.value.errors or []] == ["content"]
    assert sorted(i.field for i in invalid.value.issues) == ["content", "overrides.timezone"]


async def test_other_users_conversation_is_not_found(flow: Flow) -> None:
    owner, intruder = await flow.user(), await flow.user()
    service = flow.conversations()
    conversation = await service.create(owner, title=None, language="en", accept_language=None)

    calls = [
        service.get(intruder, conversation.id),
        service.messages(intruder, conversation.id, limit=None, cursor=None),
        ask(service, intruder, conversation.id, "Safe?", trip()),
        service.delete(intruder, conversation.id),
    ]
    for call in calls:
        with pytest.raises(AppError) as info:
            await call
        assert info.value.code is ErrorCode.NOT_FOUND
    assert await service.get(owner, conversation.id) == conversation


async def test_delete_keeps_the_recommendation(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)
    reply = await ask(service, user, conversation.id, "Safe?", trip())
    assert isinstance(reply, MessageReply)
    assert reply.message.recommendation_id is not None

    await service.delete(user, conversation.id)

    with pytest.raises(AppError):
        await service.get(user, conversation.id)
    record = await flow.recommendations().get(user, reply.message.recommendation_id)
    assert record.conversation_id is None


async def test_conversation_list_pages(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()
    for n in range(3):
        await service.create(user, title=f"c{n}", language="en", accept_language=None)

    first = await service.list(user, limit=2, cursor=None)
    second = await service.list(user, limit=2, cursor=first.next_cursor)

    assert [c.title for c in first.items] == ["c2", "c1"]
    assert [c.title for c in second.items] == ["c0"]
    assert second.next_cursor is None


async def test_bad_page_arguments(flow: Flow) -> None:
    user = await flow.user()
    service = flow.conversations()

    with pytest.raises(AppError) as info:
        await service.list(user, limit=500, cursor=None)
    with pytest.raises(AppError) as cursor:
        await service.list(user, limit=None, cursor="nope")

    assert [e.field for e in info.value.errors or []] == ["limit"]
    assert [e.field for e in cursor.value.errors or []] == ["cursor"]


async def test_recommendation_history(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    recommendations = flow.recommendations()
    service = flow.conversations()
    conversation = await service.create(user, title=None, language="en", accept_language=None)
    await ask(service, user, conversation.id, "Safe?", trip())
    flow.agent_state.scenario = "high_risk"
    await ask(service, user, conversation.id, "And now?")

    everything = await recommendations.list(
        user, limit=None, cursor=None, created_from=None, created_to=None, risk_level=None
    )
    high = await recommendations.list(
        user,
        limit=None,
        cursor=None,
        created_from=None,
        created_to=None,
        risk_level=RiskLevel.HIGH,
    )
    paged = await recommendations.list(
        user, limit=1, cursor=None, created_from=None, created_to=None, risk_level=None
    )
    nothing = await recommendations.list(
        other, limit=None, cursor=None, created_from=None, created_to=None, risk_level=None
    )

    assert [s.risk_level for s in everything.items] == [RiskLevel.HIGH, RiskLevel.LOW]
    assert len(high.items) == 1
    assert paged.next_cursor is not None
    assert nothing.items == []
