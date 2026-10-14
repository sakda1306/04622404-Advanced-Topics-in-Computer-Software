"""Celery app for the `worker` and `beat` containers.

celery -A app.workers.celery_app worker --loglevel=INFO
celery -A app.workers.celery_app beat --loglevel=INFO
"""

from __future__ import annotations

from typing import Any

from celery import Celery, signals

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.schedule import beat_schedule

settings = get_settings()

celery_app = Celery("api", broker=settings.broker_url, include=["app.workers.tasks"])
celery_app.conf.update(
    timezone=settings.timezone,
    enable_utc=False,
    beat_schedule=beat_schedule(),
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # A trigger older than its next run is useless: drop it instead of piling up.
    task_default_expires=25 * 60,
)


@signals.setup_logging.connect
def _setup_logging(**_kwargs: Any) -> None:
    # Replaces Celery's own logging setup with the JSON logs used by the api.
    configure_logging(settings.log_level, settings.log_json, "worker")
