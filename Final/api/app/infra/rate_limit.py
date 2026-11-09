"""In-process fixed-window counters.

The api runs as one uvicorn worker (Design.md §8), so a dict is enough; counters reset
on restart. Login counts attempts per email only: every user reaches the api through the
web proxy and so shares one client IP.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.core.errors import AppError, ErrorCode

WINDOW_SECONDS = 60


class AttemptLimiter:
    """At most `limit` unsuccessful attempts per key and window.

    `acquire` counts the attempt before the slow work (bcrypt) starts, with no `await`
    between the check and the increment, so parallel requests cannot all pass the check.
    `succeed` clears the key, so a correct password does not use up the allowance.
    """

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}

    def _current(self, key: str) -> tuple[float, int]:
        now = self._clock()
        window = self._windows.get(key)
        if window is None or now - window[0] >= WINDOW_SECONDS:
            return now, 0
        return window

    def acquire(self, key: str) -> None:
        started, count = self._current(key)
        if count >= self.limit:
            retry_after = max(1, int(WINDOW_SECONDS - (self._clock() - started)))
            raise AppError(ErrorCode.RATE_LIMITED, retry_after=retry_after)
        self._windows[key] = (started, count + 1)
        if len(self._windows) > 10_000:
            self._drop_expired()

    def succeed(self, key: str) -> None:
        self._windows.pop(key, None)

    def _drop_expired(self) -> None:
        now = self._clock()
        self._windows = {k: v for k, v in self._windows.items() if now - v[0] < WINDOW_SECONDS}
