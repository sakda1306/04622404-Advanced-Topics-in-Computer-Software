"""The scheduled scan queues re-assessments for trips with live alerts on (D-65)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.domain.enums import JobType, RequestSource
from app.domain.normalization import GeoPoint
from app.domain.trips import AlertSettings, TripDraft
from app.infrastructure.db.models import JobModel, RecommendationModel, TravelRequestModel
from tests.integration.flow import Flow, tune

pytestmark = pytest.mark.integration


def draft(**changes: object) -> TripDraft:
    base = TripDraft(
        name="Soon",
        origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
        destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
        departure_time=datetime.now(UTC) + timedelta(hours=5),
        timezone="Asia/Bangkok",
        alerts=AlertSettings(enabled=True, consent_at=datetime.now(UTC)),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


async def queued_for(flow: Flow, trip_id: UUID) -> list[tuple[str, str]]:
    async with flow.repo.sessions() as session:
        rows = (
            await session.execute(
                select(JobModel.type, TravelRequestModel.source)
                .join(RecommendationModel, RecommendationModel.id == JobModel.recommendation_id)
                .join(TravelRequestModel, TravelRequestModel.id == RecommendationModel.request_id)
                .where(RecommendationModel.trip_id == trip_id)
            )
        ).all()
    return [(row[0], row[1]) for row in rows]


async def test_scan_queues_due_trips_once(flow: Flow) -> None:
    user = await flow.user()
    trips = flow.trips()
    due = await trips.create(user, draft())
    quiet = await trips.create(user, draft(alerts=AlertSettings()))
    later = await trips.create(user, draft(departure_time=datetime.now(UTC) + timedelta(days=3)))
    scanner = flow.trip_alerts()

    result = await scanner.scan()
    await flow.queue.drain()

    assert result.queued >= 1
    assert await queued_for(flow, due.id) == [
        (JobType.TRIP_ASSESSMENT.value, RequestSource.TRIP_ALERT.value)
    ]
    assert await queued_for(flow, quiet.id) == []
    assert await queued_for(flow, later.id) == []
    loaded = await trips.get(user, due.id)
    assert loaded.last_assessment is not None

    await scanner.scan()
    await flow.queue.drain()
    assert len(await queued_for(flow, due.id)) == 1


async def test_running_assessment_is_not_queued_again(flow: Flow) -> None:
    user = await flow.user()
    trip = await flow.trips().create(user, draft())
    scanner = flow.trip_alerts()
    flow.queue.worker = None  # the job stays queued

    await scanner.scan()
    await scanner.scan()

    assert len(await queued_for(flow, trip.id)) == 1


async def test_user_at_the_job_limit_is_skipped(flow: Flow) -> None:
    settings = tune(flow.settings, limits={"max_active_jobs_per_user": 1})
    user = await flow.user()
    trips = flow.trips(settings)
    first = await trips.create(user, draft(name="first"))
    second = await trips.create(
        user, draft(name="second", departure_time=datetime.now(UTC) + timedelta(hours=6))
    )
    scanner = flow.trip_alerts(settings)
    flow.queue.worker = None

    result = await scanner.scan()

    assert result.skipped >= 1
    assert len(await queued_for(flow, first.id)) == 1
    assert await queued_for(flow, second.id) == []
