"""How old each data source is, and how long a recommendation stays valid (R-07)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.enums import DataCategory

_DEFAULT_MAX_AGE = {  # P-28
    DataCategory.WEATHER: timedelta(minutes=60),
    DataCategory.DISASTER: timedelta(minutes=15),
    DataCategory.TRANSPORT: timedelta(minutes=10),
}


@dataclass(frozen=True, slots=True)
class StalenessPolicy:
    max_age: Mapping[DataCategory, timedelta]
    # Timestamps slightly ahead of our clock are normal (clock skew); far ahead is bad data.
    future_tolerance: timedelta = field(default=timedelta(minutes=5))

    @classmethod
    def default(cls) -> StalenessPolicy:
        return cls(max_age=dict(_DEFAULT_MAX_AGE))


@dataclass(frozen=True, slots=True)
class FreshnessInput:
    category: DataCategory
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class FreshnessItem:
    category: DataCategory
    updated_at: datetime | None
    age_seconds: int | None
    is_stale: bool


@dataclass(frozen=True, slots=True)
class FreshnessReport:
    items: tuple[FreshnessItem, ...]

    @property
    def overall_is_stale(self) -> bool:
        return any(item.is_stale for item in self.items)

    def get(self, category: DataCategory) -> FreshnessItem | None:
        return next((item for item in self.items if item.category is category), None)

    def is_fresh(self, category: DataCategory) -> bool:
        item = self.get(category)
        return item is not None and not item.is_stale


def _newest(inputs: Iterable[FreshnessInput]) -> dict[DataCategory, datetime | None]:
    newest: dict[DataCategory, datetime | None] = {}
    for entry in inputs:
        current = newest.get(entry.category)
        if entry.category not in newest or (
            entry.updated_at is not None and (current is None or entry.updated_at > current)
        ):
            newest[entry.category] = entry.updated_at
    return newest


def assess_freshness(
    items: Iterable[FreshnessInput], *, now: datetime, policy: StalenessPolicy
) -> FreshnessReport:
    assessed = []
    for category, updated_at in _newest(items).items():
        if updated_at is None:
            assessed.append(FreshnessItem(category, None, None, True))
            continue
        if updated_at - now > policy.future_tolerance:
            assessed.append(FreshnessItem(category, updated_at, 0, True))
            continue
        age = max(now - updated_at, timedelta(0))
        limit = policy.max_age.get(category)
        stale = limit is not None and age > limit
        assessed.append(FreshnessItem(category, updated_at, int(age.total_seconds()), stale))
    return FreshnessReport(tuple(assessed))


def compute_valid_until(
    agent_valid_until: datetime | None,
    report: FreshnessReport,
    *,
    policy: StalenessPolicy,
    now: datetime,
) -> datetime | None:
    """Earliest of the Agent's value and each source's expiry, never before `now`."""
    candidates = [agent_valid_until] if agent_valid_until is not None else []
    for item in report.items:
        limit = policy.max_age.get(item.category)
        if item.updated_at is not None and limit is not None:
            candidates.append(item.updated_at + limit)
    if not candidates:
        return None
    return max(min(candidates), now)
