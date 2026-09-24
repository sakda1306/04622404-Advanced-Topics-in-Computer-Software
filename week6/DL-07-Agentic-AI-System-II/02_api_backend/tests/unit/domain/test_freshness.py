from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import DataCategory
from app.domain.freshness import (
    FreshnessInput,
    FreshnessItem,
    FreshnessReport,
    StalenessPolicy,
    assess_freshness,
    compute_valid_until,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
W, T, D, K = (
    DataCategory.WEATHER,
    DataCategory.TRANSPORT,
    DataCategory.DISASTER,
    DataCategory.KNOWLEDGE_BASE,
)
POLICY = StalenessPolicy.default()


def item_of(report: FreshnessReport, category: DataCategory) -> FreshnessItem:
    item = report.get(category)
    assert item is not None, f"{category} missing from report"
    return item


def ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def test_default_policy_limits_follow_p28() -> None:
    report = assess_freshness(
        [
            FreshnessInput(W, ago(60)),
            FreshnessInput(D, ago(15)),
            FreshnessInput(T, ago(10.01)),
        ],
        now=NOW,
        policy=POLICY,
    )

    assert [(i.category, i.is_stale) for i in report.items] == [(W, False), (D, False), (T, True)]


def test_disaster_data_ages_out_faster_than_weather() -> None:
    report = assess_freshness(
        [FreshnessInput(W, ago(16)), FreshnessInput(D, ago(16))], now=NOW, policy=POLICY
    )

    assert item_of(report, W).is_stale is False
    assert item_of(report, D).is_stale is True


def test_age_is_reported_in_seconds() -> None:
    report = assess_freshness([FreshnessInput(W, ago(30))], now=NOW, policy=POLICY)

    assert item_of(report, W).age_seconds == 1800


def test_missing_timestamp_is_stale_without_age() -> None:
    report = assess_freshness([FreshnessInput(D, None)], now=NOW, policy=POLICY)

    item = item_of(report, D)
    assert item.is_stale is True
    assert item.age_seconds is None


def test_timestamp_far_in_the_future_is_distrusted() -> None:
    report = assess_freshness(
        [
            FreshnessInput(W, NOW + timedelta(minutes=4)),
            FreshnessInput(D, NOW + timedelta(hours=2)),
        ],
        now=NOW,
        policy=POLICY,
    )

    assert item_of(report, W).is_stale is False
    assert item_of(report, W).age_seconds == 0
    assert item_of(report, D).is_stale is True


def test_category_without_limit_never_goes_stale() -> None:
    report = assess_freshness([FreshnessInput(K, ago(60 * 24 * 365))], now=NOW, policy=POLICY)

    assert item_of(report, K).is_stale is False


def test_duplicate_categories_keep_the_newest_timestamp() -> None:
    report = assess_freshness(
        [FreshnessInput(W, ago(90)), FreshnessInput(W, None), FreshnessInput(W, ago(5))],
        now=NOW,
        policy=POLICY,
    )

    assert len(report.items) == 1
    assert item_of(report, W).updated_at == ago(5)


def test_overall_and_per_category_checks() -> None:
    fresh = assess_freshness([FreshnessInput(W, ago(1))], now=NOW, policy=POLICY)
    mixed = assess_freshness(
        [FreshnessInput(W, ago(1)), FreshnessInput(T, ago(30))], now=NOW, policy=POLICY
    )

    assert fresh.overall_is_stale is False
    assert mixed.overall_is_stale is True
    assert fresh.is_fresh(W) is True
    assert fresh.is_fresh(D) is False  # not reported at all


def test_valid_until_is_the_earliest_expiry() -> None:
    report = assess_freshness(
        [FreshnessInput(W, ago(50)), FreshnessInput(D, ago(5)), FreshnessInput(K, ago(1))],
        now=NOW,
        policy=POLICY,
    )

    # weather expires in 10 min, disaster in 10 min at 08:10, agent says 09:00
    assert compute_valid_until(
        NOW + timedelta(hours=1), report, policy=POLICY, now=NOW
    ) == datetime(2026, 9, 17, 8, 10, tzinfo=UTC)


def test_valid_until_prefers_an_earlier_agent_value() -> None:
    report = assess_freshness([FreshnessInput(W, ago(1))], now=NOW, policy=POLICY)
    agent_value = NOW + timedelta(minutes=3)

    assert compute_valid_until(agent_value, report, policy=POLICY, now=NOW) == agent_value


def test_valid_until_is_never_in_the_past() -> None:
    report = assess_freshness([FreshnessInput(T, ago(45))], now=NOW, policy=POLICY)

    assert compute_valid_until(None, report, policy=POLICY, now=NOW) == NOW


def test_valid_until_is_none_without_any_bound() -> None:
    report = assess_freshness([FreshnessInput(K, ago(1))], now=NOW, policy=POLICY)

    assert compute_valid_until(None, report, policy=POLICY, now=NOW) is None
