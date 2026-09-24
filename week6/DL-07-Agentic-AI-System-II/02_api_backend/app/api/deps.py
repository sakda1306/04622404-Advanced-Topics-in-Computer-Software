"""Assemble application services for a request (the only api module that sees infrastructure)."""

from __future__ import annotations

from fastapi import Depends, Request

from app.api.auth import get_principal
from app.api.resources import AppResources, get_resources
from app.core.clock import SystemClock
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.security import Principal
from app.infrastructure.audit import SqlAuditWriter
from app.infrastructure.db.repositories.admin import SqlAdminRepository
from app.infrastructure.db.repositories.conversations import SqlConversationRepository
from app.infrastructure.db.repositories.exports import SqlExportRepository
from app.infrastructure.db.repositories.feedback import SqlFeedbackRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.training_exports import SqlTrainingExportRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.infrastructure.db.repositories.users import SqlUserRepository
from app.infrastructure.health import database_ok, redis_ok
from app.services.admin_service import AdminService
from app.services.conversation_service import ConversationService
from app.services.export_service import ExportService
from app.services.feedback_service import FeedbackService
from app.services.job_service import JobService
from app.services.me_service import MeService
from app.services.ops_service import Check, OpsService
from app.services.ports import AuditPort, UserRef
from app.services.recommendation_service import RecommendationService
from app.services.training_export_service import TrainingExportService
from app.services.trip_service import TripService
from app.services.user_service import UserService

log = get_logger(__name__)

_CLOCK = SystemClock()


def _require[T](value: T | None, name: str) -> T:
    if value is None:
        # Wiring error: the resource was not created at startup.
        log.error("resource_missing", resource=name)
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=5)
    return value


def _repository(resources: AppResources) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(_require(resources.sessions, "sessions"))


def get_user_service(request: Request) -> UserService:
    resources = get_resources(request)
    return UserService(_repository(resources), resources.settings.secrets.pseudonym_secret)


async def get_current_user(
    request: Request,
    principal: Principal = Depends(get_principal),
    users: UserService = Depends(get_user_service),
) -> UserRef:
    cached: UserRef | None = getattr(request.state, "user", None)
    if cached is None:
        cached = await users.resolve(principal)
        request.state.user = cached
    return cached


def get_recommendation_service(request: Request) -> RecommendationService:
    resources = get_resources(request)
    return RecommendationService(
        repository=_repository(resources),
        job_state=_require(resources.job_state, "job_state"),
        slots=_require(resources.slots, "slots"),
        cache=_require(resources.cache, "cache"),
        queue=_require(resources.queue, "queue"),
        keys=resources.keys,
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_job_service(request: Request) -> JobService:
    resources = get_resources(request)
    return JobService(
        repository=_repository(resources),
        job_state=_require(resources.job_state, "job_state"),
        slots=_require(resources.slots, "slots"),
        tickets=_require(resources.tickets, "tickets"),
        keys=resources.keys,
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_conversation_service(request: Request) -> ConversationService:
    resources = get_resources(request)
    return ConversationService(
        conversations=SqlConversationRepository(_require(resources.sessions, "sessions")),
        recommendations=get_recommendation_service(request),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_trip_service(request: Request) -> TripService:
    resources = get_resources(request)
    return TripService(
        trips=SqlTripRepository(_require(resources.sessions, "sessions")),
        recommendations=get_recommendation_service(request),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_feedback_service(request: Request) -> FeedbackService:
    resources = get_resources(request)
    sessions = _require(resources.sessions, "sessions")
    return FeedbackService(
        feedback=SqlFeedbackRepository(sessions),
        recommendations=SqlRecommendationRepository(sessions),
        audit=SqlAuditWriter(sessions),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_me_service(request: Request) -> MeService:
    resources = get_resources(request)
    sessions = _require(resources.sessions, "sessions")
    return MeService(
        users=SqlUserRepository(sessions),
        jobs=get_job_service(request),
        user_data=_require(resources.user_data, "user_data"),
        audit=SqlAuditWriter(sessions),
        queue=_require(resources.queue, "queue"),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_export_service(request: Request) -> ExportService:
    resources = get_resources(request)
    return ExportService(
        exports=SqlExportRepository(_require(resources.sessions, "sessions")),
        store=_require(resources.object_store, "object_store"),
        cooldown=_require(resources.cooldown, "cooldown"),
        queue=_require(resources.queue, "queue"),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_ops_service(request: Request) -> OpsService:
    """Works with whatever was created at startup; a missing dependency is reported as down."""
    resources = get_resources(request)
    checks: dict[str, Check] = {}
    if (engine := resources.engine) is not None:
        checks["database"] = lambda: database_ok(engine)
    if (redis := resources.redis) is not None:
        checks["redis"] = lambda: redis_ok(redis.core)
        checks["redis_cache"] = lambda: redis_ok(redis.cache)
    return OpsService(
        checks=checks,
        agent=resources.agent,
        store=resources.service_status,
        settings=resources.settings.observability,
        clock=_CLOCK,
    )


def get_audit(request: Request) -> AuditPort | None:
    """None without a database: a refusal is still a 403, it just goes unrecorded."""
    sessions = get_resources(request).sessions
    return SqlAuditWriter(sessions) if sessions is not None else None


def get_admin_service(request: Request) -> AdminService:
    resources = get_resources(request)
    sessions = _require(resources.sessions, "sessions")
    return AdminService(
        repository=SqlAdminRepository(sessions),
        audit=SqlAuditWriter(sessions),
        settings=resources.settings,
        clock=_CLOCK,
    )


def get_training_export_service(request: Request) -> TrainingExportService:
    resources = get_resources(request)
    sessions = _require(resources.sessions, "sessions")
    return TrainingExportService(
        exports=SqlTrainingExportRepository(sessions),
        store=_require(resources.file_store, "file_store"),
        queue=_require(resources.training_queue, "training_queue"),
        audit=SqlAuditWriter(sessions),
        settings=resources.settings,
        clock=_CLOCK,
    )
