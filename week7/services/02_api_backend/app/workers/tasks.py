"""Beat jobs: ask 07 football-data to run its work. 07 does the work; we only trigger.

`triggered_by` is always "beat" (CONTRACT §7). A 409 (a job of the same kind is already
running, the matchweek is not finished, the report is already published) is expected
on a timetable and is logged, not retried.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

log = get_logger(__name__)

_TRANSIENT = (httpx.TransportError,)


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    settings = get_settings()
    request_id = str(new_id())
    response = httpx.post(
        f"{settings.football_data_url.rstrip('/')}{path}",
        json=body,
        headers={"X-Request-ID": request_id},
        timeout=settings.football_data_timeout_seconds,
    )
    if response.status_code == 409:
        code = response.json().get("code") if response.content else None
        log.info("beat_trigger_skipped", path=path, code=code, request_id=request_id)
        return None
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    log.info("beat_triggered", path=path, job_id=result.get("job_id"), request_id=request_id)
    return result


@celery_app.task(
    autoretry_for=_TRANSIENT, retry_backoff=30, retry_kwargs={"max_retries": 3}, acks_late=True
)
def trigger_ingest(scope: str) -> dict[str, Any] | None:
    return _post("/ingest/run", {"scope": scope, "triggered_by": "beat"})


@celery_app.task(
    autoretry_for=_TRANSIENT, retry_backoff=60, retry_kwargs={"max_retries": 3}, acks_late=True
)
def trigger_weekly_report() -> dict[str, Any] | None:
    # No season / matchweek: 07 picks the latest matchweek that has finished.
    return _post("/reports/weekly/run", {"triggered_by": "beat"})
