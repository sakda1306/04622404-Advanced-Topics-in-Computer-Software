"""Celery beat schedule (docs/04_project_structure.md section 6).

Start the scheduler with:
    celery -A app.workers.celery_app:celery_app beat --schedule /tmp/celerybeat-schedule
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from celery.schedules import crontab

from app.core.config import Settings


def beat_schedule(settings: Settings) -> dict[str, dict[str, Any]]:
    from app.workers.celery_app import (
        ALERT_QUEUE,
        MAINTENANCE_QUEUE,
        PURGE_EXPIRED,
        REAP_STUCK_JOBS,
        SCAN_TRIP_ALERTS,
    )

    return {
        "scan-trip-alerts": _every(
            SCAN_TRIP_ALERTS,
            ALERT_QUEUE,
            settings.trips.trip_alert_scan_minutes,  # P-56
        ),
        "reap-stuck-jobs": _every(
            REAP_STUCK_JOBS,
            MAINTENANCE_QUEUE,
            settings.maintenance.reaper_interval_minutes,  # P-60
        ),
        # Cron in PURGE_TIMEZONE (the Celery app timezone), P-50.
        "purge-expired": {
            "task": PURGE_EXPIRED,
            "schedule": cron(settings.retention.purge_cron),
            "options": {"queue": MAINTENANCE_QUEUE, "expires": 3600},
        },
    }


def cron(expression: str) -> crontab:
    minute, hour, day_of_month, month_of_year, day_of_week = expression.split()
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


def _every(task: str, queue: str, minutes: int) -> dict[str, Any]:
    interval = timedelta(minutes=minutes)
    return {
        "task": task,
        "schedule": interval,
        # A run that waited longer than one interval is dropped; the next one covers it.
        "options": {"queue": queue, "expires": int(interval.total_seconds())},
    }
