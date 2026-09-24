"""Celery wiring: configuration, the task entry point and the enqueue adapter."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.ids import correlation_id_var, new_id
from app.infrastructure.queue import CeleryJobQueue
from app.workers import celery_app as celery_module
from app.workers.celery_app import (
    ALERT_QUEUE,
    BUILD_DATA_EXPORT,
    BUILD_TRAINING_EXPORT,
    DELETE_ACCOUNT,
    MAINTENANCE_QUEUE,
    PURGE_EXPIRED,
    REAP_STUCK_JOBS,
    RECOMMENDATION_QUEUE,
    RUN_RECOMMENDATION,
    SCAN_TRIP_ALERTS,
    create_celery,
)
from app.workers.runtime import WorkerRuntime
from app.workers.schedule import beat_schedule
from app.workers.tasks import maintenance as maintenance_module
from app.workers.tasks import recommendation as task_module
from app.workers.tasks import trip_alerts as alert_module


def test_celery_configuration(settings: Settings) -> None:
    app = create_celery(settings)

    conf = app.conf
    assert conf.broker_url == "redis://localhost:6379/2"
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_ignore_result is True
    assert conf.accept_content == ["json"]
    assert conf.task_default_queue == RECOMMENDATION_QUEUE
    assert conf.task_routes[RUN_RECOMMENDATION] == {"queue": RECOMMENDATION_QUEUE}
    assert conf.task_routes[SCAN_TRIP_ALERTS] == {"queue": ALERT_QUEUE}
    assert "app.workers.tasks.trip_alerts" in conf.include
    assert "app.workers.tasks.maintenance" in conf.include
    assert conf.task_routes[REAP_STUCK_JOBS] == {"queue": MAINTENANCE_QUEUE}
    assert conf.task_routes[DELETE_ACCOUNT] == {"queue": MAINTENANCE_QUEUE}
    assert conf.task_routes[BUILD_DATA_EXPORT] == {"queue": MAINTENANCE_QUEUE}
    assert conf.task_routes[PURGE_EXPIRED] == {"queue": MAINTENANCE_QUEUE}
    assert conf.task_routes[BUILD_TRAINING_EXPORT] == {"queue": MAINTENANCE_QUEUE}
    assert str(conf.timezone) == "Asia/Bangkok"
    assert conf.enable_utc is True
    assert conf.beat_schedule == beat_schedule(settings)
    # Our JSON logs go to the real stdout; the redirect proxy would swallow them.
    assert conf.worker_redirect_stdouts is False


def test_module_exposes_a_configured_app_with_the_task() -> None:
    celery_module.get_celery.cache_clear()

    app = celery_module.celery_app

    assert RUN_RECOMMENDATION in app.tasks
    assert SCAN_TRIP_ALERTS in app.tasks
    assert REAP_STUCK_JOBS in app.tasks
    assert DELETE_ACCOUNT in app.tasks
    with pytest.raises(AttributeError):
        _ = celery_module.not_there


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str | None]] = []

    def run_recommendation(self, job_id: UUID) -> str | None:
        self.calls.append((job_id, correlation_id_var.get()))
        return "succeeded"


def test_task_runs_the_job_with_its_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    monkeypatch.setattr(task_module, "runtime", runtime)
    job_id = new_id()

    result = task_module.run_recommendation(str(job_id), correlation_id="corr-42")

    assert result == "succeeded"
    assert runtime.calls == [(job_id, "corr-42")]
    assert correlation_id_var.get() is None


@pytest.mark.parametrize("correlation_id", [None, "bad id with spaces"])
def test_unsafe_correlation_id_is_replaced(
    monkeypatch: pytest.MonkeyPatch, correlation_id: str | None
) -> None:
    runtime = FakeRuntime()
    monkeypatch.setattr(task_module, "runtime", runtime)
    job_id = new_id()

    task_module.run_recommendation(str(job_id), correlation_id=correlation_id)

    assert runtime.calls[0][1] == str(job_id)


def test_invalid_job_id_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    monkeypatch.setattr(task_module, "runtime", runtime)

    assert task_module.run_recommendation("not-a-uuid") is None
    assert runtime.calls == []


class FakeCelery:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send_task(self, name: str, **options: Any) -> Any:
        self.sent.append((name, options))
        return type("Result", (), {"id": "task-123"})()


async def test_queue_sends_only_ids() -> None:
    celery = FakeCelery()
    job_id = new_id()

    task_id = await CeleryJobQueue(celery).enqueue_recommendation(  # type: ignore[arg-type]
        job_id, correlation_id="corr-1"
    )

    assert task_id == "task-123"
    name, options = celery.sent[0]
    assert name == RUN_RECOMMENDATION
    assert options["kwargs"] == {"job_id": str(job_id), "correlation_id": "corr-1"}
    assert options["queue"] == RECOMMENDATION_QUEUE
    assert options["retry_policy"]["max_retries"] <= 3


def test_runtime_runs_each_job_in_the_callers_context(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = WorkerRuntime()
    seen: list[str | None] = []

    async def fake_run(job_id: UUID) -> str | None:
        seen.append(correlation_id_var.get())
        return None

    monkeypatch.setattr(runtime, "_run", fake_run)
    try:
        for value in ("first", "second"):
            token = correlation_id_var.set(value)
            try:
                runtime.run_recommendation(new_id())
            finally:
                correlation_id_var.reset(token)
    finally:
        runtime.close()

    assert seen == ["first", "second"]


def test_beat_schedule_follows_the_scan_interval(settings: Settings) -> None:
    trips = settings.trips.model_copy(update={"trip_alert_scan_minutes": 5})
    changed = settings.model_copy(update={"trips": trips})

    entry = beat_schedule(changed)["scan-trip-alerts"]

    assert entry["task"] == SCAN_TRIP_ALERTS
    assert entry["schedule"] == timedelta(minutes=5)
    # A run that waited longer than one interval is dropped; the next one covers it.
    assert entry["options"] == {"queue": ALERT_QUEUE, "expires": 300}


class FakeAlertRuntime:
    def __init__(self) -> None:
        self.correlation_ids: list[str | None] = []

    def scan_trip_alerts(self) -> dict[str, int]:
        self.correlation_ids.append(correlation_id_var.get())
        return {"queued": 2, "skipped": 1}


def test_scan_task_runs_with_its_own_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeAlertRuntime()
    monkeypatch.setattr(alert_module, "runtime", runtime)

    assert alert_module.scan_trip_alerts() == {"queued": 2, "skipped": 1}
    alert_module.scan_trip_alerts()

    first, second = runtime.correlation_ids
    assert first
    assert second
    assert first != second
    assert correlation_id_var.get() is None


def test_runtime_scans_in_the_callers_context(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = WorkerRuntime()
    seen: list[str | None] = []

    async def fake_scan() -> dict[str, int]:
        seen.append(correlation_id_var.get())
        return {"queued": 0, "skipped": 0}

    monkeypatch.setattr(runtime, "_scan", fake_scan)
    token = correlation_id_var.set("scan-1")
    try:
        assert runtime.scan_trip_alerts() == {"queued": 0, "skipped": 0}
    finally:
        correlation_id_var.reset(token)
        runtime.close()

    assert seen == ["scan-1"]


def test_beat_schedule_runs_the_reaper(settings: Settings) -> None:
    maintenance = settings.maintenance.model_copy(update={"reaper_interval_minutes": 2})
    changed = settings.model_copy(update={"maintenance": maintenance})

    entry = beat_schedule(changed)["reap-stuck-jobs"]

    assert entry["task"] == REAP_STUCK_JOBS
    assert entry["schedule"] == timedelta(minutes=2)
    assert entry["options"] == {"queue": MAINTENANCE_QUEUE, "expires": 120}


class FakeMaintenanceRuntime:
    def __init__(self) -> None:
        self.reaps: list[str | None] = []
        self.deleted: list[tuple[UUID, str | None]] = []

    def reap_stuck_jobs(self) -> dict[str, int]:
        self.reaps.append(correlation_id_var.get())
        return {"reaped": 1, "deletions_requeued": 0}

    def delete_account(self, user_id: UUID) -> bool:
        self.deleted.append((user_id, correlation_id_var.get()))
        return True


def test_reaper_task_has_its_own_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeMaintenanceRuntime()
    monkeypatch.setattr(maintenance_module, "runtime", runtime)

    assert maintenance_module.reap_stuck_jobs() == {"reaped": 1, "deletions_requeued": 0}

    assert runtime.reaps[0]
    assert correlation_id_var.get() is None


def test_delete_account_task(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeMaintenanceRuntime()
    monkeypatch.setattr(maintenance_module, "runtime", runtime)
    user_id = new_id()

    assert maintenance_module.delete_account(str(user_id), correlation_id="corr-7") is True
    assert maintenance_module.delete_account("not-a-uuid") is False

    assert runtime.deleted == [(user_id, "corr-7")]


async def test_queue_sends_account_deletions_to_maintenance() -> None:
    celery = FakeCelery()
    user_id = new_id()

    await CeleryJobQueue(celery).enqueue_account_deletion(  # type: ignore[arg-type]
        user_id, correlation_id="corr-2"
    )

    name, options = celery.sent[0]
    assert name == DELETE_ACCOUNT
    assert options["kwargs"] == {"user_id": str(user_id), "correlation_id": "corr-2"}
    assert options["queue"] == MAINTENANCE_QUEUE


def test_runtime_runs_maintenance_in_the_callers_context(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = WorkerRuntime()
    seen: list[str | None] = []

    async def fake_reap() -> dict[str, int]:
        seen.append(correlation_id_var.get())
        return {"reaped": 0, "deletions_requeued": 0}

    async def fake_delete(user_id: UUID) -> bool:
        seen.append(correlation_id_var.get())
        return True

    monkeypatch.setattr(runtime, "_reap", fake_reap)
    monkeypatch.setattr(runtime, "_delete", fake_delete)
    token = correlation_id_var.set("maint-1")
    try:
        runtime.reap_stuck_jobs()
        assert runtime.delete_account(new_id()) is True
    finally:
        correlation_id_var.reset(token)
        runtime.close()

    assert seen == ["maint-1", "maint-1"]


def test_purge_runs_on_the_configured_cron(settings: Settings) -> None:
    retention = settings.retention.model_copy(update={"purge_cron": "30 2 * * 1"})
    changed = settings.model_copy(update={"retention": retention})

    entry = beat_schedule(changed)["purge-expired"]

    assert entry["task"] == PURGE_EXPIRED
    assert entry["options"]["queue"] == MAINTENANCE_QUEUE
    schedule = entry["schedule"]
    assert schedule.minute == {30}
    assert schedule.hour == {2}
    assert schedule.day_of_week == {1}


class FakeExportRuntime:
    def __init__(self) -> None:
        self.built: list[tuple[UUID, str | None]] = []

    def build_data_export(self, export_id: UUID) -> bool:
        self.built.append((export_id, correlation_id_var.get()))
        return True

    def purge_expired(self) -> dict[str, int]:
        return {"deleted": 3}

    def build_training_export(self, export_id: UUID) -> bool:
        self.built.append((export_id, correlation_id_var.get()))
        return True


def test_export_and_purge_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeExportRuntime()
    monkeypatch.setattr(maintenance_module, "runtime", runtime)
    export_id = new_id()

    assert maintenance_module.build_data_export(str(export_id), correlation_id="corr-9") is True
    assert maintenance_module.build_data_export("nope") is False
    assert maintenance_module.purge_expired() == {"deleted": 3}
    assert maintenance_module.build_training_export(str(export_id), correlation_id="corr-8")
    assert maintenance_module.build_training_export("nope") is False

    assert runtime.built == [(export_id, "corr-9"), (export_id, "corr-8")]


async def test_queue_sends_exports_to_maintenance() -> None:
    celery = FakeCelery()
    export_id = new_id()

    await CeleryJobQueue(celery).enqueue_data_export(  # type: ignore[arg-type]
        export_id, correlation_id="corr-3"
    )

    name, options = celery.sent[0]
    assert name == BUILD_DATA_EXPORT
    assert options["kwargs"] == {"export_id": str(export_id), "correlation_id": "corr-3"}
    assert options["queue"] == MAINTENANCE_QUEUE


async def test_queue_sends_training_exports_to_maintenance() -> None:
    celery = FakeCelery()
    export_id = new_id()

    await CeleryJobQueue(celery).enqueue_training_export(  # type: ignore[arg-type]
        export_id, correlation_id="corr-4"
    )

    name, options = celery.sent[0]
    assert name == BUILD_TRAINING_EXPORT
    assert options["kwargs"] == {"export_id": str(export_id), "correlation_id": "corr-4"}
    assert options["queue"] == MAINTENANCE_QUEUE
