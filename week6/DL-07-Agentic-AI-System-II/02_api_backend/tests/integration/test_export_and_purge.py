"""Data export, the nightly purge and export files on account deletion."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app.core.errors import AppError, ErrorCode
from app.domain.enums import ExportStatus, RequestMode
from app.infrastructure.db.models import (
    AuditLogModel,
    ConversationModel,
    DataExportModel,
)
from app.services.recommendation_service import CreateRecommendation
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration


async def ask(flow: Flow, user: Any) -> None:
    await flow.recommendations().create(
        user,
        CreateRecommendation(
            input=travel_input(question="ถนนไปเชียงใหม่ปลอดภัยไหม"),
            mode=RequestMode.AUTO,
            conversation_id=None,
            trip_id=None,
            correlation_id="corr-export",
        ),
    )
    await flow.queue.drain()


def unzip(data: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        loaded: dict[str, Any] = json.loads(archive.read("travel-safety-data.json"))
    return loaded


async def test_export_contains_the_users_data(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    await ask(flow, user)
    await ask(flow, other)
    exports = flow.exports()

    requested = await exports.request(user, correlation_id="corr-1")
    assert [export_id for export_id, _ in flow.queue.exports] == [requested.id]
    assert await exports.build(requested.id) is True
    assert await exports.build(requested.id) is False  # already built

    view = await exports.get(user, requested.id)
    assert view.record.status is ExportStatus.READY
    assert view.download_url == (f"https://storage.example/exports/{requested.id}.zip?expires=900")
    assert view.record.expires_at is not None
    assert view.record.completed_at is not None
    assert view.record.expires_at - view.record.completed_at == timedelta(days=7)
    data, content_type = flow.store.objects[f"exports/{requested.id}.zip"]
    assert content_type == "application/zip"
    exported = unzip(data)
    assert exported["profile"]["user_id"] == str(user.id)
    messages = exported["conversations"][0]["messages"]
    assert messages[0]["content"] == "ถนนไปเชียงใหม่ปลอดภัยไหม"  # decrypted for the owner
    assert len(exported["recommendations"]) == 1
    assert exported["recommendations"][0]["request"]["origin"]["lat"] == 13.7563
    assert str(other.id) not in json.dumps(exported)


async def test_one_export_per_day(flow: Flow) -> None:
    user = await flow.user()
    exports = flow.exports()
    await exports.request(user, correlation_id="c")

    with pytest.raises(AppError) as info:
        await exports.request(user, correlation_id="c")

    assert info.value.code is ErrorCode.RATE_LIMITED
    assert info.value.retry_after is not None
    assert info.value.retry_after > 23 * 3600


async def test_other_users_export_is_hidden(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    requested = await flow.exports().request(user, correlation_id="c")

    with pytest.raises(AppError) as info:
        await flow.exports().get(other, requested.id)

    assert info.value.code is ErrorCode.NOT_FOUND


async def test_storage_failure_fails_the_export(flow: Flow) -> None:
    user = await flow.user()
    exports = flow.exports()
    requested = await exports.request(user, correlation_id="c")
    flow.store.fail_on_put = True

    assert await exports.build(requested.id) is False

    view = await exports.get(user, requested.id)
    assert view.record.status is ExportStatus.FAILED
    assert view.download_url is None


async def test_expired_export_has_no_link_and_is_purged(flow: Flow) -> None:
    user = await flow.user()
    exports = flow.exports()
    requested = await exports.request(user, correlation_id="c")
    await exports.build(requested.id)
    async with flow.repo.sessions() as session, session.begin():
        await session.execute(
            update(DataExportModel)
            .where(DataExportModel.id == requested.id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    assert (await exports.get(user, requested.id)).download_url is None
    result = await flow.purge().run()

    assert result.ran is True
    assert result.exports_expired >= 1
    assert f"exports/{requested.id}.zip" not in flow.store.objects
    view = await exports.get(user, requested.id)
    assert view.record.status is ExportStatus.EXPIRED


async def test_purge_removes_expired_rows_and_is_audited(flow: Flow) -> None:
    user = await flow.user()
    await ask(flow, user)
    async with flow.repo.sessions() as session, session.begin():
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.user_id == user.id)
            .values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )

    result = await flow.purge().run()
    second = await flow.purge().run()

    assert result.deleted["conversations"] >= 1
    assert second.ran is True  # the lock is released after each run
    async with flow.repo.sessions() as session:
        left = await session.scalar(
            select(ConversationModel.id).where(ConversationModel.user_id == user.id)
        )
        audit = await session.scalar(
            select(AuditLogModel)
            .where(AuditLogModel.action == "retention.purge")
            .order_by(AuditLogModel.occurred_at.desc())
            .limit(1)
        )
    assert left is None
    assert audit is not None
    assert audit.actor_type == "system"
    assert "conversations" in audit.metadata_["deleted"]


async def test_purge_runs_once_at_a_time(flow: Flow) -> None:
    await flow.redis.set(flow.keys.cooldown("purge"), "1", ex=60)

    result = await flow.purge().run()

    assert result.ran is False


async def test_account_deletion_removes_export_files(flow: Flow) -> None:
    user = await flow.user()
    exports = flow.exports()
    requested = await exports.request(user, correlation_id="c")
    await exports.build(requested.id)
    assert f"exports/{requested.id}.zip" in flow.store.objects

    assert await flow.account().delete(user.id, correlation_id="c") is True

    assert f"exports/{requested.id}.zip" not in flow.store.objects
