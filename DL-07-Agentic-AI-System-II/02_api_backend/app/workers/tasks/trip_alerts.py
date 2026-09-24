"""scan_trip_alerts(): queue re-assessments of trips with live alerts on (D-65)."""

from __future__ import annotations

import structlog
from celery import shared_task

from app.core.ids import correlation_id_var, new_id
from app.core.telemetry import tag_correlation
from app.workers.celery_app import SCAN_TRIP_ALERTS
from app.workers.runtime import runtime


@shared_task(name=SCAN_TRIP_ALERTS, ignore_result=True)
def scan_trip_alerts() -> dict[str, int]:
    correlation = str(new_id())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation)
    token = correlation_id_var.set(correlation)
    tag_correlation(correlation)
    try:
        return runtime.scan_trip_alerts()
    finally:
        correlation_id_var.reset(token)
        structlog.contextvars.clear_contextvars()
