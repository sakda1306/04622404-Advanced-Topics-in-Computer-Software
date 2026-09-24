"""HTTP contract of /v1/travel/recommendations (services are faked)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_recommendation_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.ids import new_id
from app.domain.enums import RecommendationStatus, RequestMode, RiskLevel, TravelMode
from app.domain.errors import FieldIssue, InvalidInput
from app.main import create_app
from app.services.pagination import Page
from app.services.recommendation_service import Accepted, Finished
from tests.api.fakes import USER, FakeRecommendations, record, summary
from tests.support.auth import TokenFactory

URL = "/v1/travel/recommendations"


def body(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": "2026-09-20T01:00:00Z",
        "timezone": "Asia/Bangkok",
        "preferences": {"travel_modes": ["TRAIN"]},
        "question": "Is it safe?",
    }
    values.update(changes)
    return values


@pytest.fixture
def fake() -> FakeRecommendations:
    return FakeRecommendations()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeRecommendations) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_recommendation_service] = lambda: fake
    return application


def auth(token: str, key: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key or str(uuid4())}


async def test_finished_request_returns_the_recommendation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    done = record()
    fake.outcome = Finished(done)

    response = await client.post(
        URL, json=body(), headers={**auth(make_token()), "Accept-Language": "en-US,en;q=0.9"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommendation_id"] == str(done.id)
    assert data["conversation_id"] == str(done.conversation_id)
    assert data["request_id"] == str(done.request_id)
    assert data["created_at"] == "2026-09-17T08:00:00Z"
    assert data["status"] == "completed"
    assert data["routes"]["primary"]["legs"][0]["from"] == "Krung Thep Aphiwat"
    assert data["job_id"] is None
    assert data["error"] is None
    assert response.headers["X-Request-ID"]
    assert response.headers["RateLimit-Limit"] == "10"
    command = fake.commands[0]
    assert command.mode is RequestMode.AUTO
    assert command.input.accept_language == "en-US,en;q=0.9"
    assert command.input.question == "Is it safe?"
    assert command.input.preferences.travel_modes == (TravelMode.TRAIN,)
    assert command.input.origin.name == "Bangkok"
    assert command.correlation_id == response.headers["X-Correlation-ID"]


async def test_slow_request_is_accepted(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    job_id, rec_id, conv_id = new_id(), new_id(), new_id()
    fake.outcome = Accepted(job_id, rec_id, conv_id)
    key = str(uuid4())

    response = await client.post(f"{URL}?mode=async", json=body(), headers=auth(make_token(), key))
    replay = await client.post(f"{URL}?mode=async", json=body(), headers=auth(make_token(), key))

    assert response.status_code == 202
    assert response.headers["Location"] == f"/v1/jobs/{job_id}"
    assert response.json() == {
        "job_id": str(job_id),
        "status": "queued",
        "recommendation_id": str(rec_id),
        "conversation_id": str(conv_id),
        "events_url": f"/v1/jobs/{job_id}/events",
        "status_url": f"/v1/jobs/{job_id}",
        "estimated_seconds": 20,
    }
    assert fake.commands[0].mode is RequestMode.ASYNC
    assert replay.status_code == 202
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == response.json()
    assert len(fake.commands) == 1


async def test_conversation_and_trip_ids_are_passed(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    fake.outcome = Finished(record())
    conversation_id, trip_id = new_id(), new_id()

    await client.post(
        URL,
        json=body(conversation_id=str(conversation_id), trip_id=str(trip_id)),
        headers=auth(make_token()),
    )

    assert fake.commands[0].conversation_id == conversation_id
    assert fake.commands[0].trip_id == trip_id


async def test_write_scope_is_required(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    response = await client.post(URL, json=body(), headers=auth(make_token(scopes=["travel:read"])))

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("payload", "query"),
    [
        (body(unknown=1), ""),
        (body(origin={"lat": 1, "lon": 2, "extra": True}), ""),
        (body(preferences={"travel_modes": ["ROCKET"]}), ""),
        (body(), "?mode=bogus"),
    ],
)
async def test_schema_errors_are_422(
    client: httpx.AsyncClient,
    make_token: TokenFactory,
    fake: FakeRecommendations,
    payload: dict[str, Any],
    query: str,
) -> None:
    response = await client.post(f"{URL}{query}", json=payload, headers=auth(make_token()))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert fake.commands == []


async def test_domain_validation_errors_are_422(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    fake.outcome = InvalidInput(
        [FieldIssue("timezone", "unknown_timezone", "use an IANA timezone name")]
    )

    response = await client.post(URL, json=body(timezone="Mars"), headers=auth(make_token()))

    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert problem["errors"] == [
        {"field": "timezone", "message": "use an IANA timezone name", "code": "unknown_timezone"}
    ]


async def test_unsupported_region(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    fake.outcome = AppError(
        ErrorCode.UNSUPPORTED_REGION,
        errors=[FieldError("origin", "outside the service area", "unsupported_region")],
    )

    response = await client.post(URL, json=body(), headers=auth(make_token()))

    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_REGION"
    assert response.json()["errors"][0]["field"] == "origin"


async def test_get_returns_the_stored_recommendation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    stored = record()
    fake.records[stored.id] = stored

    response = await client.get(
        f"{URL}/{stored.id}", headers={"Authorization": f"Bearer {make_token()}"}
    )

    assert response.status_code == 200
    assert response.json()["recommendation_id"] == str(stored.id)


async def test_get_of_a_processing_recommendation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    job_id = new_id()
    stored = record(RecommendationStatus.PROCESSING, job_id=job_id)
    fake.records[stored.id] = stored

    response = await client.get(
        f"{URL}/{stored.id}", headers={"Authorization": f"Bearer {make_token()}"}
    )

    data = response.json()
    assert data["status"] == "processing"
    assert data["job_id"] == str(job_id)
    assert data["risk"] is None
    assert data["warnings"] == []


async def test_get_of_a_failed_recommendation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    stored = record(RecommendationStatus.FAILED, payload=None, error_code="AGENT_TIMEOUT")
    fake.records[stored.id] = stored

    response = await client.get(
        f"{URL}/{stored.id}", headers={"Authorization": f"Bearer {make_token()}"}
    )

    assert response.json()["error"] == {
        "code": "AGENT_TIMEOUT",
        "message": "The advisory service did not respond in time.",
    }


async def test_get_of_unknown_or_foreign_recommendation(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    foreign = record(user_id=new_id())
    fake.records[foreign.id] = foreign
    headers = {"Authorization": f"Bearer {make_token()}"}

    assert (await client.get(f"{URL}/{foreign.id}", headers=headers)).status_code == 404
    assert (await client.get(f"{URL}/{new_id()}", headers=headers)).status_code == 404
    assert (await client.get(f"{URL}/not-a-uuid", headers=headers)).status_code == 422


async def test_history_list(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeRecommendations
) -> None:
    item = summary()
    fake.page = Page([item], "more")

    response = await client.get(
        f"{URL}?limit=5&cursor=c1&from=2026-09-01T00:00:00Z&to=2026-09-18T00:00:00%2B07:00"
        "&risk_level=LOW",
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "recommendation_id": str(item.id),
                "created_at": "2026-09-17T08:00:00Z",
                "status": "completed",
                "risk_level": "LOW",
                "recommendation_type": "TRAVEL_NORMALLY",
                "origin_name": "Bangkok",
                "destination_name": "Chiang Mai",
                "departure_time": "2026-09-17T08:00:00Z",
            }
        ],
        "next_cursor": "more",
    }
    call = fake.list_calls[0]
    assert call["limit"] == 5
    assert call["cursor"] == "c1"
    assert call["created_from"] == datetime(2026, 9, 1, tzinfo=UTC)
    assert call["created_to"] == datetime(2026, 9, 17, 17, 0, tzinfo=UTC)
    assert call["risk_level"] is RiskLevel.LOW


@pytest.mark.parametrize("query", ["from=2026-09-01T00:00:00", "risk_level=EXTREME", "limit=x"])
async def test_history_rejects_bad_filters(
    client: httpx.AsyncClient, make_token: TokenFactory, query: str
) -> None:
    response = await client.get(
        f"{URL}?{query}", headers={"Authorization": f"Bearer {make_token()}"}
    )

    assert response.status_code == 422
