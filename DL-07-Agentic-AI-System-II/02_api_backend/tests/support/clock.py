from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class FakeClock:
    current: datetime = field(default_factory=lambda: datetime(2026, 9, 17, 8, 0, tzinfo=UTC))
    mono: float = 1000.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.mono += seconds
