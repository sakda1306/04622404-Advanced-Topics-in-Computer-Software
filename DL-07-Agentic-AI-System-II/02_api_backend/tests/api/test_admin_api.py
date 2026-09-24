"""Admin endpoints over HTTP with in-memory repositories (docs/02_api_spec.md 8.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_admin_service, get_audit, get_training_export_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.ids import new_id
from app.domain.admin import AuditFilter, TimeRange
from app.domain.enums import (
    ActorType,
    AuditResult,
    ExportStatus,
    JobStage,
    JobStatus,
    JobType,
    RecommendationStatus,
    RequestSource,
)
from app.main import create_app
from app.services.admin_service import AdminService
from app.services.pagination import Cursor
from app.services.ports import (
    AdminJobRecord,
    AdminRecommendationRecord,
    AuditEntry,
    AuditLogRecord,
    TrainingExportRecord,
)
from app.services.training_export_service import TrainingExportService
from tests.support.auth import TokenFactory
from tests.support.clock import FakeClock
from tests.support.storage import MemoryObjectStore

T0 = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
READ = ["admin:read"]
WRITE = ["admin:write"]


@dataclass
class RecordingAudit:
    entries: list[AuditEntry] = field(default_factory=list)

    async def write(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


def job(offset_minutes: int, **changes: Any) -> AdminJobRecord:
    record = AdminJobRecord(
        id=new_id(),
        type=JobType.RECOMMENDATION,
        status=JobStatus.SUCCEEDED,
        stage=JobStage.COMPLETED,
        attempts=1,
        error_code=None,
        recommendation_id=new_id(),
        cancel_requested=False,
        created_at=T0 - timedelta(minutes=offset_minutes),
        started_at=None,
        finished_at=None,
    )
    return replace(record, **changes)


@dataclass
class FakeAdminRepository:
    job_rows: list[AdminJobRecord] = field(default_factory=list)
    detail: AdminRecommendationRecord | None = None
    audit_rows: list[AuditLogRecord] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def jobs(
        self,
        *,
        period: TimeRange,
        status: JobStatus | None,
        job_type: JobType | None,
        limit: int,
        cursor: Cursor | None,
    ) -> list[AdminJobRecord]:
        self.calls.append({"period": period, "status": status, "type": job_type})
        rows = sorted(self.job_rows, key=lambda r: (r.created_at, r.id), reverse=True)
        if cursor is not None:
            rows = [r for r in rows if (r.created_at, r.id) < (cursor.at, cursor.id)]
        return rows[: limit + 1]

    async def recommendation(self, recommendation_id: UUID) -> AdminRecommendationRecord | None:
        if self.detail is not None and self.detail.id == recommendation_id:
            return self.detail
        return None

    async def audit_logs(
        self, *, period: TimeRange, where: AuditFilter, limit: int, cursor: Cursor | None
    ) -> list[AuditLogRecord]:
        self.calls.append({"period": period, "where": where})
        return self.audit_rows[: limit + 1]


@dataclass
class FakeTrainingRepository:
    records: dict[UUID, TrainingExportRecord] = field(default_factory=dict)

    async def create(
        self, requested_by: str, *, period: TimeRange, now: datetime
    ) -> TrainingExportRecord:
        record = TrainingExportRecord(
            id=new_id(),
            requested_by=requested_by,
            status=ExportStatus.QUEUED,
            range_from=period.start,
            range_to=period.end,
            row_count=None,
            object_key=None,
            created_at=now,
            completed_at=None,
            expires_at=None,
        )
        self.records[record.id] = record
        return record

    async def get(self, export_id: UUID) -> TrainingExportRecord | None:
        return self.records.get(export_id)

    async def start(self, export_id: UUID) -> TimeRange | None:
        return None

    async def rows(self, period: TimeRange, *, batch: int) -> AsyncIterator[dict[str, Any]]:
        return
        yield {}

    async def finish(self, export_id: UUID, **_: Any) -> None:
        return None

    async def fail(self, export_id: UUID, *, now: datetime) -> None:
        self.records[export_id] = replace(self.records[export_id], status=ExportStatus.FAILED)

    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int:
        return 0


@dataclass
class FakeQueue:
    queued: list[UUID] = field(default_factory=list)
    down: bool = False

    async def enqueue_training_export(self, export_id: UUID, *, correlation_id: str) -> str:
        if self.down:
            raise ConnectionError("broker down")
        self.queued.append(export_id)
        return "task-1"


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


@pytest.fixture
def repo() -> FakeAdminRepository:
    return FakeAdminRepository()


@pytest.fixture
def training() -> FakeTrainingRepository:
    return FakeTrainingRepository()


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def app(
    settings: Settings,
    resources: AppResources,
    audit: RecordingAudit,
    repo: FakeAdminRepository,
    training: FakeTrainingRepository,
    queue: FakeQueue,
) -> FastAPI:
    application = create_app(settings, resources)
    clock = FakeClock(current=T0)
    application.dependency_overrides[get_audit] = lambda: audit
    application.dependency_overrides[get_admin_service] = lambda: AdminService(
        repository=repo, audit=audit, settings=settings, clock=clock
    )
    application.dependency_overrides[get_training_export_service] = lambda: TrainingExportService(
        exports=training,
        store=MemoryObjectStore(),
        queue=queue,
        audit=audit,
        settings=settings,
        clock=clock,
    )
    return application


def auth(make_token: TokenFactory, scopes: list[str], **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token('admin-1', scopes)}", **extra}


async def test_admin_routes_need_a_token(client: AsyncClient) -> None:
    assert (await client.get("/v1/admin/jobs")).status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "action", "scope"),
    [
        ("GET", "/v1/admin/jobs", "admin.jobs_list", "admin:read"),
        ("GET", f"/v1/admin/recommendations/{uuid4()}", "admin.recommendation_read", "admin:read"),
        ("GET", "/v1/admin/audit-logs", "admin.audit_logs_list", "admin:read"),
        ("GET", "/v1/admin/feedback/reviews", "feedback.review_list", "safety:review"),
    ],
)
async def test_missing_scope_is_refused_and_audited(
    client: AsyncClient,
    make_token: TokenFactory,
    audit: RecordingAudit,
    method: str,
    path: str,
    action: str,
    scope: str,
) -> None:
    response = await client.request(method, path, headers=auth(make_token, ["travel:read"]))

    assert response.status_code == 403
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert (entry.action, entry.result, entry.actor_type) == (
        action,
        AuditResult.DENIED,
        ActorType.ADMIN,
    )
    assert entry.actor_ref == "admin-1"
    assert entry.metadata == {"required_scope": scope}
    assert entry.ip_hash is not None


async def test_read_scope_cannot_start_a_training_export(
    client: AsyncClient, make_token: TokenFactory, audit: RecordingAudit
) -> None:
    response = await client.post(
        "/v1/admin/exports/training-data",
        json={},
        headers=auth(make_token, READ, **{"Idempotency-Key": "train-0001"}),
    )

    assert response.status_code == 403
    assert audit.entries[0].action == "export.training_data"


async def test_list_jobs_newest_first_with_cursor(
    client: AsyncClient,
    make_token: TokenFactory,
    repo: FakeAdminRepository,
    audit: RecordingAudit,
) -> None:
    repo.job_rows = [job(minutes) for minutes in (5, 1, 3)]
    headers = auth(make_token, READ)

    first = await client.get("/v1/admin/jobs", params={"limit": 2}, headers=headers)
    body = first.json()
    second = await client.get(
        "/v1/admin/jobs", params={"limit": 2, "cursor": body["next_cursor"]}, headers=headers
    )

    assert first.status_code == 200
    assert [i["created_at"] for i in body["items"]] == [
        "2026-09-17T07:59:00Z",
        "2026-09-17T07:57:00Z",
    ]
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
    item = body["items"][0]
    assert "user_id" not in item
    assert set(item) >= {"job_id", "type", "status", "stage", "error_code", "cancel_requested"}
    assert repo.calls[0]["period"] == TimeRange(T0 - timedelta(days=1), T0)
    assert audit.entries[0].action == "admin.jobs_list"
    assert audit.entries[0].metadata["count"] == 2


async def test_list_jobs_filters_and_range(
    client: AsyncClient, make_token: TokenFactory, repo: FakeAdminRepository
) -> None:
    response = await client.get(
        "/v1/admin/jobs",
        params={
            "status": "failed",
            "type": "MESSAGE",
            "from": "2026-09-10T00:00:00Z",
            "to": "2026-09-12T00:00:00Z",
        },
        headers=auth(make_token, READ),
    )

    assert response.status_code == 200
    call = repo.calls[0]
    assert (call["status"], call["type"]) == (JobStatus.FAILED, JobType.MESSAGE)
    assert call["period"].start == datetime(2026, 9, 10, tzinfo=UTC)


@pytest.mark.parametrize(
    ("params", "field_name"),
    [
        ({"from": "2026-09-12T00:00:00Z", "to": "2026-09-10T00:00:00Z"}, "from"),
        ({"from": "2026-07-01T00:00:00Z", "to": "2026-09-10T00:00:00Z"}, "from"),
        ({"status": "lost"}, "status"),
        ({"limit": "0"}, "limit"),
        ({"cursor": "not-a-cursor"}, "cursor"),
    ],
)
async def test_list_jobs_rejects_bad_queries(
    client: AsyncClient, make_token: TokenFactory, params: dict[str, str], field_name: str
) -> None:
    response = await client.get("/v1/admin/jobs", params=params, headers=auth(make_token, READ))

    assert response.status_code == 422
    assert field_name in {e["field"].split(".")[-1] for e in response.json()["errors"]}


def detail(recommendation_id: UUID) -> AdminRecommendationRecord:
    return AdminRecommendationRecord(
        id=recommendation_id,
        source=RequestSource.RECOMMENDATION,
        status=RecommendationStatus.PARTIAL_RESULT,
        risk_level=None,
        risk_score=None,
        risk_confidence=None,
        recommendation_type=None,
        warning_codes=("DATA_INCOMPLETE",),
        safety_gate_rules=("R-02", "R-03"),
        overall_is_stale=False,
        error_code=None,
        versions={"api": "1.0.0", "agent": "0.3.1", "risk_model": None, "prompt": None},
        data_freshness=[{"category": "disaster", "updated_at": None, "is_stale": True}],
        service_status={"disaster": "unavailable"},
        created_at=T0,
        completed_at=T0,
        valid_until=None,
        job=job(0),
        agent_runs=(),
    )


async def test_recommendation_diagnostics(
    client: AsyncClient,
    make_token: TokenFactory,
    repo: FakeAdminRepository,
    audit: RecordingAudit,
) -> None:
    rec_id = new_id()
    repo.detail = detail(rec_id)

    response = await client.get(
        f"/v1/admin/recommendations/{rec_id}", headers=auth(make_token, READ)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["safety_gate_rules"] == ["R-02", "R-03"]
    assert body["versions"]["agent"] == "0.3.1"
    assert body["job"]["status"] == "succeeded"
    assert not {"payload", "user_id", "origin", "destination", "question"} & set(body)
    assert (audit.entries[0].target_type, audit.entries[0].target_id) == (
        "recommendation",
        str(rec_id),
    )


async def test_unknown_recommendation_is_404_and_audited(
    client: AsyncClient, make_token: TokenFactory, audit: RecordingAudit
) -> None:
    response = await client.get(
        f"/v1/admin/recommendations/{uuid4()}", headers=auth(make_token, READ)
    )

    assert response.status_code == 404
    assert audit.entries[0].result is AuditResult.ERROR


async def test_audit_log_listing(
    client: AsyncClient,
    make_token: TokenFactory,
    repo: FakeAdminRepository,
    audit: RecordingAudit,
) -> None:
    repo.audit_rows = [
        AuditLogRecord(
            id=42,
            occurred_at=T0,
            actor_type=ActorType.ADMIN,
            actor_ref="reviewer-1",
            action="feedback.review",
            target_type="feedback",
            target_id="abc",
            result=AuditResult.SUCCESS,
            correlation_id="corr-1",
            metadata={"status": "approved"},
        )
    ]

    response = await client.get(
        "/v1/admin/audit-logs",
        params={"action": "feedback.review", "target_type": "feedback", "target_id": "abc"},
        headers=auth(make_token, READ),
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == 42
    assert "ip_hash" not in item
    where = repo.calls[0]["where"]
    assert (where.action, where.target_id) == ("feedback.review", "abc")
    assert audit.entries[-1].action == "admin.audit_logs_list"


async def test_audit_log_rejects_bad_filters(client: AsyncClient, make_token: TokenFactory) -> None:
    response = await client.get(
        "/v1/admin/audit-logs",
        params={"action": "drop table"},
        headers=auth(make_token, READ),
    )

    assert response.status_code == 422


async def test_request_and_read_a_training_export(
    client: AsyncClient,
    make_token: TokenFactory,
    training: FakeTrainingRepository,
    queue: FakeQueue,
    audit: RecordingAudit,
) -> None:
    headers = auth(make_token, WRITE)

    accepted = await client.post(
        "/v1/admin/exports/training-data",
        json={"from": "2026-09-01T00:00:00Z", "to": "2026-09-15T00:00:00Z"},
        headers={**headers, "Idempotency-Key": "train-0001"},
    )

    assert accepted.status_code == 202
    export_id = UUID(accepted.json()["export_id"])
    assert accepted.headers["Location"] == f"/v1/admin/exports/training-data/{export_id}"
    assert queue.queued == [export_id]
    assert training.records[export_id].requested_by == "admin-1"
    assert audit.entries[0].action == "export.training_data"
    assert audit.entries[0].metadata == {
        "from": "2026-09-01T00:00:00+00:00",
        "to": "2026-09-15T00:00:00+00:00",
    }

    training.records[export_id] = replace(
        training.records[export_id],
        status=ExportStatus.READY,
        object_key=f"training/{export_id}.jsonl.gz",
        row_count=12,
        expires_at=T0 + timedelta(days=7),
    )
    status = await client.get(accepted.headers["Location"], headers=headers)

    assert status.status_code == 200
    body = status.json()
    assert (body["status"], body["row_count"]) == ("ready", 12)
    assert body["from"] == "2026-09-01T00:00:00Z"
    assert body["download_url"].startswith("https://storage.example/training/")
    assert audit.entries[-1].action == "export.training_data_read"


async def test_training_export_needs_an_idempotency_key(
    client: AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.post(
        "/v1/admin/exports/training-data", json={}, headers=auth(make_token, WRITE)
    )

    assert response.status_code == 400


async def test_training_export_range_is_bounded(
    client: AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.post(
        "/v1/admin/exports/training-data",
        json={"from": "2024-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers=auth(make_token, WRITE, **{"Idempotency-Key": "train-0002"}),
    )

    assert response.status_code == 422


async def test_training_export_when_the_queue_is_down(
    client: AsyncClient,
    make_token: TokenFactory,
    training: FakeTrainingRepository,
    queue: FakeQueue,
    audit: RecordingAudit,
) -> None:
    queue.down = True

    response = await client.post(
        "/v1/admin/exports/training-data",
        json={},
        headers=auth(make_token, WRITE, **{"Idempotency-Key": "train-0003"}),
    )

    assert response.status_code == 503
    assert [r.status for r in training.records.values()] == [ExportStatus.FAILED]
    assert audit.entries[-1].result is AuditResult.ERROR
