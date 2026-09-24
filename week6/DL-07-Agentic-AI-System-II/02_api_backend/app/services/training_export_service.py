"""Anonymized training data for the MLOps pipeline (FR-19, D-92).

An admin asks for a time range; a `maintenance` task writes gzip JSON Lines to a temp
file, uploads it and keeps it for P-68. The download link is signed and short-lived
(P-62). Rows are prediction records plus reviewer-approved feedback only: feedback is
used for retraining only after review (docs/02_api_spec.md section 7.3).
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.domain.admin import resolve_range
from app.domain.enums import AuditResult, ExportStatus
from app.services.admin_service import Actor, iso_range, write_admin_audit
from app.services.ports import (
    AuditPort,
    FileStorePort,
    TrainingExportQueue,
    TrainingExportRecord,
    TrainingExportRepository,
)

log = get_logger(__name__)

DEFAULT_WINDOW = timedelta(days=30)
BATCH_SIZE = 1000
CONTENT_TYPE = "application/gzip"
_TARGET = "training_export"


@dataclass(frozen=True, slots=True)
class TrainingExportView:
    record: TrainingExportRecord
    download_url: str | None


def training_key(export_id: UUID) -> str:
    return f"training/{export_id}.jsonl.gz"


class TrainingExportService:
    def __init__(
        self,
        *,
        exports: TrainingExportRepository,
        store: FileStorePort,
        queue: TrainingExportQueue,
        audit: AuditPort,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = exports
        self._store = store
        self._queue = queue
        self._audit = audit
        self._settings = settings
        self._clock = clock

    async def request(
        self, actor: Actor, *, start: datetime | None, end: datetime | None
    ) -> TrainingExportRecord:
        now = self._clock.now()
        period = resolve_range(
            start,
            end,
            now=now,
            default=DEFAULT_WINDOW,
            max_days=self._settings.admin.training_export_max_range_days,
        )
        record = await self._repo.create(actor.subject, period=period, now=now)
        try:
            await self._queue.enqueue_training_export(
                record.id, correlation_id=actor.correlation_id
            )
        except Exception as exc:
            log.error("training_export_enqueue_failed", error_type=type(exc).__name__)
            await self._repo.fail(record.id, now=self._clock.now())
            await write_admin_audit(
                self._audit,
                actor,
                "export.training_data",
                AuditResult.ERROR,
                target=(_TARGET, str(record.id)),
                metadata=iso_range(period),
            )
            raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=30) from exc
        await write_admin_audit(
            self._audit,
            actor,
            "export.training_data",
            AuditResult.SUCCESS,
            target=(_TARGET, str(record.id)),
            metadata=iso_range(period),
        )
        log.info("training_export_requested", export_id=str(record.id))
        return record

    async def get(self, actor: Actor, export_id: UUID) -> TrainingExportView:
        record = await self._repo.get(export_id)
        await write_admin_audit(
            self._audit,
            actor,
            "export.training_data_read",
            AuditResult.SUCCESS if record is not None else AuditResult.ERROR,
            target=(_TARGET, str(export_id)),
        )
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        url = None
        live = record.expires_at is None or record.expires_at > self._clock.now()
        if record.status is ExportStatus.READY and record.object_key is not None and live:
            url = await self._store.download_url(
                record.object_key,
                expires_seconds=self._settings.retention.data_export_url_seconds,
            )
        return TrainingExportView(record, url)

    async def build(self, export_id: UUID) -> bool:
        """Worker side; False when the export was not waiting or could not be written."""
        period = await self._repo.start(export_id)
        if period is None:
            log.info("training_export_skipped", export_id=str(export_id))
            return False
        handle, path = tempfile.mkstemp(suffix=".jsonl.gz")
        os.close(handle)
        try:
            count = 0
            with gzip.open(path, "wt", encoding="utf-8") as out:
                async for line in self._repo.rows(period, batch=BATCH_SIZE):
                    out.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")))
                    out.write("\n")
                    count += 1
            key = training_key(export_id)
            await self._store.put_file(key, path, content_type=CONTENT_TYPE)
        except Exception as exc:
            log.exception(
                "training_export_failed", export_id=str(export_id), error_type=type(exc).__name__
            )
            await self._repo.fail(export_id, now=self._clock.now())
            return False
        finally:
            os.unlink(path)
        now = self._clock.now()
        await self._repo.finish(
            export_id,
            object_key=key,
            row_count=count,
            now=now,
            expires_at=now + timedelta(days=self._settings.admin.training_export_ttl_days),
        )
        log.info("training_export_ready", export_id=str(export_id), rows=count)
        return True
