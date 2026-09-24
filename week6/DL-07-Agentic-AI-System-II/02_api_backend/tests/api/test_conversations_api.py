"""HTTP contract of /v1/conversations (services are faked)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_conversation_service, get_current_user
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.ids import new_id
from app.domain.enums import AvoidOption, MessageRole
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.follow_up import RequestOverrides
from app.main import create_app
from app.services.conversation_service import MessageReply
from app.services.pagination import Page
from app.services.recommendation_service import Accepted
from tests.api.fakes import USER, FakeConversations, conversation, message
from tests.support.auth import TokenFactory

URL = "/v1/conversations"


@pytest.fixture
def fake() -> FakeConversations:
    return FakeConversations()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeConversations) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_conversation_service] = lambda: fake
    return application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post_headers(token: str, key: str | None = None) -> dict[str, str]:
    return {**bearer(token), "Idempotency-Key": key or str(uuid4())}


def owned(fake: FakeConversations) -> str:
    record = conversation()
    fake.records[record.id] = record
    return str(record.id)


async def test_create_conversation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    response = await client.post(
        URL,
        json={"title": "Trip north", "language": "en"},
        headers={**post_headers(make_token()), "Accept-Language": "th"},
    )

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"/v1/conversations/{body['conversation_id']}"
    assert body == {
        "conversation_id": body["conversation_id"],
        "title": "Trip north",
        "language": "en",
        "created_at": "2026-09-17T08:00:00Z",
        "updated_at": "2026-09-17T08:00:00Z",
        "last_recommendation_id": None,
        "message_count": 0,
    }
    assert fake.calls == [
        ("create", {"title": "Trip north", "language": "en", "accept_language": "th"})
    ]
    assert response.headers["RateLimit-Limit"] == "10"


async def test_create_accepts_an_empty_body(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.post(URL, json={}, headers=post_headers(make_token()))

    assert response.status_code == 201


async def test_create_rejects_unknown_fields(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.post(URL, json={"topic": "x"}, headers=post_headers(make_token()))

    assert response.status_code == 422


async def test_list_conversations(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    owned(fake)

    response = await client.get(f"{URL}?limit=5&cursor=abc", headers=bearer(make_token()))

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["next_cursor"] == "next-page"
    assert fake.calls[-1] == ("list", {"limit": 5, "cursor": "abc"})


async def test_get_and_delete(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    headers = bearer(make_token())

    found = await client.get(f"{URL}/{conversation_id}", headers=headers)
    deleted = await client.delete(f"{URL}/{conversation_id}", headers=headers)
    gone = await client.get(f"{URL}/{conversation_id}", headers=headers)
    again = await client.delete(f"{URL}/{conversation_id}", headers=headers)

    assert found.status_code == 200
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert gone.status_code == 404
    assert again.status_code == 404


async def test_delete_needs_write_scope(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)

    response = await client.delete(
        f"{URL}/{conversation_id}", headers=bearer(make_token(scopes=["travel:read"]))
    )

    assert response.status_code == 403


async def test_foreign_conversation_is_404(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    foreign = conversation(user_id=new_id())
    fake.records[foreign.id] = foreign

    response = await client.get(f"{URL}/{foreign.id}", headers=bearer(make_token()))

    assert response.status_code == 404


async def test_list_messages(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    reply = message(role=MessageRole.USER, recommendation_id=None, content="Safe?")
    fake.message_page = Page([reply], None)

    response = await client.get(
        f"{URL}/{conversation_id}/messages?limit=10", headers=bearer(make_token())
    )

    assert response.json() == {
        "items": [
            {
                "message_id": str(reply.id),
                "role": "user",
                "content": "Safe?",
                "recommendation_id": None,
                "created_at": "2026-09-17T08:00:00Z",
            }
        ],
        "next_cursor": None,
    }
    assert fake.calls[-1] == ("messages", {"limit": 10, "cursor": None})


async def test_post_message_returns_the_reply(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    reply = message()
    fake.reply = MessageReply(reply)

    response = await client.post(
        f"{URL}/{conversation_id}/messages",
        json={
            "content": "And later?",
            "overrides": {
                "departure_time": "2026-09-20T04:00:00Z",
                "waypoints": [],
                "preferences": {"avoid": ["TOLLS"]},
            },
        },
        headers={**post_headers(make_token()), "Accept-Language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["message_id"] == str(reply.id)
    assert response.json()["role"] == "assistant"
    call = fake.calls[-1][1]
    assert call["content"] == "And later?"
    assert call["stream"] is False
    assert call["accept_language"] == "en"
    assert call["correlation_id"] == response.headers["X-Correlation-ID"]
    overrides: RequestOverrides = call["overrides"]
    assert overrides.departure_time == datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    assert overrides.waypoints == ()
    assert overrides.origin is None
    assert overrides.preferences is not None
    assert overrides.preferences.avoid == (AvoidOption.TOLLS,)
    assert overrides.preferences.travel_modes is None


async def test_post_message_without_overrides(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    fake.reply = MessageReply(message())

    await client.post(
        f"{URL}/{conversation_id}/messages",
        json={"content": "Safe?"},
        headers=post_headers(make_token()),
    )

    assert fake.calls[-1][1]["overrides"] == RequestOverrides()


async def test_streamed_message_is_accepted_and_replayed(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    job_id = new_id()
    fake.reply = Accepted(job_id, new_id(), new_id())
    key = str(uuid4())
    payload = {"content": "Safe?", "stream": True}

    first = await client.post(
        f"{URL}/{conversation_id}/messages", json=payload, headers=post_headers(make_token(), key)
    )
    second = await client.post(
        f"{URL}/{conversation_id}/messages", json=payload, headers=post_headers(make_token(), key)
    )

    assert first.status_code == 202
    assert first.headers["Location"] == f"/v1/jobs/{job_id}"
    assert first.json()["events_url"] == f"/v1/jobs/{job_id}/events"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert len([c for c in fake.calls if c[0] == "post_message"]) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": "x", "overrides": {"seats": 2}},
        {"content": "x", "overrides": {"preferences": {"pets": True}}},
        {"content": "x", "extra": 1},
    ],
)
async def test_invalid_message_bodies(
    client: httpx.AsyncClient,
    make_token: TokenFactory,
    fake: FakeConversations,
    payload: dict[str, object],
) -> None:
    conversation_id = owned(fake)

    response = await client.post(
        f"{URL}/{conversation_id}/messages", json=payload, headers=post_headers(make_token())
    )

    assert response.status_code == 422


async def test_domain_errors_of_a_message(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeConversations
) -> None:
    conversation_id = owned(fake)
    fake.reply = InvalidInput([FieldIssue("overrides", "travel_context_required", "give a trip")])

    response = await client.post(
        f"{URL}/{conversation_id}/messages",
        json={"content": "Safe?"},
        headers=post_headers(make_token()),
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "travel_context_required"
