"""Job status, progress stream and stream tickets (docs/02_api_spec.md 6.1 and 6.3)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from redis.exceptions import RedisError

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import ERROR_SPECS, AppError, ErrorCode
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.metrics import JOBS
from app.domain.enums import JobStage, JobStatus
from app.infrastructure.redis.job_state import JobEvent
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import SlotLimiter
from app.services.agent_run_service import result_url
from app.services.ports import JobRecord, JobStatePort, RecommendationRepository, TicketPort

log = get_logger(__name__)

_REDIS_ERRORS = (RedisError, OSError)
_STREAM_ID = re.compile(r"^\d{1,20}-\d{1,20}$")
_START = "0-0"
_MAX_BLOCK_SECONDS = 1.0


class JobService:
    def __init__(
        self,
        *,
        repository: RecommendationRepository,
        job_state: JobStatePort,
        slots: SlotLimiter,
        tickets: TicketPort,
        keys: RedisKeys,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._jobs = job_state
        self._slots = slots
        self._tickets = tickets
        self._keys = keys
        self._settings = settings
        self._clock = clock

    # ------------------------------------------------------------------ status

    async def get(self, user_id: UUID, job_id: UUID) -> JobRecord:
        try:
            snapshot = await self._jobs.get(job_id)
        except _REDIS_ERRORS as exc:
            log.warning("job_state_unavailable", error_type=type(exc).__name__)
            snapshot = None
        if snapshot is not None:
            if snapshot.user_id != user_id:
                raise AppError(ErrorCode.NOT_FOUND)
            return JobRecord.from_snapshot(snapshot)
        record = await self._repo.get_job(user_id, job_id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return record

    # ------------------------------------------------------------------ cancel

    async def cancel(self, user_id: UUID, job_id: UUID) -> JobRecord:
        """E-05: the database decides; the worker notices and stops the Agent run (D-72)."""
        now = self._clock.now()
        outcome, record = await self._repo.cancel_job(user_id, job_id, now=now)
        if outcome is None or record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if outcome == "not_cancellable":
            raise AppError(ErrorCode.JOB_NOT_CANCELLABLE)
        JOBS.labels(status=JobStatus.CANCELLED.value).inc()
        try:
            await self._jobs.update(
                job_id, updated_at=now, status=JobStatus.CANCELLED, stage=JobStage.CANCELLED
            )
            await self._jobs.publish(job_id, "cancelled", {"job_id": str(job_id)})
            await self._slots.release(self._keys.active_jobs(user_id), str(job_id))
        except _REDIS_ERRORS as exc:
            # Clients fall back to the database, which already says cancelled.
            log.warning("job_cancel_state_unavailable", error_type=type(exc).__name__)
        log.info("job_cancelled", job_id=str(job_id))
        return record

    # ------------------------------------------------------------------ tickets

    async def issue_ticket(self, user_id: UUID, job_id: UUID) -> tuple[str, int]:
        await self.get(user_id, job_id)
        ttl = self._settings.jobs.stream_ticket_seconds
        return await self._tickets.issue(user_id, job_id, ttl_seconds=ttl), ttl

    async def redeem_ticket(self, ticket: str, job_id: UUID) -> UUID:
        redeemed = await self._tickets.redeem(ticket)
        if redeemed is None or redeemed[1] != job_id:
            raise AppError(ErrorCode.UNAUTHENTICATED, detail="The stream ticket is not valid.")
        return redeemed[0]

    # ------------------------------------------------------------------ stream

    def _stream_ttl(self) -> int:
        # A connection that stops sending heartbeats frees its slot after three beats.
        return self._settings.limits.sse_heartbeat_seconds * 3

    async def open_stream(self, user_id: UUID, job_id: UUID) -> tuple[JobRecord, str]:
        job = await self.get(user_id, job_id)
        connection_id = str(new_id())
        allowed = await self._slots.acquire(
            self._keys.streams(user_id),
            connection_id,
            limit=self._settings.limits.max_streams_per_user,
            ttl_seconds=self._stream_ttl(),
        )
        if not allowed:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                detail="Too many open event streams.",
                retry_after=self._settings.limits.sse_heartbeat_seconds,
            )
        return job, connection_id

    async def close_stream(self, user_id: UUID, connection_id: str) -> None:
        try:
            await self._slots.release(self._keys.streams(user_id), connection_id)
        except _REDIS_ERRORS as exc:
            log.warning("stream_release_failed", error_type=type(exc).__name__)

    async def stream(
        self,
        user_id: UUID,
        job: JobRecord,
        connection_id: str,
        *,
        last_event_id: str | None,
        disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[JobEvent | None]:
        """Job events in order; None means "send a heartbeat".

        `disconnected` is polled about once a second so a closed connection frees its
        stream slot quickly instead of at the next heartbeat.
        """
        heartbeat = float(self._settings.limits.sse_heartbeat_seconds)
        limit = float(self._settings.jobs.sse_max_stream_seconds)
        after = last_event_id if last_event_id and _STREAM_ID.fullmatch(last_event_id) else _START
        started = last_beat = self._clock.monotonic()
        checked_database = False
        while (elapsed := self._clock.monotonic() - started) < limit:
            if disconnected is not None and await disconnected():
                return
            since_beat = self._clock.monotonic() - last_beat
            wait = max(0.001, min(_MAX_BLOCK_SECONDS, heartbeat - since_beat, limit - elapsed))
            events = await self._jobs.read(job.id, after=after, block_ms=int(wait * 1000))
            for event in events:
                yield event
                after = event.id
                if event.terminal:
                    return
            if not events and not checked_database:
                checked_database = True
                final = await self._final_from_database(user_id, job.id)
                if final is not None:
                    yield final
                    return
            if self._clock.monotonic() - last_beat >= heartbeat:
                yield None
                last_beat = self._clock.monotonic()
                await self._slots.refresh(
                    self._keys.streams(user_id), connection_id, ttl_seconds=self._stream_ttl()
                )

    async def _final_from_database(self, user_id: UUID, job_id: UUID) -> JobEvent | None:
        """Events expire with the job state; a finished job still gets its final event."""
        if await self._jobs.get(job_id) is not None:
            return None
        record = await self._repo.get_job(user_id, job_id)
        if record is None:
            return None
        if record.status is JobStatus.SUCCEEDED and record.recommendation_id is not None:
            recommendation = await self._repo.get_recommendation(user_id, record.recommendation_id)
            status = recommendation.status.value if recommendation else "completed"
            data = {
                "job_id": str(job_id),
                "status": status,
                "result_url": result_url(record.recommendation_id),
            }
            return JobEvent(_START, "completed", data)
        if record.status is JobStatus.FAILED:
            known = {code.value for code in ErrorCode}
            code = (
                ErrorCode(record.error_code)
                if record.error_code in known
                else (ErrorCode.INTERNAL_ERROR)
            )
            error = {"code": code.value, "message": ERROR_SPECS[code].detail}
            return JobEvent(_START, "failed", {"job_id": str(job_id), "error": error})
        if record.status is JobStatus.CANCELLED:
            return JobEvent(_START, "cancelled", {"job_id": str(job_id)})
        return None
