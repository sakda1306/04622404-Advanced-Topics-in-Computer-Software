"""Per-process resources for Celery tasks (D-20, D-50).

Tasks are synchronous; each worker process keeps one event loop (asyncio.Runner) so the
database pool, Redis clients and HTTP client created on first use can be reused.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.core.ids import correlation_id_var, new_id
from app.infrastructure.agent.factory import build_agent_client
from app.infrastructure.audit import SqlAuditWriter
from app.infrastructure.db.repositories.exports import SqlExportRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.retention import (
    EXPORT_TABLES,
    PURGE_ORDER,
    SqlRetentionRepository,
)
from app.infrastructure.db.repositories.training_exports import SqlTrainingExportRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.infrastructure.db.repositories.users import SqlUserRepository
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.queue import CeleryJobQueue
from app.infrastructure.redis.cache import RedisRecommendationCache
from app.infrastructure.redis.clients import RedisClients, create_redis_clients
from app.infrastructure.redis.cooldown import RedisCooldown
from app.infrastructure.redis.job_state import RedisJobStateStore
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.service_status import RedisServiceStatusStore
from app.infrastructure.redis.slots import RedisSlotLimiter
from app.infrastructure.storage.object_store import MinioObjectStore
from app.services.account_service import AccountService
from app.services.agent_run_service import AgentRunService
from app.services.export_service import ExportService
from app.services.purge_service import PurgeService
from app.services.reaper_service import ReaperService
from app.services.recommendation_service import RecommendationService
from app.services.training_export_service import TrainingExportService
from app.services.trip_alert_service import TripAlertService
from app.services.trip_service import TripService
from app.workers.celery_app import get_celery


@dataclass
class WorkerResources:
    engine: AsyncEngine
    redis: RedisClients
    http: httpx.AsyncClient
    service: AgentRunService
    alerts: TripAlertService
    reaper: ReaperService
    accounts: AccountService
    exports: ExportService | None
    purge: PurgeService
    training: TrainingExportService | None

    async def aclose(self) -> None:
        await self.http.aclose()
        await self.redis.aclose()
        await self.engine.dispose()


def build_worker_resources(settings: Settings) -> WorkerResources:
    engine = create_engine(settings.db)
    redis = create_redis_clients(settings.redis)
    keys = RedisKeys(settings.app.app_env.value)
    http = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
    sessions = create_session_factory(engine)
    repository = SqlRecommendationRepository(sessions)
    job_state = RedisJobStateStore(
        redis.core, keys, ttl_seconds=settings.jobs.job_result_ttl_seconds
    )
    slots = RedisSlotLimiter(redis.core)
    cache = RedisRecommendationCache(redis.cache, keys)
    clock = SystemClock()
    service = AgentRunService(
        repository=repository,
        agent=build_agent_client(settings, http, redis.core, keys),
        job_state=job_state,
        slots=slots,
        cache=cache,
        keys=keys,
        settings=settings,
        clock=clock,
        service_reports=RedisServiceStatusStore(redis.cache, keys),
    )
    # Scheduled re-assessments are queued like API requests and run by run_recommendation.
    trips = SqlTripRepository(sessions)
    queue = CeleryJobQueue(get_celery())
    recommendations = RecommendationService(
        repository=repository,
        job_state=job_state,
        slots=slots,
        cache=cache,
        queue=queue,
        keys=keys,
        settings=settings,
        clock=clock,
    )
    alerts = TripAlertService(
        trips=trips,
        trip_service=TripService(
            trips=trips, recommendations=recommendations, settings=settings, clock=clock
        ),
        settings=settings,
        clock=clock,
    )
    users = SqlUserRepository(sessions)
    export_rows = SqlExportRepository(sessions)
    training_rows = SqlTrainingExportRepository(sessions)
    store = MinioObjectStore(settings.storage) if settings.storage.enabled else None
    cooldown = RedisCooldown(redis.core, keys)
    audit = SqlAuditWriter(sessions)
    reaper = ReaperService(
        recommendations=repository,
        users=users,
        job_state=job_state,
        slots=slots,
        queue=queue,
        keys=keys,
        settings=settings,
        clock=clock,
        exports=export_rows,
        training_exports=training_rows,
    )
    accounts = AccountService(users=users, audit=audit, exports=export_rows, store=store)
    exports = None
    if store is not None:
        exports = ExportService(
            exports=export_rows,
            store=store,
            cooldown=cooldown,
            queue=queue,
            settings=settings,
            clock=clock,
        )
    purge = PurgeService(
        retention=SqlRetentionRepository(sessions),
        tables=PURGE_ORDER,
        store=store,
        export_tables=EXPORT_TABLES,
        audit=audit,
        lock=cooldown,
        settings=settings,
        clock=clock,
    )
    training = None
    if store is not None:
        training = TrainingExportService(
            exports=training_rows,
            store=store,
            queue=queue,
            audit=audit,
            settings=settings,
            clock=clock,
        )
    return WorkerResources(
        engine, redis, http, service, alerts, reaper, accounts, exports, purge, training
    )


class WorkerRuntime:
    def __init__(self) -> None:
        self._runner: asyncio.Runner | None = None
        self._resources: WorkerResources | None = None

    def _call[T](self, work: Coroutine[Any, Any, T]) -> T:
        if self._runner is None:
            self._runner = asyncio.Runner()
        # Runner.run() would otherwise reuse the context of its first call, so the
        # correlation id and log context of an earlier task would leak into this one.
        return self._runner.run(work, context=contextvars.copy_context())

    def run_recommendation(self, job_id: UUID) -> str | None:
        return self._call(self._run(job_id))

    def scan_trip_alerts(self) -> dict[str, int]:
        return self._call(self._scan())

    def reap_stuck_jobs(self) -> dict[str, int]:
        return self._call(self._reap())

    def delete_account(self, user_id: UUID) -> bool:
        return self._call(self._delete(user_id))

    def build_data_export(self, export_id: UUID) -> bool:
        return self._call(self._export(export_id))

    def purge_expired(self) -> dict[str, int]:
        return self._call(self._purge())

    def build_training_export(self, export_id: UUID) -> bool:
        return self._call(self._training(export_id))

    def _get_resources(self) -> WorkerResources:
        if self._resources is None:
            self._resources = build_worker_resources(get_settings())
        return self._resources

    async def _run(self, job_id: UUID) -> str | None:
        status = await self._get_resources().service.run(job_id)
        return status.value if status is not None else None

    async def _scan(self) -> dict[str, int]:
        result = await self._get_resources().alerts.scan()
        return {"queued": result.queued, "skipped": result.skipped}

    async def _reap(self) -> dict[str, int]:
        result = await self._get_resources().reaper.run()
        return {"reaped": result.reaped, "deletions_requeued": result.deletions_requeued}

    async def _delete(self, user_id: UUID) -> bool:
        correlation = correlation_id_var.get() or str(new_id())
        return await self._get_resources().accounts.delete(user_id, correlation_id=correlation)

    async def _export(self, export_id: UUID) -> bool:
        exports = self._get_resources().exports
        if exports is None:
            # Configuration error: object storage is missing in the worker.
            return False
        return await exports.build(export_id)

    async def _training(self, export_id: UUID) -> bool:
        training = self._get_resources().training
        if training is None:
            # Configuration error: object storage is missing in the worker.
            return False
        return await training.build(export_id)

    async def _purge(self) -> dict[str, int]:
        result = await self._get_resources().purge.run()
        return {
            "deleted": sum(result.deleted.values()),
            "exports_expired": result.exports_expired,
            "partitions_created": result.partitions_created,
            "partitions_dropped": result.partitions_dropped,
        }

    def close(self) -> None:
        if self._runner is None:
            return
        if self._resources is not None:
            self._runner.run(self._resources.aclose())
            self._resources = None
        self._runner.close()
        self._runner = None


runtime = WorkerRuntime()
