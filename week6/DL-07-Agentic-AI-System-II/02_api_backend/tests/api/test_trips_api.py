"""HTTP contract of /v1/trips (services are faked)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_trip_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.ids import new_id
from app.domain.enums import (
    AlertChannel,
    RecommendationStatus,
    RequestMode,
    RiskLevel,
    TravelMode,
    TripStatus,
)
from app.domain.trips import AlertSettings
from app.main import create_app
from app.services.pagination import Page
from app.services.ports import AssessmentSummary
from app.services.recommendation_service import Accepted, Finished
from tests.api.fakes import T0, USER, FakeTrips, record, summary, trip
from tests.support.auth import TokenFactory

URL = "/v1/trips"
READ_ONLY = "travel:read"


@pytest.fixture
def fake() -> FakeTrips:
    return FakeTrips()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeTrips) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_trip_service] = lambda: fake
    return application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post_headers(token: str, key: str | None = None) -> dict[str, str]:
    return {**bearer(token), "Idempotency-Key": key or str(uuid4())}


def owned(fake: FakeTrips, **changes: Any) -> str:
    made = trip(**changes)
    fake.records[made.id] = made
    return str(made.id)


def body(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": "เชียงใหม่ ก.ย.",
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": "2026-09-20T01:00:00Z",
        "timezone": "Asia/Bangkok",
        "preferences": {"travel_modes": ["TRAIN"]},
        "alerts": {"enabled": True, "consent_at": "2026-09-17T08:00:00Z", "channels": ["IN_APP"]},
    }
    values.update(changes)
    return values


async def test_create_trip(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    response = await client.post(URL, json=body(), headers=post_headers(make_token()))

    assert response.status_code == 201, response.text
    data = response.json()
    assert response.headers["Location"] == f"/v1/trips/{data['trip_id']}"
    draft = fake.calls[0][1]
    assert draft.name == "เชียงใหม่ ก.ย."
    assert draft.preferences.travel_modes == (TravelMode.TRAIN,)
    assert draft.alerts == AlertSettings(
        enabled=True,
        consent_at=datetime(2026, 9, 17, 8, tzinfo=UTC),
        channels=(AlertChannel.IN_APP,),
    )
    assert data == {
        "trip_id": data["trip_id"],
        "name": "เชียงใหม่ ก.ย.",
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok", "place_id": None},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai", "place_id": None},
        "waypoints": [],
        "departure_time": "2026-09-20T01:00:00Z",
        "timezone": "Asia/Bangkok",
        "preferences": {
            "travel_modes": ["TRAIN"],
            "avoid": [],
            "max_travel_hours": None,
            "mobility_needs": [],
            "traveler_count": 1,
        },
        "alerts": {
            "enabled": True,
            "consent_at": "2026-09-17T08:00:00Z",
            "channels": ["IN_APP"],
        },
        "status": "PLANNED",
        "last_assessment": None,
        "created_at": "2026-09-17T08:00:00Z",
        "updated_at": "2026-09-17T08:00:00Z",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"color": "red"},
        {"status": "ACTIVE"},
        {"alerts": {"enabled": True, "channels": ["SMS"]}},
        {"name": None},
    ],
)
async def test_create_rejects_bad_bodies(
    client: httpx.AsyncClient, make_token: TokenFactory, bad: dict[str, Any]
) -> None:
    response = await client.post(URL, json=body(**bad), headers=post_headers(make_token()))

    assert response.status_code == 422


async def test_create_needs_write_scope_and_key(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    read_only = await client.post(
        URL, json=body(), headers=post_headers(make_token(scopes=[READ_ONLY]))
    )
    no_key = await client.post(URL, json=body(), headers=bearer(make_token()))

    assert read_only.status_code == 403
    assert no_key.status_code == 400


async def test_create_is_idempotent(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    headers = post_headers(make_token())

    first = await client.post(URL, json=body(), headers=headers)
    second = await client.post(URL, json=body(), headers=headers)

    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json() == first.json()
    assert len(fake.calls) == 1


async def test_list_and_get(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(
        fake,
        last_assessment=AssessmentSummary(
            new_id(), RecommendationStatus.COMPLETED, RiskLevel.HIGH, None, T0
        ),
        assessment_outdated=True,
    )
    headers = bearer(make_token(scopes=[READ_ONLY]))

    listed = await client.get(f"{URL}?limit=5&cursor=abc&status=PLANNED", headers=headers)
    found = await client.get(f"{URL}/{trip_id}", headers=headers)
    missing = await client.get(f"{URL}/{uuid4()}", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["next_cursor"] == "next-page"
    assert fake.calls[-1] == (
        "list",
        {"limit": 5, "cursor": "abc", "status": TripStatus.PLANNED},
    )
    assessment = found.json()["last_assessment"]
    assert assessment["risk_level"] == "HIGH"
    assert assessment["outdated"] is True
    assert missing.status_code == 404


async def test_patch_with_merge_patch(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)

    response = await client.patch(
        f"{URL}/{trip_id}",
        content=b'{"name": "Renamed", "preferences": {"max_travel_hours": 6}, "waypoints": null}',
        headers={**bearer(make_token()), "Content-Type": "application/merge-patch+json"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed"
    changes = fake.calls[-1][1]
    assert changes.name == "Renamed"
    assert changes.preferences.max_travel_hours == 6
    assert changes.preferences.travel_modes is None
    assert changes.explicit_nulls == frozenset({"waypoints"})


async def test_patch_tracks_nested_nulls(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)

    await client.patch(
        f"{URL}/{trip_id}",
        json={"preferences": {"max_travel_hours": None}, "alerts": {"channels": None}},
        headers=bearer(make_token()),
    )

    changes = fake.calls[-1][1]
    assert changes.explicit_nulls == frozenset({"preferences.max_travel_hours", "alerts.channels"})


async def test_patch_null_on_required_field_is_422(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)

    response = await client.patch(
        f"{URL}/{trip_id}", json={"name": None}, headers=bearer(make_token())
    )

    assert response.status_code == 422
    assert response.json()["errors"][0] == {
        "field": "name",
        "message": "this field cannot be null",
        "code": "required",
    }


async def test_patch_status_and_scope(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)

    forbidden = await client.patch(
        f"{URL}/{trip_id}",
        json={"status": "ACTIVE"},
        headers=bearer(make_token(scopes=[READ_ONLY])),
    )
    active = await client.patch(
        f"{URL}/{trip_id}", json={"status": "ACTIVE"}, headers=bearer(make_token())
    )
    bad = await client.patch(
        f"{URL}/{trip_id}", json={"status": "LOST"}, headers=bearer(make_token())
    )

    assert forbidden.status_code == 403
    assert active.json()["status"] == "ACTIVE"
    assert bad.status_code == 422


async def test_delete(client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips) -> None:
    trip_id = owned(fake)
    headers = bearer(make_token())

    deleted = await client.delete(f"{URL}/{trip_id}", headers=headers)
    again = await client.delete(f"{URL}/{trip_id}", headers=headers)

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert again.status_code == 404


async def test_assess_finished(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)
    fake.outcome = Finished(record())

    response = await client.post(
        f"{URL}/{trip_id}/assessments",
        json={"mode": "sync", "language": "en"},
        headers={**post_headers(make_token()), "Accept-Language": "th"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.headers["RateLimit-Limit"] == "10"
    kwargs = fake.calls[-1][1]
    assert kwargs["mode"] is RequestMode.SYNC
    assert kwargs["language"] == "en"
    assert kwargs["accept_language"] == "th"


async def test_assess_accepted_with_empty_body(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)
    job_id, rec_id, conv_id = new_id(), new_id(), new_id()
    fake.outcome = Accepted(job_id, rec_id, conv_id)

    response = await client.post(
        f"{URL}/{trip_id}/assessments", json={}, headers=post_headers(make_token())
    )

    assert response.status_code == 202
    assert response.json()["events_url"] == f"/v1/jobs/{job_id}/events"
    assert response.headers["Location"] == f"/v1/jobs/{job_id}"
    assert fake.calls[-1][1]["mode"] is RequestMode.AUTO


async def test_assessment_history(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    trip_id = owned(fake)
    item = summary()
    fake.page = Page([item], None)

    response = await client.get(
        f"{URL}/{trip_id}/assessments?limit=3", headers=bearer(make_token(scopes=[READ_ONLY]))
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["recommendation_id"] == str(item.id)
    assert fake.calls[-1] == ("assessments", {"limit": 3, "cursor": None})


async def test_other_users_trip_is_404(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeTrips
) -> None:
    stranger = replace(trip(), user_id=new_id())
    fake.records[stranger.id] = stranger
    headers = bearer(make_token())

    responses = [
        await client.get(f"{URL}/{stranger.id}", headers=headers),
        await client.patch(f"{URL}/{stranger.id}", json={"name": "x"}, headers=headers),
        await client.delete(f"{URL}/{stranger.id}", headers=headers),
        await client.get(f"{URL}/{stranger.id}/assessments", headers=headers),
        await client.post(
            f"{URL}/{stranger.id}/assessments", json={}, headers=post_headers(make_token())
        ),
    ]

    assert [r.status_code for r in responses] == [404] * 5
