"""Profile, consents and account deletion use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.domain.enums import JobStatus, RequestMode, RequestSource
from app.domain.errors import InvalidInput
from app.domain.normalization import NormalizationLimits, normalize_travel_request
from app.domain.profile import ConsentChanges, ProfileChanges
from app.infrastructure.db.models import AuditLogModel, JobModel, UserModel
from app.services.ports import NewRecommendation, UserRef
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration


def new(user: UserRef) -> NewRecommendation:
    now = datetime.now(UTC)
    return NewRecommendation(
        user_id=user.id,
        request=normalize_travel_request(travel_input(), now=now, limits=NormalizationLimits()),
        mode=RequestMode.ASYNC,
        source=RequestSource.RECOMMENDATION,
        conversation_id=None,
        trip_id=None,
        cache_key=None,
        correlation_id="corr-me",
        now=now,
        retention_days=30,
        conversation_days=30,
    )


async def audit(flow: Flow, actor_ref: str) -> list[tuple[str, str, dict[str, object]]]:
    async with flow.repo.sessions() as session:
        rows = (
            await session.scalars(
                select(AuditLogModel)
                .where(AuditLogModel.actor_ref == actor_ref)
                .order_by(AuditLogModel.id)
            )
        ).all()
    return [(row.action, row.actor_type, row.metadata_) for row in rows]


async def test_get_masks_the_email(flow: Flow) -> None:
    user = await flow.user()

    record, masked = await flow.me().get(user, email="sakda@example.com")

    assert record.user_id == user.id
    assert masked == "s***@example.com"
    with pytest.raises(AppError) as info:
        await flow.me().get(UserRef(UUID(int=1), "x", "th", None), email=None)
    assert info.value.code is ErrorCode.NOT_FOUND


async def test_update_audits_consent_changes_only(flow: Flow) -> None:
    user = await flow.user()
    me = flow.me()

    renamed = await me.update(
        user, ProfileChanges(display_name="Nok"), correlation_id="c1", ip_hash=None
    )
    agreed = await me.update(
        user,
        ProfileChanges(consents=ConsentChanges(analytics=True)),
        correlation_id="c2",
        ip_hash="a" * 64,
    )

    assert renamed.profile.display_name == "Nok"
    assert agreed.profile.consents.analytics is True
    assert await audit(flow, user.pseudonymous_id) == [
        ("user.consent", "user", {"analytics": True})
    ]
    with pytest.raises(InvalidInput):
        await me.update(user, ProfileChanges(language="fr"), correlation_id="c3", ip_hash=None)


async def test_delete_stops_everything_and_queues_the_deletion(flow: Flow) -> None:
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user))
    idem = flow.keys.idempotency("principal-hash", "POST", "/v1/x", "k-1")
    await flow.redis.set(idem, "stored response")

    await flow.me().delete(
        user, principal_hash="principal-hash", correlation_id="c-del", ip_hash=None
    )

    async with flow.repo.sessions() as session:
        job = await session.get(JobModel, job_id)
        row = await session.get(UserModel, user.id)
    assert job is not None
    assert job.status == JobStatus.CANCELLED.value
    assert row is not None
    assert row.deleted_at is not None
    assert not await flow.redis.exists(idem)
    assert not await flow.redis.exists(flow.keys.job(job_id))
    assert [uid for uid, _ in flow.queue.deletions] == [user.id]
    assert ("user.delete_requested", "user", {}) in await audit(flow, user.pseudonymous_id)

    await flow.me().delete(user, principal_hash="principal-hash", correlation_id="c2", ip_hash=None)
    assert len(flow.queue.deletions) == 1


async def test_account_deletion_task(flow: Flow) -> None:
    user = await flow.user()
    await flow.me().delete(user, principal_hash="p", correlation_id="c", ip_hash=None)

    assert await flow.account().delete(user.id, correlation_id="c-task") is True
    assert await flow.account().delete(user.id, correlation_id="c-task") is False

    async with flow.repo.sessions() as session:
        assert await session.get(UserModel, user.id) is None
    assert ("user.delete", "system", {}) in await audit(flow, user.pseudonymous_id)
