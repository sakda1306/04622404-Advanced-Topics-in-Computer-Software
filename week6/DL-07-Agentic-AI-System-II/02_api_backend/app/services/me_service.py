"""The caller's own profile, consents and account deletion (docs/02_api_spec.md 7.4).

Deleting an account is two-phase (D-78): this request marks the user, stops their jobs
and removes live data from Redis; a `maintenance` task deletes the rows (D-79).
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from redis.exceptions import RedisError

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.domain.enums import ActorType, AuditResult
from app.domain.profile import (
    ProfileChanges,
    apply_profile_changes,
    consent_changes,
    mask_email,
)
from app.services.job_service import JobService
from app.services.ports import (
    AuditEntry,
    AuditPort,
    JobQueue,
    ProfileRecord,
    UserDataPort,
    UserRef,
    UserRepository,
)

log = get_logger(__name__)

_REDIS_ERRORS = (RedisError, OSError)


class MeService:
    def __init__(
        self,
        *,
        users: UserRepository,
        jobs: JobService,
        user_data: UserDataPort,
        audit: AuditPort,
        queue: JobQueue,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._users = users
        self._jobs = jobs
        self._user_data = user_data
        self._audit = audit
        self._queue = queue
        self._settings = settings
        self._clock = clock

    async def get(self, user: UserRef, *, email: str | None) -> tuple[ProfileRecord, str | None]:
        record = await self._users.profile(user.id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return record, mask_email(email)

    async def update(
        self,
        user: UserRef,
        changes: ProfileChanges,
        *,
        correlation_id: str,
        ip_hash: str | None,
    ) -> ProfileRecord:
        current, _ = await self.get(user, email=None)
        now = self._clock.now()
        profile = apply_profile_changes(current.profile, changes, now=now)
        saved = await self._users.update_profile(user.id, profile, now=now)
        if saved is None:
            raise AppError(ErrorCode.NOT_FOUND)
        changed = consent_changes(current.profile.consents, profile.consents)
        if changed:
            # Evidence of when consent was given or withdrawn (PDPA).
            await self._write_audit(user, "user.consent", correlation_id, ip_hash, changed)
        return saved

    async def delete(
        self,
        user: UserRef,
        *,
        principal_hash: str,
        correlation_id: str,
        ip_hash: str | None,
    ) -> None:
        now = self._clock.now()
        first = await self._users.request_deletion(user.id, now=now)
        since = now - timedelta(seconds=self._settings.jobs.job_result_ttl_seconds)
        job_ids = await self._users.recent_job_ids(user.id, since=since)
        for job_id in job_ids:
            with contextlib.suppress(AppError):  # already finished
                await self._jobs.cancel(user.id, job_id)
        try:
            removed = await self._user_data.forget(
                user.id, principal_hash=principal_hash, job_ids=job_ids
            )
            log.info("user_live_data_removed", keys=removed)
        except _REDIS_ERRORS as exc:
            # Everything left in Redis expires on its own (P-05, P-25).
            log.warning("user_live_data_unavailable", error_type=type(exc).__name__)
        if not first:
            return
        await self._write_audit(user, "user.delete_requested", correlation_id, ip_hash, {})
        await self._queue.enqueue_account_deletion(user.id, correlation_id=correlation_id)
        log.info("account_deletion_requested")

    async def _write_audit(
        self,
        user: UserRef,
        action: str,
        correlation_id: str,
        ip_hash: str | None,
        metadata: dict[str, Any],
    ) -> None:
        await self._audit.write(
            AuditEntry(
                actor_type=ActorType.USER,
                actor_ref=user.pseudonymous_id,
                action=action,
                target_type=None,
                target_id=None,
                result=AuditResult.SUCCESS,
                correlation_id=correlation_id,
                ip_hash=ip_hash,
                metadata=metadata,
            )
        )
