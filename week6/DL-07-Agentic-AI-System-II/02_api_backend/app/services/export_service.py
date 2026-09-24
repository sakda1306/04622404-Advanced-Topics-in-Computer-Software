"""Data export of everything stored about the user (E-21/E-22, PDPA; D-82..D-84).

The API claims the once-per-P-63 slot, stores the request and queues a `maintenance`
task; the task writes a zip of JSON to object storage. The download link is signed and
short-lived (P-62); the file itself is deleted after P-49.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.domain.enums import ExportStatus
from app.services.ports import (
    CooldownPort,
    ExportRecord,
    ExportRepository,
    JobQueue,
    ObjectStorePort,
    UserRef,
)

log = get_logger(__name__)

EXPORT_FILE = "travel-safety-data.json"


@dataclass(frozen=True, slots=True)
class ExportView:
    record: ExportRecord
    download_url: str | None


def export_key(export_id: UUID) -> str:
    # Only the export id: the object name says nothing about the user.
    return f"exports/{export_id}.zip"


def _zip(data: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(EXPORT_FILE, json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return buffer.getvalue()


class ExportService:
    def __init__(
        self,
        *,
        exports: ExportRepository,
        store: ObjectStorePort,
        cooldown: CooldownPort,
        queue: JobQueue,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = exports
        self._store = store
        self._cooldown = cooldown
        self._queue = queue
        self._settings = settings
        self._clock = clock

    def _cooldown_key(self, user_id: UUID) -> str:
        return f"export:{user_id}"

    async def request(self, user: UserRef, *, correlation_id: str) -> ExportRecord:
        hours = self._settings.retention.data_export_cooldown_hours
        remaining = await self._cooldown.claim(self._cooldown_key(user.id), seconds=hours * 3600)
        if remaining is not None:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                detail="A data export can be requested once a day.",
                retry_after=remaining,
            )
        record = await self._repo.create(user.id, now=self._clock.now())
        try:
            await self._queue.enqueue_data_export(record.id, correlation_id=correlation_id)
        except Exception as exc:
            log.error("export_enqueue_failed", error_type=type(exc).__name__)
            await self._repo.fail(record.id, now=self._clock.now())
            await self._cooldown.release(self._cooldown_key(user.id))
            raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=30) from exc
        log.info("export_requested", export_id=str(record.id))
        return record

    async def get(self, user: UserRef, export_id: UUID) -> ExportView:
        record = await self._repo.get(user.id, export_id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        url = None
        ready = record.status is ExportStatus.READY and record.object_key is not None
        if ready and (record.expires_at is None or record.expires_at > self._clock.now()):
            assert record.object_key is not None
            url = await self._store.download_url(
                record.object_key, expires_seconds=self._settings.retention.data_export_url_seconds
            )
        return ExportView(record, url)

    async def build(self, export_id: UUID) -> bool:
        """Worker side; False when the export was not waiting (already built or failed)."""
        user_id = await self._repo.start(export_id)
        if user_id is None:
            log.info("export_skipped", export_id=str(export_id))
            return False
        try:
            data = await self._repo.collect(user_id)
            now = self._clock.now()
            data = {"exported_at": now.isoformat(), **data}
            key = export_key(export_id)
            await self._store.put(key, _zip(data), content_type="application/zip")
        except Exception as exc:
            log.exception("export_failed", export_id=str(export_id), error_type=type(exc).__name__)
            await self._repo.fail(export_id, now=self._clock.now())
            return False
        await self._repo.finish(
            export_id,
            object_key=key,
            now=now,
            expires_at=now + timedelta(days=self._settings.retention.data_export_ttl_days),
        )
        log.info("export_ready", export_id=str(export_id))
        return True
