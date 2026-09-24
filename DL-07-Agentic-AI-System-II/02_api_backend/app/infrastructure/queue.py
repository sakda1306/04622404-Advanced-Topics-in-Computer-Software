"""Enqueue jobs on Celery from async code."""

from __future__ import annotations

import asyncio
from uuid import UUID

from celery import Celery

from app.workers.celery_app import (
    BUILD_DATA_EXPORT,
    BUILD_TRAINING_EXPORT,
    DELETE_ACCOUNT,
    MAINTENANCE_QUEUE,
    RECOMMENDATION_QUEUE,
    RUN_RECOMMENDATION,
)

# Publishing blocks while the broker is unreachable; keep that short.
_RETRY_POLICY = {"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1}


class CeleryJobQueue:
    def __init__(self, celery: Celery) -> None:
        self._celery = celery

    async def enqueue_recommendation(self, job_id: UUID, *, correlation_id: str) -> str:
        # Only ids go through the broker (docs/04_project_structure.md section 6).
        result = await asyncio.to_thread(
            self._celery.send_task,
            RUN_RECOMMENDATION,
            kwargs={"job_id": str(job_id), "correlation_id": correlation_id},
            queue=RECOMMENDATION_QUEUE,
            retry=True,
            retry_policy=_RETRY_POLICY,
        )
        return str(result.id)

    async def enqueue_account_deletion(self, user_id: UUID, *, correlation_id: str) -> str:
        result = await asyncio.to_thread(
            self._celery.send_task,
            DELETE_ACCOUNT,
            kwargs={"user_id": str(user_id), "correlation_id": correlation_id},
            queue=MAINTENANCE_QUEUE,
            retry=True,
            retry_policy=_RETRY_POLICY,
        )
        return str(result.id)

    async def enqueue_data_export(self, export_id: UUID, *, correlation_id: str) -> str:
        result = await asyncio.to_thread(
            self._celery.send_task,
            BUILD_DATA_EXPORT,
            kwargs={"export_id": str(export_id), "correlation_id": correlation_id},
            queue=MAINTENANCE_QUEUE,
            retry=True,
            retry_policy=_RETRY_POLICY,
        )
        return str(result.id)

    async def enqueue_training_export(self, export_id: UUID, *, correlation_id: str) -> str:
        result = await asyncio.to_thread(
            self._celery.send_task,
            BUILD_TRAINING_EXPORT,
            kwargs={"export_id": str(export_id), "correlation_id": correlation_id},
            queue=MAINTENANCE_QUEUE,
            retry=True,
            retry_policy=_RETRY_POLICY,
        )
        return str(result.id)
