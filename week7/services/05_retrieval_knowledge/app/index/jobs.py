"""Rebuild jobs (CONTRACT §6): one at a time, run in the background, kept in memory.

Only the latest jobs are kept and a restart forgets them all; the admin page only needs
to follow the job it just started.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.core.clock import bangkok_now, version_stamp
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.index.service import IndexService

log = get_logger(__name__)

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass(slots=True)
class Job:
    job_id: str
    category: str | None
    status: JobStatus = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    detail: str | None = None


class RebuildJobs:
    def __init__(
        self,
        index: IndexService,
        *,
        keep: int = 50,
        clock: Callable[[], datetime] = bangkok_now,
    ) -> None:
        self._index = index
        self._keep = keep
        self._clock = clock
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._task: asyncio.Task[None] | None = None

    def start(self, category: str | None) -> Job:
        if self._task is not None and not self._task.done():
            raise AppError(ErrorCode.JOB_ALREADY_RUNNING)
        job = Job(job_id=str(uuid.uuid4()), category=category)
        self._jobs[job.job_id] = job
        while len(self._jobs) > self._keep:
            self._jobs.popitem(last=False)
        self._task = asyncio.create_task(self._run(job))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def wait(self) -> None:
        """Wait for the current job, if any (tests and shutdown)."""
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        await self.wait()

    async def _run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = version_stamp(self._clock())
        log.info("rebuild_started", job_id=job.job_id, category=job.category)
        try:
            result = await self._index.rebuild(job.category)
        except asyncio.CancelledError:
            job.status = "failed"
            job.detail = "cancelled"
            raise
        except Exception as exc:
            job.status = "failed"
            # The type only: messages can carry paths or SQL (CONTRACT §0).
            job.detail = type(exc).__name__
            log.exception("rebuild_failed", job_id=job.job_id)
        else:
            job.status = "done"
            job.detail = f"{result.documents} documents, {result.chunks} chunks"
            log.info("rebuild_done", job_id=job.job_id, index_version=result.index_version)
        finally:
            job.finished_at = version_stamp(self._clock())
