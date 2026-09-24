"""Queue `maintenance`: reaper (D-74), account deletion (D-79), exports (D-82, D-92),
purge (D-85)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import structlog
from celery import shared_task

from app.core.ids import accept_client_id, correlation_id_var, new_id
from app.core.logging import get_logger
from app.core.telemetry import tag_correlation
from app.workers.celery_app import (
    BUILD_DATA_EXPORT,
    BUILD_TRAINING_EXPORT,
    DELETE_ACCOUNT,
    PURGE_EXPIRED,
    REAP_STUCK_JOBS,
)
from app.workers.runtime import runtime

log = get_logger(__name__)


@contextmanager
def _correlation(value: str) -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=value)
    token = correlation_id_var.set(value)
    tag_correlation(value)
    try:
        yield
    finally:
        correlation_id_var.reset(token)
        structlog.contextvars.clear_contextvars()


@shared_task(name=REAP_STUCK_JOBS, ignore_result=True)
def reap_stuck_jobs() -> dict[str, int]:
    with _correlation(str(new_id())):
        return runtime.reap_stuck_jobs()


@shared_task(name=DELETE_ACCOUNT, ignore_result=True)
def delete_account(user_id: str, correlation_id: str | None = None) -> bool:
    with _correlation(accept_client_id(correlation_id) or str(new_id())):
        try:
            parsed = UUID(user_id)
        except ValueError:
            log.warning("invalid_user_id")
            return False
        return runtime.delete_account(parsed)


@shared_task(name=BUILD_DATA_EXPORT, ignore_result=True)
def build_data_export(export_id: str, correlation_id: str | None = None) -> bool:
    with _correlation(accept_client_id(correlation_id) or str(new_id())):
        try:
            parsed = UUID(export_id)
        except ValueError:
            log.warning("invalid_export_id")
            return False
        return runtime.build_data_export(parsed)


@shared_task(name=PURGE_EXPIRED, ignore_result=True)
def purge_expired() -> dict[str, int]:
    with _correlation(str(new_id())):
        return runtime.purge_expired()


@shared_task(name=BUILD_TRAINING_EXPORT, ignore_result=True)
def build_training_export(export_id: str, correlation_id: str | None = None) -> bool:
    with _correlation(accept_client_id(correlation_id) or str(new_id())):
        try:
            parsed = UUID(export_id)
        except ValueError:
            log.warning("invalid_export_id")
            return False
        return runtime.build_training_export(parsed)
