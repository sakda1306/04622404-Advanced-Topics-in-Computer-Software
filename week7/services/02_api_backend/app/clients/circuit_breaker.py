"""In-process circuit breaker for the router.

closed    -> calls pass; failures inside the window are counted
open      -> calls are rejected until `reset_seconds` have passed
half_open -> one probe call is let through; success closes, failure re-opens

Each api process keeps its own state. That is enough here: the point is to stop a
process from queueing 45-second calls to a router that is already down.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        window_seconds: float,
        reset_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._window = window_seconds
        self._reset = reset_seconds
        self._clock = clock
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._clock() - self._opened_at >= self._reset:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def retry_after(self) -> int:
        if self._opened_at is None:
            return 0
        return max(int(self._opened_at + self._reset - self._clock() + 0.999), 1)

    def allow(self) -> bool:
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.HALF_OPEN and not self._probe_in_flight:
            self._probe_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        self._failures.clear()
        self._opened_at = None
        self._probe_in_flight = False

    def record_failure(self) -> None:
        now = self._clock()
        if self._probe_in_flight or self.state is not BreakerState.CLOSED:
            self._opened_at = now
            self._probe_in_flight = False
            return
        self._failures.append(now)
        while self._failures and self._failures[0] <= now - self._window:
            self._failures.popleft()
        if len(self._failures) >= self._threshold:
            self._opened_at = now
            self._failures.clear()
