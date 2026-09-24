"""Scheduled clean-up of stuck jobs and unfinished account deletions (D-74, D-78).

Workers normally end every job. A job whose message was lost, or whose worker died,
stays queued/running; the reaper fails it after P-04 x 2 so the user gets an answer and
the active-job slot is freed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from redis.exceptions import RedisError

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import ERROR_SPECS, ErrorCode
from app.core.ids import current_correlation_id, new_id
from app.core.logging import get_logger
from app.core.metrics import JOBS
from app.domain.enums import JobStage, JobStatus
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import SlotLimiter
from app.services.ports import (
    ExportRepository,
    JobQueue,
    JobRecord,
    JobStatePort,
    RecommendationRepository,
    UserRepository,
)

log = get_logger(__name__)

BATCH_SIZE = 100
# Building an export takes seconds; one still waiting after this is lost.
EXPORT_STUCK_AFTER = timedelta(minutes=30)


class StuckExports(Protocol):
    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int: ...


_REDIS_ERRORS = (RedisError, OSError)
_CODE = ErrorCode.AGENT_TIMEOUT


@dataclass(frozen=True, slots=True)
class ReapResult:
    reaped: int
    deletions_requeued: int
    exports_failed: int = 0


class ReaperService:
    def __init__(
        self,
        *,
        recommendations: RecommendationRepository,
        users: UserRepository,
        job_state: JobStatePort,
        slots: SlotLimiter,
        queue: JobQueue,
        keys: RedisKeys,
        settings: Settings,
        clock: Clock,
        exports: ExportRepository | None = None,
        training_exports: StuckExports | None = None,
    ) -> None:
        self._exports = exports
        self._training_exports = training_exports
        self._repo = recommendations
        self._users = users
        self._jobs = job_state
        self._slots = slots
        self._queue = queue
        self._keys = keys
        self._settings = settings
        self._clock = clock

    async def run(self) -> ReapResult:
        now = self._clock.now()
        stuck_after = timedelta(seconds=self._settings.agent.job_agent_timeout_seconds * 2)
        reaped = await self._repo.reap_stuck_jobs(
            older_than=now - stuck_after, now=now, limit=BATCH_SIZE
        )
        for job in reaped:
            await self._announce(job)
        if reaped:
            JOBS.labels(status=JobStatus.FAILED.value).inc(len(reaped))

        retry_after = timedelta(minutes=self._settings.maintenance.account_deletion_retry_minutes)
        pending = await self._users.pending_deletions(
            older_than=now - retry_after, limit=BATCH_SIZE
        )
        for user_id in pending:
            await self._queue.enqueue_account_deletion(
                user_id, correlation_id=current_correlation_id() or str(new_id())
            )
        exports_failed = 0
        for exports in (self._exports, self._training_exports):
            if exports is not None:
                exports_failed += await exports.fail_stuck(
                    older_than=now - EXPORT_STUCK_AFTER, now=now
                )
        log.info(
            "reaper_run",
            reaped=len(reaped),
            deletions_requeued=len(pending),
            exports_failed=exports_failed,
        )
        return ReapResult(
            reaped=len(reaped), deletions_requeued=len(pending), exports_failed=exports_failed
        )

    async def _announce(self, job: JobRecord) -> None:
        log.warning("job_reaped", job_id=str(job.id))
        try:
            await self._jobs.update(
                job.id,
                updated_at=self._clock.now(),
                status=JobStatus.FAILED,
                stage=JobStage.FAILED,
                error_code=_CODE.value,
            )
            await self._jobs.publish(
                job.id,
                "failed",
                {
                    "job_id": str(job.id),
                    "error": {"code": _CODE.value, "message": ERROR_SPECS[_CODE].detail},
                },
            )
            await self._slots.release(self._keys.active_jobs(job.user_id), str(job.id))
        except _REDIS_ERRORS as exc:
            # The database has the outcome; clients fall back to it.
            log.warning("job_reap_state_unavailable", error_type=type(exc).__name__)
