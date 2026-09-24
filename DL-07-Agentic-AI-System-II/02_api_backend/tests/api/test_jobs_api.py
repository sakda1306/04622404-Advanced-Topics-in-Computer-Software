"""HTTP contract of /v1/jobs, stream tickets and SSE (services are faked)."""

from __future__ import annotations

import anyio
import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_job_service, get_user_service
from app.api.resources import AppResources
from app.api.v1.jobs import event_frames
from app.core.config import Settings
from app.core.ids import new_id
from app.domain.enums import JobStage, JobStatus
from app.infrastructure.redis.job_state import JobEvent
from app.main import create_app
from tests.api.fakes import USER, FakeJobs, FakeUsers, job
from tests.support.auth import TokenFactory


@pytest.fixture
def fake() -> FakeJobs:
    return FakeJobs()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeJobs) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_job_service] = lambda: fake
    application.dependency_overrides[get_user_service] = lambda: FakeUsers()
    return application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_job_status(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    failed = job(status=JobStatus.FAILED, stage=JobStage.FAILED, error_code="AGENT_TIMEOUT")
    fake.jobs.update({running.id: running, failed.id: failed})

    first = (await client.get(f"/v1/jobs/{running.id}", headers=bearer(make_token()))).json()
    second = (await client.get(f"/v1/jobs/{failed.id}", headers=bearer(make_token()))).json()

    assert first == {
        "job_id": str(running.id),
        "type": "RECOMMENDATION",
        "status": "running",
        "stage": "assessing_risk",
        "progress": 60,
        "created_at": "2026-09-17T08:00:00Z",
        "updated_at": "2026-09-17T08:00:00Z",
        "result_url": f"/v1/travel/recommendations/{running.recommendation_id}",
        "error": None,
    }
    assert second["error"] == {
        "code": "AGENT_TIMEOUT",
        "message": "The advisory service did not respond in time.",
    }


async def test_foreign_job_is_404(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    foreign = job(user_id=new_id())
    fake.jobs[foreign.id] = foreign

    response = await client.get(f"/v1/jobs/{foreign.id}", headers=bearer(make_token()))

    assert response.status_code == 404


async def test_read_scope_is_required(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running
    token = make_token(scopes=["profile:read"])

    status = await client.get(f"/v1/jobs/{running.id}", headers=bearer(token))
    events = await client.get(f"/v1/jobs/{running.id}/events", headers=bearer(token))

    assert status.status_code == 403
    assert events.status_code == 403


async def test_stream_ticket(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running

    response = await client.post(
        f"/v1/jobs/{running.id}/stream-ticket", headers=bearer(make_token())
    )

    assert response.status_code == 200
    assert response.json() == {"ticket": "ticket-0", "expires_in": 60}


def stream_events(job_id: str) -> list[JobEvent | None]:
    return [
        JobEvent("1-0", "progress", {"job_id": job_id, "stage": "queued", "progress": 0}),
        None,
        JobEvent("2-0", "completed", {"job_id": job_id, "status": "completed"}),
    ]


async def test_events_with_bearer_token(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running
    fake.events = stream_events(str(running.id))

    response = await client.get(
        f"/v1/jobs/{running.id}/events",
        headers={**bearer(make_token()), "Last-Event-ID": "1-0"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.text == (
        "id: 1-0\nevent: progress\n"
        f'data: {{"job_id":"{running.id}","stage":"queued","progress":0}}\n\n'
        ": ping\n\n"
        "id: 2-0\nevent: completed\n"
        f'data: {{"job_id":"{running.id}","status":"completed"}}\n\n'
    )
    assert fake.last_event_ids == ["1-0"]
    assert fake.closed == ["conn-1"]


async def test_synthetic_final_event_has_no_id(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running
    fake.events = [JobEvent("0-0", "cancelled", {"job_id": str(running.id)})]

    response = await client.get(f"/v1/jobs/{running.id}/events", headers=bearer(make_token()))

    assert response.text == f'event: cancelled\ndata: {{"job_id":"{running.id}"}}\n\n'


async def test_events_with_ticket_and_no_header(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running
    fake.events = stream_events(str(running.id))
    ticket = (
        await client.post(f"/v1/jobs/{running.id}/stream-ticket", headers=bearer(make_token()))
    ).json()["ticket"]

    first = await client.get(f"/v1/jobs/{running.id}/events?ticket={ticket}")
    reused = await client.get(f"/v1/jobs/{running.id}/events?ticket={ticket}")

    assert first.status_code == 200
    assert "event: completed" in first.text
    assert reused.status_code == 401
    assert reused.json()["code"] == "UNAUTHENTICATED"


async def test_events_without_credentials(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/jobs/{new_id()}/events")

    assert response.status_code == 401


async def test_stream_slot_is_released_when_the_response_is_cancelled() -> None:
    fake = FakeJobs(events=[None], hang=True)
    running = job()
    frames = event_frames(fake, USER.id, running, "conn-1", last_event_id=None)  # type: ignore[arg-type]

    # Starlette cancels the streaming task when the client goes away.
    with anyio.CancelScope() as scope:
        async for _ in frames:
            scope.cancel()

    assert fake.closed == ["conn-1"]


async def test_cancel_a_job(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    done = job(status=JobStatus.SUCCEEDED, stage=JobStage.COMPLETED)
    fake.jobs.update({running.id: running, done.id: done})
    headers = bearer(make_token())

    cancelled = await client.delete(f"/v1/jobs/{running.id}", headers=headers)
    finished = await client.delete(f"/v1/jobs/{done.id}", headers=headers)
    missing = await client.delete(f"/v1/jobs/{new_id()}", headers=headers)
    read_only = await client.delete(
        f"/v1/jobs/{running.id}", headers=bearer(make_token(scopes=["travel:read"]))
    )

    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["stage"] == "cancelled"
    assert finished.status_code == 409
    assert finished.json()["code"] == "JOB_NOT_CANCELLABLE"
    assert missing.status_code == 404
    assert read_only.status_code == 403


async def test_cancel_reports_rate_limit_headers(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeJobs
) -> None:
    running = job()
    fake.jobs[running.id] = running

    response = await client.delete(f"/v1/jobs/{running.id}", headers=bearer(make_token()))

    assert response.status_code == 202
    assert "RateLimit-Limit" in response.headers
