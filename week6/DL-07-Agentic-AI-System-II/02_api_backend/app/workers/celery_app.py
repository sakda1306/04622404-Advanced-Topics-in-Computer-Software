"""Celery application (docs/04_project_structure.md section 6).

Start a worker and the scheduler with:
    celery -A app.workers.celery_app:celery_app worker -Q recommendations,alerts,maintenance
    celery -A app.workers.celery_app:celery_app beat --schedule /tmp/celerybeat-schedule

The app is created on first access, so importing this module needs no configuration.
Messages carry only ids; results live in PostgreSQL and Redis, not in Celery.
"""

from __future__ import annotations

from functools import lru_cache

from celery import Celery

from app.core.config import Settings, get_settings

RECOMMENDATION_QUEUE = "recommendations"
ALERT_QUEUE = "alerts"
MAINTENANCE_QUEUE = "maintenance"
RUN_RECOMMENDATION = "app.workers.tasks.recommendation.run_recommendation"
SCAN_TRIP_ALERTS = "app.workers.tasks.trip_alerts.scan_trip_alerts"
REAP_STUCK_JOBS = "app.workers.tasks.maintenance.reap_stuck_jobs"
DELETE_ACCOUNT = "app.workers.tasks.maintenance.delete_account"
BUILD_DATA_EXPORT = "app.workers.tasks.maintenance.build_data_export"
PURGE_EXPIRED = "app.workers.tasks.maintenance.purge_expired"
BUILD_TRAINING_EXPORT = "app.workers.tasks.maintenance.build_training_export"


def create_celery(settings: Settings) -> Celery:
    from app.workers.schedule import beat_schedule

    app = Celery("tsa", broker=settings.redis.broker_url(), set_as_current=False)
    app.conf.update(
        include=[
            "app.workers.tasks.recommendation",
            "app.workers.tasks.trip_alerts",
            "app.workers.tasks.maintenance",
        ],
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        accept_content=["json"],
        task_default_queue=RECOMMENDATION_QUEUE,
        task_routes={
            RUN_RECOMMENDATION: {"queue": RECOMMENDATION_QUEUE},
            SCAN_TRIP_ALERTS: {"queue": ALERT_QUEUE},
            REAP_STUCK_JOBS: {"queue": MAINTENANCE_QUEUE},
            DELETE_ACCOUNT: {"queue": MAINTENANCE_QUEUE},
            BUILD_DATA_EXPORT: {"queue": MAINTENANCE_QUEUE},
            PURGE_EXPIRED: {"queue": MAINTENANCE_QUEUE},
            BUILD_TRAINING_EXPORT: {"queue": MAINTENANCE_QUEUE},
        },
        beat_schedule=beat_schedule(settings),
        # Beat reads cron entries in this zone (P-50); times on the wire stay UTC.
        timezone=settings.retention.purge_timezone,
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        worker_hijack_root_logger=False,
        # structlog writes JSON to stdout; Celery's stdout proxy would loop it back into logging.
        worker_redirect_stdouts=False,
        worker_send_task_events=False,
    )
    return app


@lru_cache
def get_celery() -> Celery:
    celery = create_celery(get_settings())
    # Registers the tasks on this app (they are declared with shared_task) and the
    # process signal handlers (logging, tracing, metrics).
    from app.workers import signals  # noqa: F401
    from app.workers.tasks import maintenance, recommendation, trip_alerts  # noqa: F401

    return celery


def __getattr__(name: str) -> Celery:
    if name == "celery_app":
        return get_celery()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
