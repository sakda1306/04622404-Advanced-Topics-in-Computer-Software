"""Wiring for recommendation-flow tests: PostGIS, fakeredis and the mock Agent in-process."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from fakeredis import FakeAsyncRedis

from app.core.clock import SystemClock
from app.core.config import Settings
from app.domain.enums import JobStage, JobStatus, JobType, TravelMode
from app.domain.normalization import GeoPoint, TravelPreferences, TravelRequestInput
from app.infrastructure.agent.auth import NoAuth
from app.infrastructure.agent.circuit_breaker import RedisCircuitBreaker
from app.infrastructure.agent.client import AgentClient
from app.infrastructure.audit import SqlAuditWriter
from app.infrastructure.db.repositories.admin import SqlAdminRepository
from app.infrastructure.db.repositories.conversations import SqlConversationRepository
from app.infrastructure.db.repositories.exports import SqlExportRepository
from app.infrastructure.db.repositories.feedback import SqlFeedbackRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.retention import (
    EXPORT_TABLES,
    PURGE_ORDER,
    SqlRetentionRepository,
)
from app.infrastructure.db.repositories.training_exports import SqlTrainingExportRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.infrastructure.db.repositories.users import SqlUserRepository
from app.infrastructure.redis.cache import RedisRecommendationCache
from app.infrastructure.redis.cooldown import RedisCooldown
from app.infrastructure.redis.job_state import JobSnapshot, RedisJobStateStore
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.service_status import RedisServiceStatusStore
from app.infrastructure.redis.slots import RedisSlotLimiter
from app.infrastructure.redis.tickets import RedisTicketStore
from app.infrastructure.redis.user_data import RedisUserData
from app.services.account_service import AccountService
from app.services.admin_service import AdminService
from app.services.agent_run_service import AgentRunService
from app.services.conversation_service import ConversationService
from app.services.export_service import ExportService
from app.services.feedback_service import FeedbackService
from app.services.job_service import JobService
from app.services.me_service import MeService
from app.services.ports import NewRecommendation, UserRef
from app.services.purge_service import PurgeService
from app.services.reaper_service import ReaperService
from app.services.recommendation_service import RecommendationService
from app.services.training_export_service import TrainingExportService
from app.services.trip_alert_service import TripAlertService
from app.services.trip_service import TripService
from mock_agent.main import MockState, create_app
from tests.support.storage import MemoryObjectStore

AGENT_URL = "http://mock-agent"


def tune(settings: Settings, **groups: dict[str, Any]) -> Settings:
    """Copy settings with some fields of the named groups changed."""
    updates = {
        name: getattr(settings, name).model_copy(update=values) for name, values in groups.items()
    }
    return settings.model_copy(update=updates)


def travel_input(**changes: Any) -> TravelRequestInput:
    values: dict[str, Any] = {
        "origin": GeoPoint(13.7563, 100.5018, name="Bangkok"),
        "destination": GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
        "departure_time": datetime.now(UTC) + timedelta(days=2),
        "timezone": "Asia/Bangkok",
        "language": "en",
        "preferences": TravelPreferences(travel_modes=(TravelMode.TRAIN,)),
    }
    values.update(changes)
    return TravelRequestInput(**values)


class InlineQueue:
    """Runs the worker use case in a background task, like a Celery worker would."""

    def __init__(self) -> None:
        self.worker: Callable[[UUID], Coroutine[Any, Any, object]] | None = None
        self.tasks: list[asyncio.Task[object]] = []
        self.enqueued: list[tuple[UUID, str]] = []
        self.fail = False
        self.failed: list[tuple[UUID, str]] = []
        self.deletions: list[tuple[UUID, str]] = []
        self.exports: list[tuple[UUID, str]] = []
        self.training: list[tuple[UUID, str]] = []

    async def enqueue_recommendation(self, job_id: UUID, *, correlation_id: str) -> str:
        if self.fail:
            self.failed.append((job_id, correlation_id))
            raise ConnectionError("broker down")
        self.enqueued.append((job_id, correlation_id))
        if self.worker is not None:
            self.tasks.append(asyncio.create_task(self.worker(job_id)))
        return f"task-{len(self.enqueued)}"

    async def enqueue_account_deletion(self, user_id: UUID, *, correlation_id: str) -> str:
        self.deletions.append((user_id, correlation_id))
        return f"delete-{len(self.deletions)}"

    async def enqueue_data_export(self, export_id: UUID, *, correlation_id: str) -> str:
        self.exports.append((export_id, correlation_id))
        return f"export-{len(self.exports)}"

    async def enqueue_training_export(self, export_id: UUID, *, correlation_id: str) -> str:
        self.training.append((export_id, correlation_id))
        return f"training-{len(self.training)}"

    async def drain(self) -> None:
        await asyncio.gather(*self.tasks)


@dataclass
class Flow:
    settings: Settings
    repo: SqlRecommendationRepository
    redis: FakeAsyncRedis
    keys: RedisKeys
    jobs: RedisJobStateStore
    slots: RedisSlotLimiter
    tickets: RedisTicketStore
    cache: RedisRecommendationCache
    agent_state: MockState
    agent: AgentClient
    queue: InlineQueue = field(default_factory=InlineQueue)
    store: MemoryObjectStore = field(default_factory=MemoryObjectStore)

    def worker(self, settings: Settings | None = None) -> AgentRunService:
        return AgentRunService(
            repository=self.repo,
            agent=self.agent,
            job_state=self.jobs,
            slots=self.slots,
            cache=self.cache,
            keys=self.keys,
            settings=settings or self.settings,
            clock=SystemClock(),
            service_reports=RedisServiceStatusStore(self.redis, self.keys),
        )

    def recommendations(self, settings: Settings | None = None) -> RecommendationService:
        """API use case whose queue runs the worker in-process."""
        chosen = settings or self.settings
        self.queue.worker = self.worker(chosen).run
        return RecommendationService(
            repository=self.repo,
            job_state=self.jobs,
            slots=self.slots,
            cache=self.cache,
            queue=self.queue,
            keys=self.keys,
            settings=chosen,
            clock=SystemClock(),
        )

    def conversations(self, settings: Settings | None = None) -> ConversationService:
        chosen = settings or self.settings
        return ConversationService(
            conversations=SqlConversationRepository(self.repo.sessions),
            recommendations=self.recommendations(chosen),
            settings=chosen,
            clock=SystemClock(),
        )

    def trips(self, settings: Settings | None = None) -> TripService:
        chosen = settings or self.settings
        return TripService(
            trips=SqlTripRepository(self.repo.sessions),
            recommendations=self.recommendations(chosen),
            settings=chosen,
            clock=SystemClock(),
        )

    def trip_alerts(self, settings: Settings | None = None) -> TripAlertService:
        chosen = settings or self.settings
        return TripAlertService(
            trips=SqlTripRepository(self.repo.sessions),
            trip_service=self.trips(chosen),
            settings=chosen,
            clock=SystemClock(),
        )

    def jobs_service(self) -> JobService:
        return JobService(
            repository=self.repo,
            job_state=self.jobs,
            slots=self.slots,
            tickets=self.tickets,
            keys=self.keys,
            settings=self.settings,
            clock=SystemClock(),
        )

    def me(self, settings: Settings | None = None) -> MeService:
        chosen = settings or self.settings
        return MeService(
            users=SqlUserRepository(self.repo.sessions),
            jobs=self.jobs_service(),
            user_data=RedisUserData(self.redis, self.keys),
            audit=SqlAuditWriter(self.repo.sessions),
            queue=self.queue,
            settings=chosen,
            clock=SystemClock(),
        )

    def account(self) -> AccountService:
        return AccountService(
            users=SqlUserRepository(self.repo.sessions),
            audit=SqlAuditWriter(self.repo.sessions),
            exports=SqlExportRepository(self.repo.sessions),
            store=self.store,
        )

    def exports(self, settings: Settings | None = None) -> ExportService:
        return ExportService(
            exports=SqlExportRepository(self.repo.sessions),
            store=self.store,
            cooldown=RedisCooldown(self.redis, self.keys),
            queue=self.queue,
            settings=settings or self.settings,
            clock=SystemClock(),
        )

    def admin(self) -> AdminService:
        return AdminService(
            repository=SqlAdminRepository(self.repo.sessions),
            audit=SqlAuditWriter(self.repo.sessions),
            settings=self.settings,
            clock=SystemClock(),
        )

    def training(self) -> TrainingExportService:
        return TrainingExportService(
            exports=SqlTrainingExportRepository(self.repo.sessions),
            store=self.store,
            queue=self.queue,
            audit=SqlAuditWriter(self.repo.sessions),
            settings=self.settings,
            clock=SystemClock(),
        )

    def purge(self) -> PurgeService:
        return PurgeService(
            retention=SqlRetentionRepository(self.repo.sessions),
            tables=PURGE_ORDER,
            store=self.store,
            export_tables=EXPORT_TABLES,
            audit=SqlAuditWriter(self.repo.sessions),
            lock=RedisCooldown(self.redis, self.keys),
            settings=self.settings,
            clock=SystemClock(),
        )

    def reaper(self, settings: Settings | None = None) -> ReaperService:
        return ReaperService(
            recommendations=self.repo,
            users=SqlUserRepository(self.repo.sessions),
            job_state=self.jobs,
            slots=self.slots,
            queue=self.queue,
            keys=self.keys,
            settings=settings or self.settings,
            clock=SystemClock(),
            training_exports=SqlTrainingExportRepository(self.repo.sessions),
        )

    def feedback(self) -> FeedbackService:
        return FeedbackService(
            feedback=SqlFeedbackRepository(self.repo.sessions),
            recommendations=self.repo,
            audit=SqlAuditWriter(self.repo.sessions),
            settings=self.settings,
            clock=SystemClock(),
        )

    async def user(self) -> UserRef:
        return await self.repo.get_or_create_user(
            "http://testserver/dev-issuer",
            f"sub-{uuid4()}",
            # Opaque like the real HMAC pseudonym, so leaks of the user id are detectable.
            pseudonym=lambda uid: hashlib.sha256(uid.bytes).hexdigest(),
        )

    async def queued_job(self, new: NewRecommendation) -> tuple[UUID, UUID]:
        """What the API does before enqueueing: rows, Redis state and the active slot."""
        created = await self.repo.create_pending(new)
        assert created.job_id is not None
        await self.jobs.create(
            JobSnapshot(
                job_id=created.job_id,
                user_id=new.user_id,
                type=JobType.RECOMMENDATION,
                status=JobStatus.QUEUED,
                stage=JobStage.QUEUED,
                progress=0,
                recommendation_id=created.recommendation_id,
                error_code=None,
                created_at=new.now,
                updated_at=new.now,
            )
        )
        await self.slots.acquire(
            self.keys.active_jobs(new.user_id), str(created.job_id), limit=10, ttl_seconds=120
        )
        return created.job_id, created.recommendation_id


def build_agent(state: MockState, redis: FakeAsyncRedis, settings: Settings) -> AgentClient:
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(state)), base_url=AGENT_URL
    )
    return AgentClient(
        http,
        settings=settings.agent.model_copy(update={"agent_service_url": AGENT_URL}),
        tokens=NoAuth(),
        breaker=RedisCircuitBreaker(
            redis, name="cb:test", failure_threshold=50, window_seconds=30, reset_seconds=30
        ),
    )
