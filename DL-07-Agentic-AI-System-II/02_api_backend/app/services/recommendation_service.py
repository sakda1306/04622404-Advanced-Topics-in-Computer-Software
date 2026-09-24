"""API use case for POST/GET /v1/travel/recommendations (docs/02_api_spec.md 5.1-5.2).

The API never calls the Agent itself (D-03): it stores the request, queues a job and,
in auto/sync mode, waits for the job's final event for at most P-02.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import ERROR_SPECS, AppError, ErrorCode, FieldError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.metrics import CACHE_HITS, CACHE_MISSES, count_recommendation
from app.domain.cache_policy import cache_key, request_is_cacheable
from app.domain.enums import (
    JobStage,
    JobStatus,
    RecommendationStatus,
    RecommendationType,
    RequestMode,
    RequestSource,
    RiskLevel,
    job_type_for,
)
from app.domain.normalization import (
    NormalizationLimits,
    NormalizedTravelRequest,
    TravelRequestInput,
    normalize_travel_request,
)
from app.infrastructure.redis.job_state import JobSnapshot
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import SlotLimiter
from app.services.agent_run_service import staleness_policy
from app.services.pagination import Cursor, Page, build_page, decode_cursor, page_limit
from app.services.ports import (
    CachePort,
    JobQueue,
    JobStatePort,
    NewRecommendation,
    RecommendationRecord,
    RecommendationRepository,
    RecommendationSummaryRecord,
    StoredResult,
    UserRef,
)
from app.services.progress import STAGE_PROGRESS, stage_message
from app.services.recommendation_payload import iso, refresh_freshness

log = get_logger(__name__)

_REDIS_ERRORS = (RedisError, OSError)
_RETRY_AFTER_SECONDS = 5
_MAX_BLOCK_MS = 1000


@dataclass(frozen=True, slots=True)
class CreateRecommendation:
    input: TravelRequestInput
    mode: RequestMode
    conversation_id: UUID | None
    trip_id: UUID | None
    correlation_id: str
    source: RequestSource = RequestSource.RECOMMENDATION


@dataclass(frozen=True, slots=True)
class Finished:
    record: RecommendationRecord


@dataclass(frozen=True, slots=True)
class Accepted:
    job_id: UUID
    recommendation_id: UUID
    conversation_id: UUID


CreateOutcome = Finished | Accepted


def _error_from_event(data: dict[str, Any]) -> AppError:
    raw = data.get("error", {}).get("code")
    known = {code.value for code in ErrorCode}
    code = ErrorCode(raw) if raw in known else ErrorCode.INTERNAL_ERROR
    retry_after = _RETRY_AFTER_SECONDS if code is ErrorCode.DEPENDENCY_UNAVAILABLE else None
    return AppError(code, retry_after=retry_after)


def _cached_result(payload: dict[str, Any], api_version: str) -> StoredResult:
    risk = payload.get("risk") or {}
    action = payload.get("recommendation") or {}
    versions = payload.get("versions") or {}
    valid_until = payload.get("valid_until")
    return StoredResult(
        status=RecommendationStatus.COMPLETED,
        risk_level=RiskLevel(risk["level"]) if risk.get("level") else None,
        risk_score=risk.get("score"),
        risk_confidence=risk.get("confidence"),
        recommendation_type=RecommendationType(action["type"]) if action.get("type") else None,
        payload=payload,
        warning_codes=tuple(w["code"] for w in payload.get("warnings", [])),
        applied_rules=(),
        overall_is_stale=False,
        valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
        api_version=api_version,
        agent_version=versions.get("agent"),
        risk_model_version=versions.get("risk_model"),
        prompt_version=versions.get("prompt"),
        message=action.get("summary"),
    )


class RecommendationService:
    def __init__(
        self,
        *,
        repository: RecommendationRepository,
        job_state: JobStatePort,
        slots: SlotLimiter,
        cache: CachePort,
        queue: JobQueue,
        keys: RedisKeys,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._jobs = job_state
        self._slots = slots
        self._cache = cache
        self._queue = queue
        self._keys = keys
        self._settings = settings
        self._clock = clock
        self._policy = staleness_policy(settings.cache)

    # ------------------------------------------------------------------ queries

    async def get(self, user: UserRef, recommendation_id: UUID) -> RecommendationRecord:
        record = await self._repo.get_recommendation(user.id, recommendation_id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return record

    async def list(
        self,
        user: UserRef,
        *,
        limit: int | None,
        cursor: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        risk_level: RiskLevel | None,
    ) -> Page[RecommendationSummaryRecord]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.list_recommendations(
            user.id,
            limit=size,
            cursor=decode_cursor(cursor),
            created_from=created_from,
            created_to=created_to,
            risk_level=risk_level,
        )
        return build_page(rows, size, key=lambda row: Cursor(row.created_at, row.id))

    # ------------------------------------------------------------------ create

    async def create(self, user: UserRef, command: CreateRecommendation) -> CreateOutcome:
        now = self._clock.now()
        request = self._normalize(command.input, now)
        await self._check_ownership(user, command)
        await self._check_coverage(request)

        key: str | None = None
        if request_is_cacheable(request, has_conversation=command.conversation_id is not None):
            key = cache_key(request, bucket_minutes=self._settings.cache.cache_time_bucket_minutes)
        new = NewRecommendation(
            user_id=user.id,
            request=request,
            mode=command.mode,
            source=command.source,
            conversation_id=command.conversation_id,
            trip_id=command.trip_id,
            cache_key=key,
            correlation_id=command.correlation_id,
            now=now,
            retention_days=self._settings.retention.retention_recommendation_days,
            conversation_days=self._settings.retention.retention_conversation_days,
            job_id=new_id(),
        )
        if key is not None and command.mode is not RequestMode.ASYNC:
            hit = await self._from_cache(user, new, key)
            if hit is not None:
                return hit

        job_id = new.job_id
        assert job_id is not None
        await self._take_slot(user, job_id)
        try:
            created = await self._repo.create_pending(new)
        except BaseException:
            await self._release_slot(user, job_id)
            raise
        await self._start(user, new, job_id, created.recommendation_id, request.language)
        accepted = Accepted(job_id, created.recommendation_id, created.conversation_id)
        if command.mode is RequestMode.ASYNC:
            return accepted
        return await self._wait(user, accepted, command.mode)

    def _normalize(self, raw: TravelRequestInput, now: datetime) -> NormalizedTravelRequest:
        limits = self._settings.limits
        return normalize_travel_request(
            raw,
            now=now,
            limits=NormalizationLimits(
                max_waypoints=limits.max_waypoints,
                max_days_ahead=limits.max_days_ahead,
                max_question_chars=limits.max_question_chars,
                min_distance_m=limits.min_route_distance_meters,
            ),
        )

    async def _check_ownership(self, user: UserRef, command: CreateRecommendation) -> None:
        # Another user's resource is reported exactly like a missing one.
        if command.conversation_id is not None and not await self._repo.conversation_exists(
            user.id, command.conversation_id
        ):
            raise AppError(ErrorCode.NOT_FOUND, detail="The conversation was not found.")
        if command.trip_id is not None and not await self._repo.trip_exists(
            user.id, command.trip_id
        ):
            raise AppError(ErrorCode.NOT_FOUND, detail="The trip was not found.")

    async def _check_coverage(self, request: NormalizedTravelRequest) -> None:
        points = [("origin", request.origin), ("destination", request.destination)]
        points += [(f"waypoints.{i}", p) for i, p in enumerate(request.waypoints)]
        outside = [
            FieldError(field=name, message="outside the service area", code="unsupported_region")
            for name, point in points
            if await self._repo.region_for(point.lat, point.lon) is None
        ]
        if outside:
            raise AppError(ErrorCode.UNSUPPORTED_REGION, errors=outside)

    async def _from_cache(self, user: UserRef, new: NewRecommendation, key: str) -> Finished | None:
        result = await self._cached(key, new)
        if result is None:
            CACHE_MISSES.inc()
            return None
        CACHE_HITS.inc()
        created = await self._repo.create_completed(new, result)
        record = await self._repo.get_recommendation(user.id, created.recommendation_id)
        assert record is not None
        count_recommendation(result.status, result.risk_level, result.recommendation_type)
        log.info("recommendation_cache_hit")
        return Finished(record)

    async def _cached(self, key: str, new: NewRecommendation) -> StoredResult | None:
        cached = await self._cache.get(key)
        if cached is None:
            return None
        payload = refresh_freshness(cached, now=new.now, policy=self._policy)
        if payload is None:
            return None
        try:
            return _cached_result(payload, self._settings.app.api_version)
        except (KeyError, TypeError, ValueError):
            log.warning("cache_entry_invalid")
            return None

    async def _take_slot(self, user: UserRef, job_id: UUID) -> None:
        ttl = int(self._settings.agent.job_agent_timeout_seconds * 2)
        try:
            allowed = await self._slots.acquire(
                self._keys.active_jobs(user.id),
                str(job_id),
                limit=self._settings.limits.max_active_jobs_per_user,
                ttl_seconds=ttl,
            )
        except _REDIS_ERRORS as exc:
            log.warning("active_jobs_unavailable", error_type=type(exc).__name__)
            raise AppError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=_RETRY_AFTER_SECONDS
            ) from exc
        if not allowed:
            raise AppError(ErrorCode.TOO_MANY_ACTIVE_JOBS, retry_after=_RETRY_AFTER_SECONDS)

    async def _release_slot(self, user: UserRef, job_id: UUID) -> None:
        try:
            await self._slots.release(self._keys.active_jobs(user.id), str(job_id))
        except _REDIS_ERRORS as exc:
            log.warning("active_job_release_failed", error_type=type(exc).__name__)

    async def _start(
        self,
        user: UserRef,
        new: NewRecommendation,
        job_id: UUID,
        recommendation_id: UUID,
        language: str,
    ) -> None:
        now = new.now
        try:
            await self._jobs.create(
                JobSnapshot(
                    job_id=job_id,
                    user_id=user.id,
                    type=job_type_for(new.source),
                    status=JobStatus.QUEUED,
                    stage=JobStage.QUEUED,
                    progress=0,
                    recommendation_id=recommendation_id,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await self._jobs.publish(
                job_id,
                "progress",
                {
                    "job_id": str(job_id),
                    "stage": JobStage.QUEUED.value,
                    "progress": STAGE_PROGRESS[JobStage.QUEUED],
                    "message": stage_message(JobStage.QUEUED, language),
                    "at": iso(now),
                },
            )
            task_id = await self._queue.enqueue_recommendation(
                job_id, correlation_id=new.correlation_id
            )
        except Exception as exc:
            log.error("job_enqueue_failed", job_id=str(job_id), error_type=type(exc).__name__)
            await self._abandon(user, job_id)
            raise AppError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=_RETRY_AFTER_SECONDS
            ) from exc
        await self._repo.set_task_id(job_id, task_id)

    async def _abandon(self, user: UserRef, job_id: UUID) -> None:
        code = ErrorCode.DEPENDENCY_UNAVAILABLE
        await self._repo.fail_job(job_id, code.value, self._clock.now())
        await self._release_slot(user, job_id)
        try:
            await self._jobs.update(
                job_id,
                updated_at=self._clock.now(),
                status=JobStatus.FAILED,
                stage=JobStage.FAILED,
                error_code=code.value,
            )
            await self._jobs.publish(
                job_id,
                "failed",
                {
                    "job_id": str(job_id),
                    "error": {"code": code.value, "message": ERROR_SPECS[code].detail},
                },
            )
        except _REDIS_ERRORS:
            pass  # Redis may be the reason we are here; the database has the outcome.

    async def _wait(self, user: UserRef, accepted: Accepted, mode: RequestMode) -> CreateOutcome:
        budget = self._settings.agent.sync_agent_timeout_seconds
        deadline = self._clock.monotonic() + budget
        after = "0-0"
        while (remaining := deadline - self._clock.monotonic()) > 0:
            try:
                events = await self._jobs.read(
                    accepted.job_id,
                    after=after,
                    block_ms=max(1, min(_MAX_BLOCK_MS, int(remaining * 1000))),
                )
            except _REDIS_ERRORS as exc:
                log.warning("job_wait_unavailable", error_type=type(exc).__name__)
                break
            for event in events:
                after = event.id
                if event.event == "completed":
                    return Finished(await self.get(user, accepted.recommendation_id))
                if event.terminal:
                    raise _error_from_event(event.data)
        if mode is RequestMode.SYNC:
            # The job keeps running; its result appears in the history (D-44).
            raise AppError(ErrorCode.AGENT_TIMEOUT)
        return accepted
