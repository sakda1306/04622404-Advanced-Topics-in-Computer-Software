"""Scheduled re-assessment of trips with live alerts on (D-65, D-66).

The scan only queues jobs; the recommendation worker runs them, and the repository
stores an in-app alert message when the risk changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.domain.enums import RequestMode, RequestSource
from app.domain.errors import InvalidInput
from app.services.ports import TripRepository
from app.services.trip_service import TripService

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ScanResult:
    queued: int
    skipped: int


class TripAlertService:
    def __init__(
        self,
        *,
        trips: TripRepository,
        trip_service: TripService,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = trips
        self._trips = trip_service
        self._settings = settings
        self._clock = clock

    async def scan(self) -> ScanResult:
        config = self._settings.trips
        due = await self._repo.due_for_alerts(
            self._clock.now(),
            window=timedelta(hours=config.trip_alert_window_hours),
            stale_after=timedelta(minutes=config.trip_alert_reassess_minutes),
            # A job older than its slot lifetime is stuck, not running (P-04 x 2).
            processing_after=timedelta(seconds=self._settings.agent.job_agent_timeout_seconds * 2),
            limit=config.trip_alert_batch_size,
        )
        queued = skipped = 0
        for item in due:
            user = await self._repo.user(item.user_id)
            if user is None:
                skipped += 1
                continue
            try:
                await self._trips.assess(
                    user,
                    item.trip_id,
                    mode=RequestMode.ASYNC,
                    language=None,
                    accept_language=None,
                    correlation_id=str(new_id()),
                    source=RequestSource.TRIP_ALERT,
                )
            except (AppError, InvalidInput) as exc:
                code = exc.code.value if isinstance(exc, AppError) else exc.issues[0].code
                log.warning("trip_alert_skipped", trip_id=str(item.trip_id), reason=code)
                skipped += 1
                continue
            queued += 1
        log.info("trip_alert_scan", due=len(due), queued=queued, skipped=skipped)
        return ScanResult(queued=queued, skipped=skipped)
