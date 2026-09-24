"""Worker use case: call the Agent, apply the safety rules, store and announce the result.

The worker is the only caller of the Agent (D-03). Every outcome ends the job with a
final event, so waiting API requests and SSE clients always learn the result.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError

from app.core.clock import Clock
from app.core.config import CacheSettings, Settings
from app.core.errors import ERROR_SPECS, ErrorCode
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.metrics import (
    JOBS,
    SAFETY_OVERRIDES,
    SAFETY_REJECTIONS,
    count_recommendation,
)
from app.domain.cache_policy import cache_ttl_seconds, result_is_cacheable
from app.domain.enums import (
    AgentRunStatus,
    DataCategory,
    JobStage,
    JobStatus,
    RiskLevel,
)
from app.domain.freshness import StalenessPolicy
from app.domain.normalization import GeoPoint
from app.domain.prediction import PredictionData, build_prediction
from app.domain.safety_gate import SafetyGateRejection
from app.infrastructure.agent.client import AgentCallError, AttemptRecord
from app.infrastructure.agent.contracts import (
    AgentContext,
    AgentLimits,
    AgentLocation,
    AgentMessage,
    AgentRunRequest,
    AgentRunResponse,
    AgentTravelRequest,
    AgentUserProfile,
    IntentHint,
    ProgressLine,
)
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import SlotLimiter
from app.services.ports import (
    AgentPort,
    AgentRunRecord,
    CachePort,
    JobOutcome,
    JobStatePort,
    RecommendationRepository,
    ServiceReportPort,
    StoredResult,
    WorkItem,
)
from app.services.progress import STAGE_PROGRESS, stage_message
from app.services.recommendation_payload import assess, iso

log = get_logger(__name__)

_AGENT_STAGES = frozenset(
    {JobStage.FETCHING_DATA, JobStage.ASSESSING_RISK, JobStage.GENERATING_ADVICE}
)
_REDIS_ERRORS = (RedisError, OSError)
# How often a running job checks whether the user cancelled it (D-72).
CANCEL_POLL_SECONDS = 1.0


def staleness_policy(settings: CacheSettings) -> StalenessPolicy:
    return StalenessPolicy(
        max_age={
            DataCategory.WEATHER: timedelta(minutes=settings.stale_weather_minutes),
            DataCategory.DISASTER: timedelta(minutes=settings.stale_disaster_minutes),
            DataCategory.TRANSPORT: timedelta(minutes=settings.stale_transport_minutes),
        }
    )


def result_url(recommendation_id: UUID) -> str:
    return f"/v1/travel/recommendations/{recommendation_id}"


def _location(point: GeoPoint) -> AgentLocation:
    return AgentLocation(lat=point.lat, lon=point.lon, name=point.name, place_id=point.place_id)


def _run_record(
    run_id: UUID,
    attempt: int,
    attempts: tuple[AttemptRecord, ...],
    response: AgentRunResponse | None = None,
    *,
    rejected_by: str | None = None,
) -> AgentRunRecord | None:
    if not attempts:
        return None
    last = attempts[-1]
    diagnostics = response.diagnostics if response is not None else None
    return AgentRunRecord(
        run_id=run_id,
        attempt=attempt,
        status=AgentRunStatus.BAD_RESPONSE if rejected_by else last.status,
        http_status=last.http_status,
        error_code=rejected_by or last.error_code,
        started_at=attempts[0].started_at,
        finished_at=last.finished_at,
        tool_calls=diagnostics.tool_calls if diagnostics else None,
        agent_version=response.versions.agent if response is not None else None,
        trace_id=diagnostics.trace_id if diagnostics else None,
    )


class _Progress:
    """Publishes a stage once, in the request language."""

    def __init__(self, service: AgentRunService, item: WorkItem) -> None:
        self._service = service
        self._item = item
        self._last: JobStage | None = None

    async def stage(self, stage: JobStage, *, status: JobStatus | None = None) -> None:
        if stage is self._last:
            return
        self._last = stage
        await self._service._set_stage(self._item, stage, status=status)

    async def from_agent(self, line: ProgressLine) -> None:
        if line.stage in _AGENT_STAGES:
            await self.stage(line.stage)


class AgentRunService:
    def __init__(
        self,
        *,
        repository: RecommendationRepository,
        agent: AgentPort,
        job_state: JobStatePort,
        slots: SlotLimiter,
        cache: CachePort,
        keys: RedisKeys,
        settings: Settings,
        clock: Clock,
        service_reports: ServiceReportPort | None = None,
    ) -> None:
        self._repo = repository
        self._agent = agent
        self._reports = service_reports
        self._jobs = job_state
        self._slots = slots
        self._cache = cache
        self._keys = keys
        self._settings = settings
        self._clock = clock
        self._policy = staleness_policy(settings.cache)

    async def run(self, job_id: UUID) -> JobStatus | None:
        item = await self._repo.start_job(
            job_id,
            self._clock.now(),
            context_messages=self._settings.agent.agent_context_messages,
        )
        if item is None:
            log.info("job_skipped", job_id=str(job_id))
            return None
        log.info("job_started", job_id=str(job_id), attempt=item.attempt)
        try:
            return await self._process(item)
        except Exception as exc:
            log.exception("job_crashed", job_id=str(job_id), error_type=type(exc).__name__)
            await self._fail(item, ErrorCode.INTERNAL_ERROR, None)
            return JobStatus.FAILED
        finally:
            await self._release_slot(item)

    # ------------------------------------------------------------------ steps

    async def _process(self, item: WorkItem) -> JobStatus:
        progress = _Progress(self, item)
        await progress.stage(JobStage.FETCHING_DATA, status=JobStatus.RUNNING)
        run_id = new_id()
        started = self._clock.now()
        deadline = started + timedelta(seconds=self._settings.agent.job_agent_timeout_seconds)
        call_task = asyncio.create_task(
            self._agent.run(
                self._agent_request(item, run_id, deadline),
                deadline=deadline,
                on_progress=progress.from_agent,
            )
        )
        watch_task = asyncio.create_task(self._watch_cancel(item.job_id))
        try:
            await asyncio.wait({call_task, watch_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watch_task.cancel()
            if not call_task.done():
                # Cancelled by the user (or the worker is stopping): the client tells the
                # Agent to stop the run before the task ends.
                call_task.cancel()
            await asyncio.gather(call_task, watch_task, return_exceptions=True)
        if call_task.cancelled():
            return await self._cancelled(item, run_id, started)
        try:
            call = call_task.result()
        except AgentCallError as exc:
            record = _run_record(run_id, item.attempt, exc.attempts)
            return await self._fail(item, exc.to_app_error().code, record)

        response = call.response
        await self._record_services(response)
        try:
            assessment = assess(
                response,
                now=self._clock.now(),
                language=item.request.language,
                policy=self._policy,
                emergency_fallback=await self._fallback(item, response),
                low_confidence_below=self._settings.safety.low_confidence_threshold,
                api_version=self._settings.app.api_version,
            )
        except SafetyGateRejection as rejection:
            SAFETY_REJECTIONS.labels(rule=rejection.rule).inc()
            if rejection.needs_safety_review:
                log.warning(
                    "safety_review_required",
                    rule=rejection.rule,
                    job_id=str(item.job_id),
                    run_id=str(run_id),
                )
            code = (
                ErrorCode.DEPENDENCY_UNAVAILABLE
                if rejection.agent_failed
                else ErrorCode.AGENT_BAD_RESPONSE
            )
            record = _run_record(
                run_id,
                item.attempt,
                call.attempts,
                response,
                rejected_by=None if rejection.agent_failed else rejection.rule,
            )
            return await self._fail(item, code, record)

        result = StoredResult.from_assessment(
            assessment, versions=response.versions, api_version=self._settings.app.api_version
        )
        now = self._clock.now()
        stored = await self._repo.finish_job(
            item.job_id,
            JobOutcome(
                status=JobStatus.SUCCEEDED,
                finished_at=now,
                result=result,
                error_code=None,
                agent_run=_run_record(run_id, item.attempt, call.attempts, response),
                conversation_days=self._settings.retention.retention_conversation_days,
                prediction=await self._prediction(item, result, now),
                prediction_days=self._settings.retention.retention_prediction_days,
            ),
        )
        if not stored:
            # Cancelled or reaped while the Agent was working: nothing to announce (D-73).
            return JobStatus.CANCELLED
        JOBS.labels(status=JobStatus.SUCCEEDED.value).inc()
        count_recommendation(
            assessment.status, assessment.risk_level, assessment.recommendation_type
        )
        for rule in assessment.applied_rules:
            SAFETY_OVERRIDES.labels(rule=rule).inc()
        if item.cache_key is not None and result_is_cacheable(
            status=assessment.status,
            risk_level=assessment.risk_level,
            overall_is_stale=assessment.overall_is_stale,
        ):
            ttl = cache_ttl_seconds(
                now=now,
                valid_until=assessment.valid_until,
                max_seconds=self._settings.cache.recommendation_cache_seconds,
            )
            await self._cache.put(item.cache_key, assessment.payload, ttl_seconds=ttl)
        await self._finish_state(
            item,
            JobStatus.SUCCEEDED,
            JobStage.COMPLETED,
            "completed",
            {
                "job_id": str(item.job_id),
                "status": assessment.status.value,
                "result_url": result_url(item.recommendation_id),
            },
        )
        log.info(
            "job_succeeded",
            job_id=str(item.job_id),
            status=assessment.status.value,
            rules=list(assessment.applied_rules),
        )
        return JobStatus.SUCCEEDED

    async def _watch_cancel(self, job_id: UUID) -> None:
        while True:
            await asyncio.sleep(CANCEL_POLL_SECONDS)
            try:
                if await self._repo.job_cancelled(job_id):
                    return
            except Exception as exc:  # the next poll tries again
                log.warning("job_cancel_check_failed", error_type=type(exc).__name__)

    async def _cancelled(self, item: WorkItem, run_id: UUID, started: datetime) -> JobStatus:
        now = self._clock.now()
        stored = await self._repo.finish_job(
            item.job_id,
            JobOutcome(
                status=JobStatus.CANCELLED,
                finished_at=now,
                result=None,
                error_code=None,
                agent_run=AgentRunRecord(
                    run_id=run_id,
                    attempt=item.attempt,
                    status=AgentRunStatus.CANCELLED,
                    http_status=None,
                    error_code=None,
                    started_at=started,
                    finished_at=now,
                    tool_calls=None,
                    agent_version=None,
                    trace_id=None,
                ),
                conversation_days=self._settings.retention.retention_conversation_days,
            ),
        )
        if stored:
            # Usually the API already counted it: E-05 cancels in the database first.
            JOBS.labels(status=JobStatus.CANCELLED.value).inc()
        log.info("job_stopped_after_cancel", job_id=str(item.job_id))
        return JobStatus.CANCELLED

    async def _record_services(self, response: AgentRunResponse) -> None:
        """Note what the Agent said about its data services, for E-23 (best effort)."""
        if self._reports is None or not response.service_status:
            return
        window = self._settings.observability.service_status_window_minutes
        try:
            await self._reports.record(
                response.service_status, at=self._clock.now(), ttl_seconds=window * 60
            )
        except _REDIS_ERRORS as exc:
            log.warning("service_status_unavailable", error_type=type(exc).__name__)

    async def _prediction(
        self, item: WorkItem, result: StoredResult, now: datetime
    ) -> PredictionData | None:
        if not item.analytics:
            return None
        origin = item.request.origin
        return build_prediction(
            item.request,
            result,
            now=now,
            region_code=await self._repo.region_for(origin.lat, origin.lon),
            precision=self._settings.privacy.prediction_geohash_precision,
        )

    def _agent_request(self, item: WorkItem, run_id: UUID, deadline: datetime) -> AgentRunRequest:
        request = item.request
        prefs = request.preferences
        return AgentRunRequest(
            run_id=run_id,
            intent_hint=IntentHint.FOLLOW_UP if item.context else IntentHint.CHECK_SAFETY,
            request=AgentTravelRequest(
                origin=_location(request.origin),
                destination=_location(request.destination),
                waypoints=[_location(p) for p in request.waypoints],
                departure_time=request.departure_time,
                timezone=request.timezone,
                language=request.language,
                preferences={
                    "travel_modes": list(prefs.travel_modes),
                    "avoid": list(prefs.avoid),
                    "max_travel_hours": prefs.max_travel_hours,
                    "mobility_needs": list(prefs.mobility_needs),
                    "traveler_count": prefs.traveler_count,
                },
                question=request.question,
            ),
            context=AgentContext(
                conversation_id=item.conversation_id,
                messages=[
                    AgentMessage(role=role, content=content) for role, content in item.context
                ],
                previous_recommendation_id=item.previous_recommendation_id,
            ),
            user_profile=AgentUserProfile(
                pseudonymous_id=item.user.pseudonymous_id,
                language=request.language,
                home_region=item.user.home_region,
            ),
            limits=AgentLimits(
                deadline_at=deadline, max_tool_calls=self._settings.agent.agent_max_tool_calls
            ),
        )

    async def _fallback(self, item: WorkItem, response: AgentRunResponse) -> dict[str, Any] | None:
        # Only needed for R-01: high risk without the Agent's own instructions.
        risk = response.risk
        if risk is None or risk.level is not RiskLevel.HIGH or response.emergency_instructions:
            return None
        request = item.request
        region = await self._repo.region_for(
            request.destination.lat, request.destination.lon
        ) or await self._repo.region_for(request.origin.lat, request.origin.lon)
        if region is None:
            return None
        return await self._repo.emergency_default(
            region, request.language
        ) or await self._repo.emergency_default(region, "en")

    async def _fail(
        self, item: WorkItem, code: ErrorCode, record: AgentRunRecord | None
    ) -> JobStatus:
        stored = await self._repo.finish_job(
            item.job_id,
            JobOutcome(
                status=JobStatus.FAILED,
                finished_at=self._clock.now(),
                result=None,
                error_code=code.value,
                agent_run=record,
                conversation_days=self._settings.retention.retention_conversation_days,
            ),
        )
        if not stored:
            return JobStatus.CANCELLED
        JOBS.labels(status=JobStatus.FAILED.value).inc()
        await self._finish_state(
            item,
            JobStatus.FAILED,
            JobStage.FAILED,
            "failed",
            {
                "job_id": str(item.job_id),
                "error": {"code": code.value, "message": ERROR_SPECS[code].detail},
            },
            error_code=code.value,
        )
        log.warning("job_failed", job_id=str(item.job_id), code=code.value)
        return JobStatus.FAILED

    # ------------------------------------------------------------------ redis

    async def _set_stage(
        self, item: WorkItem, stage: JobStage, *, status: JobStatus | None = None
    ) -> None:
        now = self._clock.now()
        progress = STAGE_PROGRESS[stage]
        try:
            await self._jobs.update(
                item.job_id, updated_at=now, status=status, stage=stage, progress=progress
            )
            await self._jobs.publish(
                item.job_id,
                "progress",
                {
                    "job_id": str(item.job_id),
                    "stage": stage.value,
                    "progress": progress,
                    "message": stage_message(stage, item.request.language),
                    "at": iso(now),
                },
            )
        except _REDIS_ERRORS as exc:
            # Progress is best effort; the final state is what matters.
            log.warning("job_progress_unavailable", error_type=type(exc).__name__)

    async def _finish_state(
        self,
        item: WorkItem,
        status: JobStatus,
        stage: JobStage,
        event: str,
        data: dict[str, Any],
        *,
        error_code: str | None = None,
    ) -> None:
        try:
            await self._jobs.update(
                item.job_id,
                updated_at=self._clock.now(),
                status=status,
                stage=stage,
                progress=STAGE_PROGRESS[stage] if status is JobStatus.SUCCEEDED else None,
                error_code=error_code,
            )
            await self._jobs.publish(item.job_id, event, data)
        except _REDIS_ERRORS as exc:
            # The database has the result; clients fall back to it.
            log.error(
                "job_state_unavailable", job_id=str(item.job_id), error_type=type(exc).__name__
            )

    async def _release_slot(self, item: WorkItem) -> None:
        try:
            await self._slots.release(self._keys.active_jobs(item.user.id), str(item.job_id))
        except _REDIS_ERRORS as exc:
            log.warning("active_job_release_failed", error_type=type(exc).__name__)
