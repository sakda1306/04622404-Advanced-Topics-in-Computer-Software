"""run_recommendation(job_id): the worker side of POST /v1/travel/recommendations."""

from __future__ import annotations

from uuid import UUID

import structlog
from celery import shared_task

from app.core.ids import accept_client_id, correlation_id_var
from app.core.logging import get_logger
from app.core.telemetry import tag_correlation
from app.workers.celery_app import RUN_RECOMMENDATION
from app.workers.runtime import runtime

log = get_logger(__name__)


@shared_task(name=RUN_RECOMMENDATION, ignore_result=True)
def run_recommendation(job_id: str, correlation_id: str | None = None) -> str | None:
    correlation = accept_client_id(correlation_id) or job_id[:64]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation, job_id=job_id[:64])
    token = correlation_id_var.set(correlation)
    tag_correlation(correlation)
    try:
        try:
            parsed = UUID(job_id)
        except ValueError:
            log.warning("invalid_job_id")
            return None
        return runtime.run_recommendation(parsed)
    finally:
        correlation_id_var.reset(token)
        structlog.contextvars.clear_contextvars()
