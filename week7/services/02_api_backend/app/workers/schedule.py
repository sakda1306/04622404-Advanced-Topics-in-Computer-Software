"""Beat timetable from CONTRACT.md §7, in Asia/Bangkok time.

- ingest fixtures: every 30 min from Fri 18:00 to Tue 06:00 (match window), every 6 h otherwise
- ingest details:  every 2 h
- weekly report:   Mon 09:00 and Tue 09:00 (for Monday-night games)

Celery crontab cannot express "Fri 18:00 to Tue 06:00" in one entry, so the window
is split into several entries that do not overlap.
"""

from __future__ import annotations

from typing import Any

from celery.schedules import crontab

INGEST_TASK = "app.workers.tasks.trigger_ingest"
REPORT_TASK = "app.workers.tasks.trigger_weekly_report"

HALF_HOURLY = "0,30"
SIX_HOURLY = "0,6,12,18"


def _entry(task: str, schedule: crontab, **kwargs: Any) -> dict[str, Any]:
    return {"task": task, "schedule": schedule, "kwargs": kwargs}


def beat_schedule() -> dict[str, dict[str, Any]]:
    fixtures = {"scope": "fixtures"}
    return {
        # Match window: Fri 18:00 -> Tue 06:00, every 30 minutes.
        "fixtures-fri-evening": _entry(
            INGEST_TASK, crontab(minute=HALF_HOURLY, hour="18-23", day_of_week="fri"), **fixtures
        ),
        "fixtures-weekend": _entry(
            INGEST_TASK, crontab(minute=HALF_HOURLY, day_of_week="sat,sun,mon"), **fixtures
        ),
        "fixtures-tue-early": _entry(
            INGEST_TASK, crontab(minute=HALF_HOURLY, hour="0-5", day_of_week="tue"), **fixtures
        ),
        "fixtures-tue-0600": _entry(
            INGEST_TASK, crontab(minute=0, hour=6, day_of_week="tue"), **fixtures
        ),
        # Outside the window: every 6 hours.
        "fixtures-tue-rest": _entry(
            INGEST_TASK, crontab(minute=0, hour="12,18", day_of_week="tue"), **fixtures
        ),
        "fixtures-midweek": _entry(
            INGEST_TASK, crontab(minute=0, hour=SIX_HOURLY, day_of_week="wed,thu"), **fixtures
        ),
        "fixtures-fri-day": _entry(
            INGEST_TASK, crontab(minute=0, hour="0,6,12", day_of_week="fri"), **fixtures
        ),
        # Offset from the fixtures runs so both jobs do not start together.
        "details-every-2h": _entry(INGEST_TASK, crontab(minute=15, hour="*/2"), scope="details"),
        "weekly-report": _entry(REPORT_TASK, crontab(minute=0, hour=9, day_of_week="mon,tue")),
    }
