# Step 5.5 — Domain Layer & Safety Gate Implementation Plan

**Goal:** Pure-Python domain rules that turn an Agent result into a safe, honest recommendation: output sanitizing (R-06), data freshness and `valid_until` (R-07), the Safety Gate (R-01 to R-05), and normalization of incoming travel requests.

**Architecture:** Everything lives in `app/domain/` and imports only the standard library, `app/core/clock`-free values (callers pass `now`) and `app/core/geo`. No FastAPI, SQLAlchemy, Redis, httpx or Pydantic API schemas. The service layer (step 5.6) maps Agent contracts and API schemas to these dataclasses. Shared vocabulary (`DataCategory`, `ServiceState`) moves to `app/domain/enums.py`; the Agent contract re-uses it.

**Tech Stack:** Python 3.12 dataclasses, `zoneinfo` + `tzdata`, pytest.

**Spec:** `docs/02_api_spec.md` §1 (conventions), §5.1 (TravelRequest validation), §5.3–5.4 (response and Safety Gate rules R-01..R-07), §2 (P-28, P-41..P-43).

## Global Constraints

- Python ≥ 3.12; domain modules must not import `fastapi`, `sqlalchemy`, `redis`, `httpx`, `app.api`, `app.schemas`, `app.infrastructure`.
- Stale limits (P-28): weather 60 min, disaster 15 min, transport 10 min.
- Question ≤ 1,000 characters (P-41); waypoints ≤ 5 (P-42); departure ≤ 14 days ahead (P-43), not more than 1 hour in the past (spec §5.1).
- Coordinates WGS84, lat ∈ [-90, 90], lon ∈ [-180, 180], at most 6 decimals.
- Supported languages: `th`, `en`; default `th`.
- When weather or disaster data is missing, unavailable or stale the result must never be `TRAVEL_NORMALLY`.
- `risk_level = HIGH` must never be combined with `TRAVEL_NORMALLY`.
- Checkpoints: the user commits and pushes; ask before any git write. No AI attribution anywhere.
- Test commands: `python -m uv run pytest ...` (uv is not on PATH on this machine).

---

## File Map

| File | Responsibility |
|---|---|
| `app/domain/enums.py` (modify) | add `DataCategory`, `ServiceState`, `WarningCode`, `TravelMode`, `AvoidOption`, `MobilityNeed` |
| `app/infrastructure/agent/contracts.py` (modify) | import `DataCategory`, `ServiceState` from domain |
| `app/domain/errors.py` (create) | `DomainError`, `FieldIssue`, `InvalidInput` |
| `app/domain/sanitizer.py` (create) | R-06: `clean_text`, `truncate`, `safe_url`, `strip_internal` |
| `app/domain/freshness.py` (create) | `StalenessPolicy`, `assess_freshness`, `FreshnessReport`, R-07 `compute_valid_until` |
| `app/domain/safety_gate.py` (create) | R-01..R-05: `GateInput`, `GateResult`, `apply_safety_gate`, `SafetyGateRejection` |
| `app/core/geo.py` (create) | `haversine_m` |
| `app/domain/normalization.py` (create) | `normalize_travel_request`, `negotiate_language` |
| `tests/unit/domain/*` (create) | one test file per module |
| `pyproject.toml` (modify) | add `tzdata` |
| `docs/02_api_spec.md`, `docs/04_project_structure.md`, `README.md` (modify) | record decisions |

---

### Task 1: Sanitizer (R-06)

**Files:**
- Create: `app/domain/sanitizer.py`
- Test: `tests/unit/domain/test_sanitizer.py`

**Interfaces:**
- Produces: `clean_text(value: str | None) -> str | None`, `truncate(value: str, max_length: int) -> str`, `safe_url(value: str | None, *, max_length: int = 2048) -> str | None`, `strip_internal(data: Any) -> Any`, `INTERNAL_KEYS: frozenset[str]`

- [x] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from app.domain.sanitizer import clean_text, safe_url, strip_internal, truncate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello  ", "hello"),
        ("line1\r\nline2\rline3", "line1\nline2\nline3"),
        ("tab\tok", "tab\tok"),
        ("bell\x07null\x00esc\x1b", "bellnullesc"),
        ("rtl‮override​zero", "rtloverridezero"),
        ("é", "é"),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_clean_text(raw: str | None, expected: str | None) -> None:
    assert clean_text(raw) == expected


def test_truncate_keeps_short_text_and_cuts_long_text() -> None:
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdef", 4) == "abc…"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.tmd.go.th/warn?id=1", "https://www.tmd.go.th/warn?id=1"),
        (" https://example.org ", "https://example.org"),
        ("http://example.org", None),
        ("javascript:alert(1)", None),
        ("data:text/html;base64,xx", None),
        ("https://user:pw@example.org", None),
        ("https:///no-host", None),
        ("ftp://example.org", None),
        ("https://example.org/" + "a" * 2100, None),
        ("", None),
        (None, None),
    ],
)
def test_safe_url(raw: str | None, expected: str | None) -> None:
    assert safe_url(raw) == expected


def test_strip_internal_removes_internal_fields_at_any_depth() -> None:
    payload = {
        "summary": "ok",
        "diagnostics": {"trace_id": "t"},
        "prompt": "system prompt",
        "_debug": 1,
        "internal_score": 3,
        "routes": {"primary": {"route_id": "r1", "cost": 12, "legs": [{"mode": "BUS", "trace": "x"}]}},
    }

    assert strip_internal(payload) == {
        "summary": "ok",
        "routes": {"primary": {"route_id": "r1", "legs": [{"mode": "BUS"}]}},
    }


def test_strip_internal_does_not_modify_the_input() -> None:
    payload = {"a": {"diagnostics": 1}}

    strip_internal(payload)

    assert payload == {"a": {"diagnostics": 1}}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/unit/domain/test_sanitizer.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.domain.sanitizer'`

- [x] **Step 3: Write the implementation**

```python
"""Output hygiene for text and links that reach users (rule R-06)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# C0/C1 controls except tab and newline, plus zero-width and bidi override characters
# that can hide or reorder text.
_UNSAFE_CHARS = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]"
)
_ELLIPSIS = "…"

INTERNAL_KEYS = frozenset(
    {"diagnostics", "prompt", "prompts", "tool_trace", "trace", "cost", "debug", "internal"}
)


def clean_text(value: str | None) -> str | None:
    """Normalize to NFC, unify newlines, drop unsafe characters. Blank -> None."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _UNSAFE_CHARS.sub("", text).strip()
    return text or None


def truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + _ELLIPSIS


def safe_url(value: str | None, *, max_length: int = 2048) -> str | None:
    """Return the URL only if it is an https link without embedded credentials."""
    if not value:
        return None
    candidate = value.strip()
    if len(candidate) > max_length:
        return None
    parts = urlsplit(candidate)
    if parts.scheme != "https" or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return urlunsplit(parts)


def _is_internal(key: str) -> bool:
    return key in INTERNAL_KEYS or key.startswith(("_", "internal_"))


def strip_internal(data: Any) -> Any:
    """Copy of `data` without fields that must never reach users."""
    if isinstance(data, dict):
        return {k: strip_internal(v) for k, v in data.items() if not _is_internal(str(k))}
    if isinstance(data, list):
        return [strip_internal(item) for item in data]
    return data
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m uv run pytest tests/unit/domain/test_sanitizer.py -q`
Expected: all pass

- [x] **Step 5: Checkpoint** — no commit; the user commits.

---

### Task 2: Freshness and `valid_until` (R-07)

**Files:**
- Modify: `app/domain/enums.py` (add `DataCategory`, `ServiceState`)
- Modify: `app/infrastructure/agent/contracts.py` (import them instead of defining)
- Create: `app/domain/freshness.py`
- Test: `tests/unit/domain/test_freshness.py`

**Interfaces:**
- Produces:
  - `DataCategory` (`WEATHER`, `TRANSPORT`, `DISASTER`, `KNOWLEDGE_BASE`), `ServiceState` (`ok`, `degraded`, `unavailable`, `not_used`) in `app.domain.enums`
  - `FreshnessInput(category: DataCategory, updated_at: datetime | None)`
  - `FreshnessItem(category, updated_at, age_seconds: int | None, is_stale: bool)`
  - `FreshnessReport(items: tuple[FreshnessItem, ...])` with `overall_is_stale: bool`, `get(category) -> FreshnessItem | None`, `is_fresh(category) -> bool`
  - `StalenessPolicy(max_age: Mapping[DataCategory, timedelta], future_tolerance: timedelta = 5 min)` and `StalenessPolicy.default()` (P-28)
  - `assess_freshness(items: Iterable[FreshnessInput], *, now: datetime, policy: StalenessPolicy) -> FreshnessReport`
  - `compute_valid_until(agent_valid_until: datetime | None, report: FreshnessReport, *, policy: StalenessPolicy, now: datetime) -> datetime | None`

- [x] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import DataCategory
from app.domain.freshness import (
    FreshnessInput,
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


def test_age_is_reported_in_seconds() -> None:
    report = assess_freshness([FreshnessInput(W, ago(30))], now=NOW, policy=POLICY)

    assert report.get(W).age_seconds == 1800


def test_missing_timestamp_is_stale_without_age() -> None:
    report = assess_freshness([FreshnessInput(D, None)], now=NOW, policy=POLICY)

    item = report.get(D)
    assert item.is_stale is True
    assert item.age_seconds is None


def test_timestamp_far_in_the_future_is_distrusted() -> None:
    report = assess_freshness(
        [FreshnessInput(W, NOW + timedelta(minutes=4)), FreshnessInput(D, NOW + timedelta(hours=2))],
        now=NOW,
        policy=POLICY,
    )

    assert report.get(W).is_stale is False
    assert report.get(W).age_seconds == 0
    assert report.get(D).is_stale is True


def test_category_without_limit_never_goes_stale() -> None:
    report = assess_freshness([FreshnessInput(K, ago(60 * 24 * 365))], now=NOW, policy=POLICY)

    assert report.get(K).is_stale is False


def test_duplicate_categories_keep_the_newest_timestamp() -> None:
    report = assess_freshness(
        [FreshnessInput(W, ago(90)), FreshnessInput(W, None), FreshnessInput(W, ago(5))],
        now=NOW,
        policy=POLICY,
    )

    assert len(report.items) == 1
    assert report.get(W).updated_at == ago(5)


def test_overall_and_per_category_checks() -> None:
    fresh = assess_freshness([FreshnessInput(W, ago(1))], now=NOW, policy=POLICY)
    mixed = assess_freshness([FreshnessInput(W, ago(1)), FreshnessInput(T, ago(30))], now=NOW, policy=POLICY)

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
    assert compute_valid_until(NOW + timedelta(hours=1), report, policy=POLICY, now=NOW) == datetime(
        2026, 9, 17, 8, 10, tzinfo=UTC
    )


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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/unit/domain/test_freshness.py -q`
Expected: `ImportError` for `DataCategory` / `app.domain.freshness`

- [x] **Step 3: Write the implementation**

Append to `app/domain/enums.py`:

```python
class DataCategory(StrEnum):
    WEATHER = "WEATHER"
    TRANSPORT = "TRANSPORT"
    DISASTER = "DISASTER"
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"


class ServiceState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_USED = "not_used"
```

In `app/infrastructure/agent/contracts.py` delete the local `ServiceState` and `DataCategory` classes and import them:

```python
from app.domain.enums import DataCategory, JobStage, RecommendationType, RiskLevel, ServiceState
```

Create `app/domain/freshness.py`:

```python
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
```

- [x] **Step 4: Run tests to verify they pass** (also the contract tests, which use the moved enums)

Run: `python -m uv run pytest tests/unit/domain/test_freshness.py tests/contract tests/unit/test_agent_client.py -q`
Expected: all pass

- [x] **Step 5: Checkpoint** — no commit.

---

### Task 3: Safety Gate (R-01 … R-05)

**Files:**
- Modify: `app/domain/enums.py` (add `WarningCode`)
- Create: `app/domain/errors.py`
- Create: `app/domain/safety_gate.py`
- Test: `tests/unit/domain/test_safety_gate.py`

**Interfaces:**
- Consumes: `FreshnessReport`, `FreshnessInput`, `assess_freshness`, `StalenessPolicy` (Task 2); `DataCategory`, `ServiceState` (Task 2)
- Produces:
  - `WarningCode` (`DATA_INCOMPLETE`, `DATA_STALE`, `SERVICE_DEGRADED`, `LOW_CONFIDENCE`, `OUTSIDE_COVERAGE`)
  - `DomainError(Exception)`
  - `GateInput(status: RecommendationStatus, risk_level: RiskLevel | None, risk_confidence: float | None, recommendation_type: RecommendationType | None, summary: str | None, has_clarification: bool, emergency_instructions: Mapping[str, Any] | None, service_status: Mapping[str, ServiceState], freshness: FreshnessReport)`
  - `GateWarning(code: WarningCode, message: str)`
  - `GateResult(status, recommendation_type, summary, emergency_instructions, warnings: tuple[GateWarning, ...], applied_rules: tuple[str, ...])`
  - `SafetyGateRejection(DomainError)` with `rule: str`, `needs_safety_review: bool`, `agent_failed: bool`
  - `apply_safety_gate(inp: GateInput, *, language: str, emergency_fallback: Mapping[str, Any] | None, low_confidence_below: float = 0.5) -> GateResult`

Rule decisions (recorded as D-34 in docs):
- R-02 nulls only `TRAVEL_NORMALLY`; a more cautious action (`CHANGE_ROUTE`, `DELAY_TRAVEL`, `AVOID_TRAVEL`) stays, but the status becomes `partial_result` with the warning.
- For R-02, weather/disaster count as missing when their service state is `unavailable`, `not_used` or absent, or their freshness item is absent, has no timestamp or is stale.
- Agent `status = failed` → rejection with `agent_failed=True` (service maps to 503).
- `completed` without risk or recommendation → rejection `R-05` (contract).
- Confidence below 0.5 → `LOW_CONFIDENCE` warning only.

- [x] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.enums import (
    DataCategory,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    ServiceState,
    WarningCode,
)
from app.domain.freshness import FreshnessInput, StalenessPolicy, assess_freshness
from app.domain.safety_gate import (
    GateInput,
    SafetyGateRejection,
    apply_safety_gate,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
OK = ServiceState.OK
FALLBACK: Mapping[str, Any] = {
    "what_to_do_now": "Move to a safe place.",
    "safety_steps": [],
    "contacts": [{"name": "Police", "phone": "191"}],
    "nearest_support": [],
}
AGENT_STEPS: Mapping[str, Any] = {**FALLBACK, "what_to_do_now": "Agent steps"}


def report(**ages: float | None) -> Any:
    items = [
        FreshnessInput(DataCategory(name.upper()), None if m is None else NOW - timedelta(minutes=m))
        for name, m in ages.items()
    ]
    return assess_freshness(items, now=NOW, policy=StalenessPolicy.default())


def gate_input(**overrides: Any) -> GateInput:
    base = GateInput(
        status=RecommendationStatus.COMPLETED,
        risk_level=RiskLevel.LOW,
        risk_confidence=0.9,
        recommendation_type=RecommendationType.TRAVEL_NORMALLY,
        summary="Safe to travel.",
        has_clarification=False,
        emergency_instructions=None,
        service_status={"weather": OK, "transport": OK, "disaster": OK},
        freshness=report(weather=5, transport=1, disaster=1),
    )
    return replace(base, **overrides)


def run(inp: GateInput, *, language: str = "en", fallback: Mapping[str, Any] | None = FALLBACK) -> Any:
    return apply_safety_gate(inp, language=language, emergency_fallback=fallback)


def codes(result: Any) -> list[WarningCode]:
    return [w.code for w in result.warnings]


# ------------------------------------------------------------ clean pass


def test_complete_and_fresh_result_passes_unchanged() -> None:
    result = run(gate_input())

    assert result.status is RecommendationStatus.COMPLETED
    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert result.summary == "Safe to travel."
    assert result.warnings == ()
    assert result.applied_rules == ()


# ------------------------------------------------------------ R-02


@pytest.mark.parametrize(
    ("overrides", "warning"),
    [
        ({"service_status": {"weather": OK, "transport": OK, "disaster": ServiceState.UNAVAILABLE}},
         WarningCode.DATA_INCOMPLETE),
        ({"service_status": {"weather": ServiceState.NOT_USED, "transport": OK, "disaster": OK}},
         WarningCode.DATA_INCOMPLETE),
        ({"service_status": {"transport": OK, "disaster": OK}}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1)}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1, disaster=None)}, WarningCode.DATA_INCOMPLETE),
        ({"freshness": report(weather=5, transport=1, disaster=16)}, WarningCode.DATA_STALE),
        ({"freshness": report(weather=61, transport=1, disaster=1)}, WarningCode.DATA_STALE),
    ],
)
def test_r02_missing_or_stale_critical_data_blocks_travel_normally(
    overrides: dict[str, Any], warning: WarningCode
) -> None:
    result = run(gate_input(**overrides))

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is None
    assert "incomplete" in (result.summary or "")
    assert warning in codes(result)
    assert "R-02" in result.applied_rules


def test_r02_message_follows_the_language() -> None:
    inp = gate_input(freshness=report(weather=5, transport=1))

    assert "ไม่ครบถ้วน" in (run(inp, language="th").summary or "")


@pytest.mark.parametrize(
    "action",
    [RecommendationType.AVOID_TRAVEL, RecommendationType.DELAY_TRAVEL, RecommendationType.CHANGE_ROUTE],
)
def test_r02_keeps_a_more_cautious_action(action: RecommendationType) -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.MEDIUM,
            recommendation_type=action,
            summary="Delay your trip.",
            freshness=report(weather=5, transport=1),
        )
    )

    assert result.recommendation_type is action
    assert result.summary == "Delay your trip."
    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert WarningCode.DATA_INCOMPLETE in codes(result)


def test_r02_does_not_fire_when_only_transport_is_stale() -> None:
    result = run(gate_input(freshness=report(weather=5, transport=30, disaster=1)))

    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert "R-02" not in result.applied_rules


# ------------------------------------------------------------ R-03


@pytest.mark.parametrize(
    "status",
    [
        {"weather": OK, "transport": ServiceState.DEGRADED, "disaster": OK},
        {"weather": OK, "transport": OK, "disaster": OK, "llm": ServiceState.UNAVAILABLE},
        {"weather": ServiceState.DEGRADED, "transport": OK, "disaster": OK},
    ],
)
def test_r03_degraded_dependency_makes_a_partial_result(status: dict[str, ServiceState]) -> None:
    result = run(gate_input(service_status=status))

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    assert codes(result) == [WarningCode.SERVICE_DEGRADED]
    assert result.applied_rules == ("R-03",)


def test_r03_not_used_service_is_not_degraded() -> None:
    status = {"weather": OK, "transport": OK, "disaster": OK, "rag": ServiceState.NOT_USED}

    assert run(gate_input(service_status=status)).warnings == ()


# ------------------------------------------------------------ R-01


def test_r01_high_risk_without_steps_gets_the_regional_fallback() -> None:
    result = run(
        gate_input(risk_level=RiskLevel.HIGH, recommendation_type=RecommendationType.AVOID_TRAVEL)
    )

    assert result.emergency_instructions == FALLBACK
    assert WarningCode.DATA_INCOMPLETE in codes(result)
    assert result.applied_rules == ("R-01",)


def test_r01_agent_steps_are_kept() -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.HIGH,
            recommendation_type=RecommendationType.AVOID_TRAVEL,
            emergency_instructions=AGENT_STEPS,
        )
    )

    assert result.emergency_instructions == AGENT_STEPS
    assert result.applied_rules == ()


def test_r01_without_fallback_rejects_the_result() -> None:
    inp = gate_input(risk_level=RiskLevel.HIGH, recommendation_type=RecommendationType.AVOID_TRAVEL)

    with pytest.raises(SafetyGateRejection) as info:
        run(inp, fallback=None)

    assert info.value.rule == "R-01"
    assert info.value.agent_failed is False


def test_r01_does_not_apply_below_high_risk() -> None:
    result = run(gate_input(risk_level=RiskLevel.MEDIUM, recommendation_type=RecommendationType.CHANGE_ROUTE))

    assert result.emergency_instructions is None
    assert result.applied_rules == ()


# ------------------------------------------------------------ R-04


def test_r04_high_risk_with_travel_normally_is_rejected_for_review() -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(risk_level=RiskLevel.HIGH, emergency_instructions=AGENT_STEPS))

    assert info.value.rule == "R-04"
    assert info.value.needs_safety_review is True


def test_r04_is_checked_before_r02_can_hide_it() -> None:
    inp = gate_input(risk_level=RiskLevel.HIGH, freshness=report(weather=5, transport=1))

    with pytest.raises(SafetyGateRejection) as info:
        run(inp)

    assert info.value.rule == "R-04"


# ------------------------------------------------------------ R-05 and contract checks


def test_r05_clarification_passes_without_risk_or_action() -> None:
    result = run(
        gate_input(
            status=RecommendationStatus.NEEDS_CLARIFICATION,
            risk_level=None,
            risk_confidence=None,
            recommendation_type=None,
            summary=None,
            has_clarification=True,
            service_status={},
            freshness=report(),
        )
    )

    assert result.status is RecommendationStatus.NEEDS_CLARIFICATION
    assert result.recommendation_type is None
    assert result.warnings == ()


def test_r05_clarification_status_without_question_is_rejected() -> None:
    inp = gate_input(
        status=RecommendationStatus.NEEDS_CLARIFICATION,
        recommendation_type=None,
        has_clarification=False,
    )

    with pytest.raises(SafetyGateRejection) as info:
        run(inp)

    assert info.value.rule == "R-05"


@pytest.mark.parametrize(
    "overrides",
    [{"recommendation_type": None}, {"risk_level": None}],
)
def test_completed_result_needs_risk_and_action(overrides: dict[str, Any]) -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(**overrides))

    assert info.value.rule == "R-05"


def test_partial_result_may_come_without_an_action() -> None:
    result = run(
        gate_input(
            status=RecommendationStatus.PARTIAL_RESULT,
            recommendation_type=None,
            summary=None,
            freshness=report(weather=5, transport=1),
        )
    )

    assert result.status is RecommendationStatus.PARTIAL_RESULT
    assert result.recommendation_type is None


def test_agent_failure_is_rejected_as_unavailable() -> None:
    with pytest.raises(SafetyGateRejection) as info:
        run(gate_input(status=RecommendationStatus.FAILED))

    assert info.value.agent_failed is True


# ------------------------------------------------------------ confidence and combinations


def test_low_confidence_adds_a_warning_only() -> None:
    result = run(gate_input(risk_confidence=0.49))

    assert codes(result) == [WarningCode.LOW_CONFIDENCE]
    assert result.status is RecommendationStatus.COMPLETED


def test_confidence_at_threshold_is_fine() -> None:
    assert run(gate_input(risk_confidence=0.5)).warnings == ()


def test_all_rules_together_keep_one_warning_per_code() -> None:
    result = run(
        gate_input(
            risk_level=RiskLevel.HIGH,
            risk_confidence=0.2,
            recommendation_type=RecommendationType.AVOID_TRAVEL,
            service_status={"weather": OK, "transport": ServiceState.DEGRADED, "disaster": ServiceState.UNAVAILABLE},
            freshness=report(weather=5, transport=1),
        )
    )

    assert codes(result) == [
        WarningCode.DATA_INCOMPLETE,
        WarningCode.SERVICE_DEGRADED,
        WarningCode.LOW_CONFIDENCE,
    ]
    assert result.applied_rules == ("R-02", "R-03", "R-01")
    assert result.recommendation_type is RecommendationType.AVOID_TRAVEL
    assert result.emergency_instructions == FALLBACK
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/unit/domain/test_safety_gate.py -q`
Expected: `ImportError` (`WarningCode`, `app.domain.safety_gate`)

- [x] **Step 3: Write the implementation**

Append to `app/domain/enums.py`:

```python
class WarningCode(StrEnum):
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    DATA_STALE = "DATA_STALE"
    SERVICE_DEGRADED = "SERVICE_DEGRADED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OUTSIDE_COVERAGE = "OUTSIDE_COVERAGE"
```

Create `app/domain/errors.py`:

```python
"""Domain errors; the API layer maps them to Problem Details."""

from __future__ import annotations

from dataclasses import dataclass


class DomainError(Exception):
    """Base class for rule violations detected in the domain layer."""


@dataclass(frozen=True, slots=True)
class FieldIssue:
    field: str
    code: str
    message: str


class InvalidInput(DomainError):
    def __init__(self, issues: list[FieldIssue]) -> None:
        super().__init__(", ".join(f"{i.field}: {i.code}" for i in issues))
        self.issues = issues
```

Create `app/domain/safety_gate.py`:

```python
"""Safety Gate: rules R-01 to R-05 of docs/02_api_spec.md section 5.4.

A wrong "safe" answer can hurt someone, so when data is missing the result degrades
honestly instead of guessing. The gate either returns an adjusted result or raises
`SafetyGateRejection` when the Agent result cannot be shown at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.enums import (
    DataCategory,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    ServiceState,
    WarningCode,
)
from app.domain.errors import DomainError
from app.domain.freshness import FreshnessReport

# Services whose absence makes "travel normally" unprovable (R-02).
CRITICAL_SOURCES = {"weather": DataCategory.WEATHER, "disaster": DataCategory.DISASTER}
_AVAILABLE = frozenset({ServiceState.OK, ServiceState.DEGRADED})
_TROUBLED = frozenset({ServiceState.DEGRADED, ServiceState.UNAVAILABLE})

_MESSAGES = {
    "en": {
        WarningCode.DATA_INCOMPLETE: "Some safety data is missing.",
        WarningCode.DATA_STALE: "Some safety data is out of date.",
        WarningCode.SERVICE_DEGRADED: "Some services are degraded; details may be limited.",
        WarningCode.LOW_CONFIDENCE: "The risk estimate has low confidence.",
        "incomplete_summary": (
            "Weather or disaster data is incomplete, so we cannot confirm it is safe to "
            "travel. Check official announcements before you go."
        ),
    },
    "th": {
        WarningCode.DATA_INCOMPLETE: "ข้อมูลด้านความปลอดภัยบางส่วนขาดหายไป",
        WarningCode.DATA_STALE: "ข้อมูลด้านความปลอดภัยบางส่วนไม่เป็นปัจจุบัน",
        WarningCode.SERVICE_DEGRADED: "บางบริการทำงานไม่เต็มที่ รายละเอียดอาจไม่ครบ",
        WarningCode.LOW_CONFIDENCE: "การประเมินความเสี่ยงมีความเชื่อมั่นต่ำ",
        "incomplete_summary": (
            "ข้อมูลสภาพอากาศหรือภัยพิบัติไม่ครบถ้วน จึงยืนยันไม่ได้ว่าเดินทางได้อย่างปลอดภัย "
            "โปรดตรวจสอบประกาศจากหน่วยงานทางการก่อนเดินทาง"
        ),
    },
}


@dataclass(frozen=True, slots=True)
class GateInput:
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    summary: str | None
    has_clarification: bool
    emergency_instructions: Mapping[str, Any] | None
    service_status: Mapping[str, ServiceState]
    freshness: FreshnessReport


@dataclass(frozen=True, slots=True)
class GateWarning:
    code: WarningCode
    message: str


@dataclass(frozen=True, slots=True)
class GateResult:
    status: RecommendationStatus
    recommendation_type: RecommendationType | None
    summary: str | None
    emergency_instructions: Mapping[str, Any] | None
    warnings: tuple[GateWarning, ...]
    applied_rules: tuple[str, ...]


class SafetyGateRejection(DomainError):
    def __init__(
        self,
        rule: str,
        reason: str,
        *,
        needs_safety_review: bool = False,
        agent_failed: bool = False,
    ) -> None:
        super().__init__(f"{rule}: {reason}")
        self.rule = rule
        self.needs_safety_review = needs_safety_review
        self.agent_failed = agent_failed


class _Builder:
    def __init__(self, inp: GateInput, language: str) -> None:
        self.messages = _MESSAGES["th" if language.lower().startswith("th") else "en"]
        self.status = inp.status
        self.recommendation_type = inp.recommendation_type
        self.summary = inp.summary
        self.emergency_instructions = inp.emergency_instructions
        self.warnings: list[GateWarning] = []
        self.rules: list[str] = []

    def warn(self, code: WarningCode) -> None:
        if all(w.code is not code for w in self.warnings):
            self.warnings.append(GateWarning(code, str(self.messages[code])))

    def apply(self, rule: str) -> None:
        if rule not in self.rules:
            self.rules.append(rule)

    def downgrade(self) -> None:
        if self.status is RecommendationStatus.COMPLETED:
            self.status = RecommendationStatus.PARTIAL_RESULT

    def result(self) -> GateResult:
        return GateResult(
            status=self.status,
            recommendation_type=self.recommendation_type,
            summary=self.summary,
            emergency_instructions=self.emergency_instructions,
            warnings=tuple(self.warnings),
            applied_rules=tuple(self.rules),
        )


def _check_contract(inp: GateInput) -> None:
    if inp.status is RecommendationStatus.FAILED:
        raise SafetyGateRejection("AGENT_FAILED", "agent reported failure", agent_failed=True)
    if inp.status is RecommendationStatus.NEEDS_CLARIFICATION:
        if not inp.has_clarification:
            raise SafetyGateRejection("R-05", "clarification status without a question")
        return
    if inp.risk_level is RiskLevel.HIGH and (
        inp.recommendation_type is RecommendationType.TRAVEL_NORMALLY
    ):
        raise SafetyGateRejection(
            "R-04", "high risk combined with travel normally", needs_safety_review=True
        )
    if inp.status is RecommendationStatus.COMPLETED and (
        inp.risk_level is None or inp.recommendation_type is None
    ):
        raise SafetyGateRejection("R-05", "completed result without risk or action")


def _critical_data_problems(inp: GateInput) -> list[WarningCode]:
    problems: list[WarningCode] = []
    for service, category in CRITICAL_SOURCES.items():
        item = inp.freshness.get(category)
        if inp.service_status.get(service) not in _AVAILABLE:
            problems.append(WarningCode.DATA_INCOMPLETE)
        elif item is None or item.updated_at is None:
            problems.append(WarningCode.DATA_INCOMPLETE)
        elif item.is_stale:
            problems.append(WarningCode.DATA_STALE)
    return problems


def apply_safety_gate(
    inp: GateInput,
    *,
    language: str,
    emergency_fallback: Mapping[str, Any] | None,
    low_confidence_below: float = 0.5,
) -> GateResult:
    _check_contract(inp)
    out = _Builder(inp, language)
    if inp.status is RecommendationStatus.NEEDS_CLARIFICATION:
        return out.result()

    # R-02: without fresh weather and disaster data, "safe" cannot be claimed.
    problems = _critical_data_problems(inp)
    if problems:
        out.apply("R-02")
        out.downgrade()
        for code in problems:
            out.warn(code)
        if out.recommendation_type is RecommendationType.TRAVEL_NORMALLY:
            out.recommendation_type = None
            out.summary = str(out.messages["incomplete_summary"])

    # R-03: other degraded dependencies make the answer partial.
    if any(state in _TROUBLED for state in inp.service_status.values()):
        out.apply("R-03")
        out.downgrade()
        out.warn(WarningCode.SERVICE_DEGRADED)

    # R-01: high risk always comes with emergency instructions.
    if inp.risk_level is RiskLevel.HIGH and out.emergency_instructions is None:
        if emergency_fallback is None:
            raise SafetyGateRejection("R-01", "high risk without emergency instructions")
        out.apply("R-01")
        out.emergency_instructions = emergency_fallback
        out.warn(WarningCode.DATA_INCOMPLETE)

    if inp.risk_confidence is not None and inp.risk_confidence < low_confidence_below:
        out.warn(WarningCode.LOW_CONFIDENCE)

    return out.result()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m uv run pytest tests/unit/domain/test_safety_gate.py -q`
Expected: all pass

- [x] **Step 5: Checkpoint** — no commit.

---

### Task 4: Request normalization

**Files:**
- Modify: `pyproject.toml` (dependency `tzdata`)
- Modify: `app/domain/enums.py` (add `TravelMode`, `AvoidOption`, `MobilityNeed`)
- Create: `app/core/geo.py`
- Create: `app/domain/normalization.py`
- Test: `tests/unit/domain/test_normalization.py`

**Interfaces:**
- Consumes: `clean_text` (Task 1), `FieldIssue`, `InvalidInput` (Task 3)
- Produces:
  - `haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float`
  - `TravelMode`, `AvoidOption`, `MobilityNeed` enums
  - `GeoPoint(lat, lon, name=None, place_id=None)`
  - `TravelPreferences(travel_modes=(), avoid=(), max_travel_hours=None, mobility_needs=(), traveler_count=1)`
  - `TravelRequestInput(origin, destination, departure_time, timezone, waypoints=(), language=None, accept_language=None, preferences=TravelPreferences(), question=None)`
  - `NormalizationLimits(max_waypoints=5, max_days_ahead=14, max_question_chars=1000, min_distance_m=50.0, past_tolerance=timedelta(hours=1))`
  - `NormalizedTravelRequest(origin, destination, waypoints: tuple[GeoPoint, ...], departure_time: datetime (UTC), timezone: str, language: str, preferences: TravelPreferences, question: str | None)`
  - `negotiate_language(explicit: str | None, accept_language: str | None) -> str`
  - `normalize_travel_request(raw: TravelRequestInput, *, now: datetime, limits: NormalizationLimits) -> NormalizedTravelRequest` (raises `InvalidInput` listing every issue)

- [x] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.core.geo import haversine_m
from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import InvalidInput
from app.domain.normalization import (
    GeoPoint,
    NormalizationLimits,
    TravelPreferences,
    TravelRequestInput,
    negotiate_language,
    normalize_travel_request,
)

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
LIMITS = NormalizationLimits()
BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")


def raw(**overrides: Any) -> TravelRequestInput:
    base = TravelRequestInput(
        origin=BANGKOK,
        destination=CHIANG_MAI,
        departure_time=datetime(2026, 9, 20, 1, 0, tzinfo=UTC),
        timezone="Asia/Bangkok",
    )
    return replace(base, **overrides)


def issues(inp: TravelRequestInput) -> dict[str, str]:
    with pytest.raises(InvalidInput) as info:
        normalize_travel_request(inp, now=NOW, limits=LIMITS)
    return {i.field: i.code for i in info.value.issues}


def test_haversine_bangkok_to_chiang_mai() -> None:
    assert haversine_m(13.7563, 100.5018, 18.7883, 98.9853) == pytest.approx(583_000, rel=0.01)
    assert haversine_m(1.0, 1.0, 1.0, 1.0) == 0.0


def test_valid_request_is_normalized() -> None:
    bangkok_time = datetime(2026, 9, 20, 8, 0, tzinfo=timezone(timedelta(hours=7)))

    result = normalize_travel_request(
        raw(
            origin=GeoPoint(13.75630049, 100.50180051, name="  Bangkok\x00 "),
            departure_time=bangkok_time,
            language="TH-th",
            question="  ปลอดภัยไหม​ ",
        ),
        now=NOW,
        limits=LIMITS,
    )

    assert result.origin == GeoPoint(13.7563, 100.5018, name="Bangkok")
    assert result.departure_time == datetime(2026, 9, 20, 1, 0, tzinfo=UTC)
    assert result.departure_time.tzinfo is UTC
    assert result.timezone == "Asia/Bangkok"
    assert result.language == "th"
    assert result.question == "ปลอดภัยไหม"


def test_blank_question_becomes_none() -> None:
    result = normalize_travel_request(raw(question="   "), now=NOW, limits=LIMITS)

    assert result.question is None


@pytest.mark.parametrize(
    ("point", "field"),
    [
        (GeoPoint(90.0001, 100.0), "origin.lat"),
        (GeoPoint(-91.0, 100.0), "origin.lat"),
        (GeoPoint(13.0, 180.5), "origin.lon"),
        (GeoPoint(float("nan"), 100.0), "origin.lat"),
    ],
)
def test_out_of_range_coordinates(point: GeoPoint, field: str) -> None:
    assert issues(raw(origin=point)) == {field: "out_of_range"}


def test_origin_and_destination_must_differ() -> None:
    near_bangkok = GeoPoint(13.7564, 100.5018)  # about 11 m away

    assert issues(raw(destination=near_bangkok)) == {"destination": "same_as_origin"}


def test_naive_departure_time_is_rejected() -> None:
    assert issues(raw(departure_time=datetime(2026, 9, 20, 1, 0))) == {
        "departure_time": "timezone_required"
    }


@pytest.mark.parametrize(
    ("when", "code"),
    [
        (NOW - timedelta(hours=1, minutes=1), "in_past"),
        (NOW + timedelta(days=14, minutes=1), "too_far_ahead"),
    ],
)
def test_departure_time_window(when: datetime, code: str) -> None:
    assert issues(raw(departure_time=when)) == {"departure_time": code}


@pytest.mark.parametrize("when", [NOW - timedelta(minutes=59), NOW + timedelta(days=14)])
def test_departure_time_window_edges_are_accepted(when: datetime) -> None:
    assert normalize_travel_request(raw(departure_time=when), now=NOW, limits=LIMITS)


@pytest.mark.parametrize("name", ["Mars/Olympus", "../etc/passwd", "", "Asia/Bangkok "])
def test_unknown_timezone(name: str) -> None:
    assert issues(raw(timezone=name)) == {"timezone": "unknown_timezone"}


def test_question_length_limit() -> None:
    assert normalize_travel_request(raw(question="ก" * 1000), now=NOW, limits=LIMITS)
    assert issues(raw(question="ก" * 1001)) == {"question": "too_long"}


def test_too_many_waypoints() -> None:
    points = tuple(GeoPoint(14.0 + i, 100.0) for i in range(6))

    assert issues(raw(waypoints=points)) == {"waypoints": "too_many"}


def test_consecutive_duplicate_waypoints_are_merged() -> None:
    a = GeoPoint(15.0, 100.0)
    a_again = GeoPoint(15.00001, 100.0)
    b = GeoPoint(16.0, 100.0)

    result = normalize_travel_request(raw(waypoints=(a, a_again, b, a)), now=NOW, limits=LIMITS)

    assert result.waypoints == (a, b, a)


def test_invalid_waypoint_is_reported_with_its_index() -> None:
    points = (GeoPoint(15.0, 100.0), GeoPoint(15.0, 200.0))

    assert issues(raw(waypoints=points)) == {"waypoints.1.lon": "out_of_range"}


def test_preferences_are_deduplicated_and_sorted() -> None:
    prefs = TravelPreferences(
        travel_modes=(TravelMode.TRAIN, TravelMode.BUS, TravelMode.TRAIN),
        avoid=(AvoidOption.TOLLS, AvoidOption.FERRIES),
        mobility_needs=(MobilityNeed.WHEELCHAIR, MobilityNeed.WHEELCHAIR),
        max_travel_hours=12,
        traveler_count=2,
    )

    result = normalize_travel_request(raw(preferences=prefs), now=NOW, limits=LIMITS)

    assert result.preferences == TravelPreferences(
        travel_modes=(TravelMode.BUS, TravelMode.TRAIN),
        avoid=(AvoidOption.FERRIES, AvoidOption.TOLLS),
        mobility_needs=(MobilityNeed.WHEELCHAIR,),
        max_travel_hours=12,
        traveler_count=2,
    )


@pytest.mark.parametrize(
    ("prefs", "field"),
    [
        (TravelPreferences(max_travel_hours=0), "preferences.max_travel_hours"),
        (TravelPreferences(max_travel_hours=49), "preferences.max_travel_hours"),
        (TravelPreferences(traveler_count=0), "preferences.traveler_count"),
        (TravelPreferences(traveler_count=21), "preferences.traveler_count"),
    ],
)
def test_preference_ranges(prefs: TravelPreferences, field: str) -> None:
    assert issues(raw(preferences=prefs)) == {field: "out_of_range"}


def test_all_issues_are_reported_together() -> None:
    found = issues(
        raw(
            origin=GeoPoint(100.0, 0.0),
            timezone="Nowhere/City",
            question="x" * 1001,
            departure_time=datetime(2026, 9, 20),
        )
    )

    assert found == {
        "origin.lat": "out_of_range",
        "timezone": "unknown_timezone",
        "question": "too_long",
        "departure_time": "timezone_required",
    }


@pytest.mark.parametrize(
    ("explicit", "header", "expected"),
    [
        ("en", "th", "en"),
        ("EN-us", None, "en"),
        ("ja", "en-US,en;q=0.9", "en"),
        (None, "ja,en-US;q=0.8,th;q=0.9", "th"),
        (None, "en;q=0, th;q=0.1", "th"),
        (None, "fr, de", "th"),
        (None, "en;q=abc, th;q=0.2", "th"),
        (None, None, "th"),
        ("", "", "th"),
    ],
)
def test_negotiate_language(explicit: str | None, header: str | None, expected: str) -> None:
    assert negotiate_language(explicit, header) == expected


def test_language_falls_back_to_accept_language() -> None:
    result = normalize_travel_request(
        raw(language=None, accept_language="en-GB,en;q=0.8"), now=NOW, limits=LIMITS
    )

    assert result.language == "en"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m uv run pytest tests/unit/domain/test_normalization.py -q`
Expected: `ImportError` (`app.core.geo`, enums, `app.domain.normalization`)

- [x] **Step 3: Write the implementation**

`python -m uv add "tzdata>=2024.1"` (no IANA database on Windows or python:slim).

Append to `app/domain/enums.py`:

```python
class TravelMode(StrEnum):
    CAR = "CAR"
    TRAIN = "TRAIN"
    BUS = "BUS"
    FLIGHT = "FLIGHT"
    FERRY = "FERRY"
    WALK = "WALK"
    BICYCLE = "BICYCLE"


class AvoidOption(StrEnum):
    TOLLS = "TOLLS"
    HIGHWAYS = "HIGHWAYS"
    FERRIES = "FERRIES"
    NIGHT_TRAVEL = "NIGHT_TRAVEL"


class MobilityNeed(StrEnum):
    WHEELCHAIR = "WHEELCHAIR"
    ELDERLY = "ELDERLY"
    CHILDREN = "CHILDREN"
    PETS = "PETS"
```

Create `app/core/geo.py`:

```python
"""Geographic helpers (WGS84)."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
```

Create `app/domain/normalization.py`:

```python
"""Normalize a travel request before it reaches the Agent (docs/02_api_spec.md 5.1).

The API schema checks types; this module applies the rules that need context (time
window, distinct locations, timezone database) and produces a canonical form: UTC
time, 6-decimal coordinates, supported language, sorted unique preferences and a
cleaned question. Every problem is reported at once.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.geo import haversine_m
from app.domain.enums import AvoidOption, MobilityNeed, TravelMode
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.sanitizer import clean_text

SUPPORTED_LANGUAGES = ("th", "en")
DEFAULT_LANGUAGE = "th"
COORDINATE_DECIMALS = 6
MAX_TRAVEL_HOURS = (1, 48)
TRAVELER_COUNT = (1, 20)
NAME_MAX_LENGTH = 200


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lon: float
    name: str | None = None
    place_id: str | None = None


@dataclass(frozen=True, slots=True)
class TravelPreferences:
    travel_modes: tuple[TravelMode, ...] = ()
    avoid: tuple[AvoidOption, ...] = ()
    max_travel_hours: int | None = None
    mobility_needs: tuple[MobilityNeed, ...] = ()
    traveler_count: int = 1


@dataclass(frozen=True, slots=True)
class TravelRequestInput:
    origin: GeoPoint
    destination: GeoPoint
    departure_time: datetime
    timezone: str
    waypoints: Sequence[GeoPoint] = ()
    language: str | None = None
    accept_language: str | None = None
    preferences: TravelPreferences = field(default_factory=TravelPreferences)
    question: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationLimits:
    max_waypoints: int = 5  # P-42
    max_days_ahead: int = 14  # P-43
    max_question_chars: int = 1000  # P-41
    min_distance_m: float = 50.0
    past_tolerance: timedelta = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class NormalizedTravelRequest:
    origin: GeoPoint
    destination: GeoPoint
    waypoints: tuple[GeoPoint, ...]
    departure_time: datetime
    timezone: str
    language: str
    preferences: TravelPreferences
    question: str | None


def _primary_language(tag: str | None) -> str | None:
    if not tag:
        return None
    primary = tag.strip().split("-")[0].split("_")[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else None


def _accept_language_candidates(header: str) -> list[str]:
    weighted: list[tuple[float, int, str]] = []
    for position, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        if tag and quality > 0:
            weighted.append((-quality, position, tag))
    return [tag for _, _, tag in sorted(weighted)]


def negotiate_language(explicit: str | None, accept_language: str | None) -> str:
    chosen = _primary_language(explicit)
    if chosen:
        return chosen
    for tag in _accept_language_candidates(accept_language or ""):
        chosen = _primary_language(tag)
        if chosen:
            return chosen
    return DEFAULT_LANGUAGE


def _point(point: GeoPoint, prefix: str, issues: list[FieldIssue]) -> GeoPoint:
    valid = True
    for name, value, bound in (("lat", point.lat, 90.0), ("lon", point.lon, 180.0)):
        if not math.isfinite(value) or abs(value) > bound:
            issues.append(FieldIssue(f"{prefix}.{name}", "out_of_range", f"must be within ±{bound:g}"))
            valid = False
    if not valid:
        return point
    name = clean_text(point.name)
    return GeoPoint(
        lat=round(point.lat, COORDINATE_DECIMALS),
        lon=round(point.lon, COORDINATE_DECIMALS),
        name=name[:NAME_MAX_LENGTH] if name else None,
        place_id=clean_text(point.place_id),
    )


def _distance(a: GeoPoint, b: GeoPoint) -> float:
    return haversine_m(a.lat, a.lon, b.lat, b.lon)


def _departure(
    value: datetime, now: datetime, limits: NormalizationLimits, issues: list[FieldIssue]
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        issues.append(FieldIssue("departure_time", "timezone_required", "include a UTC offset"))
        return value
    utc = value.astimezone(UTC)
    if utc < now - limits.past_tolerance:
        issues.append(FieldIssue("departure_time", "in_past", "departure time has passed"))
    elif utc > now + timedelta(days=limits.max_days_ahead):
        issues.append(
            FieldIssue(
                "departure_time",
                "too_far_ahead",
                f"at most {limits.max_days_ahead} days ahead",
            )
        )
    return utc


def _timezone(name: str, issues: list[FieldIssue]) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        issues.append(FieldIssue("timezone", "unknown_timezone", "use an IANA timezone name"))
    return name


def _preferences(prefs: TravelPreferences, issues: list[FieldIssue]) -> TravelPreferences:
    low, high = MAX_TRAVEL_HOURS
    if prefs.max_travel_hours is not None and not low <= prefs.max_travel_hours <= high:
        issues.append(
            FieldIssue("preferences.max_travel_hours", "out_of_range", f"must be {low}-{high}")
        )
    low, high = TRAVELER_COUNT
    if not low <= prefs.traveler_count <= high:
        issues.append(
            FieldIssue("preferences.traveler_count", "out_of_range", f"must be {low}-{high}")
        )
    return TravelPreferences(
        travel_modes=tuple(sorted(set(prefs.travel_modes))),
        avoid=tuple(sorted(set(prefs.avoid))),
        max_travel_hours=prefs.max_travel_hours,
        mobility_needs=tuple(sorted(set(prefs.mobility_needs))),
        traveler_count=prefs.traveler_count,
    )


def _waypoints(
    points: Sequence[GeoPoint], limits: NormalizationLimits, issues: list[FieldIssue]
) -> tuple[GeoPoint, ...]:
    if len(points) > limits.max_waypoints:
        issues.append(
            FieldIssue("waypoints", "too_many", f"at most {limits.max_waypoints} waypoints")
        )
        return tuple(points)
    cleaned: list[GeoPoint] = []
    for index, point in enumerate(points):
        before = len(issues)
        normalized = _point(point, f"waypoints.{index}", issues)
        if len(issues) > before:
            continue
        if cleaned and _distance(cleaned[-1], normalized) < limits.min_distance_m:
            continue
        cleaned.append(normalized)
    return tuple(cleaned)


def normalize_travel_request(
    raw: TravelRequestInput, *, now: datetime, limits: NormalizationLimits
) -> NormalizedTravelRequest:
    issues: list[FieldIssue] = []
    before = len(issues)
    origin = _point(raw.origin, "origin", issues)
    destination = _point(raw.destination, "destination", issues)
    if len(issues) == before and _distance(origin, destination) < limits.min_distance_m:
        issues.append(
            FieldIssue("destination", "same_as_origin", "destination must differ from origin")
        )
    waypoints = _waypoints(raw.waypoints, limits, issues)
    departure = _departure(raw.departure_time, now, limits, issues)
    timezone_name = _timezone(raw.timezone, issues)
    preferences = _preferences(raw.preferences, issues)
    question = clean_text(raw.question)
    if question is not None and len(question) > limits.max_question_chars:
        issues.append(
            FieldIssue(
                "question", "too_long", f"at most {limits.max_question_chars} characters"
            )
        )
    if issues:
        raise InvalidInput(issues)
    return NormalizedTravelRequest(
        origin=origin,
        destination=destination,
        waypoints=waypoints,
        departure_time=departure,
        timezone=timezone_name,
        language=negotiate_language(raw.language, raw.accept_language),
        preferences=preferences,
        question=question,
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m uv run pytest tests/unit/domain/test_normalization.py -q`
Expected: all pass

- [x] **Step 5: Checkpoint** — no commit.

---

### Task 5: Guard the layer rule, settings, docs, full verification

**Files:**
- Create: `tests/unit/domain/test_layering.py`
- Modify: `app/core/config.py` (P-51 `LOW_CONFIDENCE_THRESHOLD`, P-52 `MIN_ROUTE_DISTANCE_METERS`)
- Modify: `docs/02_api_spec.md` (§2 P-51/P-52, §5.4 clarifications), `docs/04_project_structure.md` (D-34, D-35), `README.md` (status)

**Interfaces:**
- Produces: `LimitSettings.min_route_distance_meters: float = 50`, `SafetySettings.low_confidence_threshold: float = 0.5` exposed as `Settings.safety`

- [x] **Step 1: Write the failing tests**

```python
"""The domain layer stays framework-free (docs/04_project_structure.md section 2)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[3] / "app" / "domain"
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "geoalchemy2", "redis", "httpx",
             "pydantic", "app.api", "app.schemas", "app.infrastructure", "app.services")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", sorted(DOMAIN.glob("*.py")), ids=lambda p: p.name)
def test_domain_module_has_no_framework_imports(path: Path) -> None:
    bad = {name for name in _imports(path) if name.startswith(FORBIDDEN)}

    assert bad == set()
```

Add to `tests/unit/test_config.py`:

```python
def test_safety_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().safety.low_confidence_threshold == 0.5  # P-51
    assert Settings().limits.min_route_distance_meters == 50  # P-52

    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings()
```

- [x] **Step 2: Run tests to verify the config test fails** (the layering test documents an existing rule and should pass immediately; to prove it can fail, temporarily add `import httpx` to `app/domain/errors.py`, watch it fail, then remove the line)

Run: `python -m uv run pytest tests/unit/domain/test_layering.py tests/unit/test_config.py -q`
Expected: config test fails with `AttributeError: 'Settings' object has no attribute 'safety'`

- [x] **Step 3: Implement**

In `app/core/config.py` add to `LimitSettings`:

```python
    min_route_distance_meters: float = Field(default=50.0, ge=0)  # P-52
```

Add a new group before `Settings`:

```python
class SafetySettings(BaseSettings):
    model_config = _ENV_CONFIG

    low_confidence_threshold: float = Field(default=0.5, ge=0, le=1)  # P-51
```

and in `Settings`:

```python
    safety: SafetySettings = Field(default_factory=SafetySettings)
```

Docs:
- `docs/02_api_spec.md` §2 add rows `P-51 | ความเชื่อมั่นต่ำกว่านี้ → warning LOW_CONFIDENCE | 0.5 | LOW_CONFIDENCE_THRESHOLD` and `P-52 | ระยะขั้นต่ำระหว่างต้นทาง/ปลายทาง/waypoint | 50 m | MIN_ROUTE_DISTANCE_METERS`; §5.4 add the rule decisions listed in Task 3; change log 0.6.
- `docs/04_project_structure.md` add D-34 (R-02 keeps cautious actions, `not_used` counts as missing) and D-35 (Agent `failed` → 503 via `agent_failed`); change log 0.6.
- `README.md` status row 5.5 done.

- [x] **Step 4: Full verification**

Run:
```
python -m uv run ruff format --check .
python -m uv run ruff check .
python -m uv run mypy app tests migrations scripts mock_agent
python -m uv run pytest -q --cov
```
Expected: all clean, all tests pass.

- [x] **Step 5: Checkpoint** — report to the user; they commit.

---

## Self-Review

- Spec coverage: R-01 (Task 3), R-02 (Task 3), R-03 (Task 3), R-04 (Task 3), R-05 (Task 3), R-06 (Task 1), R-07 (Task 2), §5.1 validation (Task 4), P-28/P-41/P-42/P-43 (Tasks 2, 4), layer rule (Task 5). Wiring into services is step 5.6.
- Placeholders: none.
- Types: `FreshnessReport.get/is_fresh` used by Task 3 match Task 2; `FieldIssue`/`InvalidInput` defined in Task 3 and used in Task 4; `clean_text` signature from Task 1 used in Task 4.

## Execution Notes (2026-09-17)

All five tasks were executed in order with RED → GREEN for each. Differences from the code above:

- Task 3: the Safety Gate tests were first run against a pass-through stub (24 of 32 failed, the other 8 expect "no change"), then against the real gate. A mutation run of 13 planted bugs was fully caught.
- Task 3: `_critical_data_problems` merges the two `DATA_INCOMPLETE` branches (ruff SIM114).
- Task 4: `_timezone` checks `zoneinfo.available_timezones()` instead of `ZoneInfo(name)`. Root cause: on Windows the file lookup accepts `"Asia/Bangkok "` and `"Asia/Bangkok."` because the file system ignores trailing spaces and dots; Linux rejects them. Test cases were added for both, and for `"asia/bangkok"` (D-36).
- Task 4: the rounding fixture used `100.50180051`, which correctly rounds to `100.501801`; it was changed to `100.50180049`. A loop variable was renamed (`name` → `label`) for mypy.
- Task 4: a mutation run showed that `q=0` in `Accept-Language` was not really tested; `("fr, en;q=0") -> "th"` was added.
- Task 2: a mutation run showed the 15-minute disaster limit was not tested; `test_disaster_data_ages_out_faster_than_weather` was added. `test_freshness.py` uses an `item_of()` helper so mypy accepts the optional lookups.

### Code review fixes

- Critical: `safe_url("https://[::1")` raised `ValueError` (one bad link from the Agent would fail the whole response). Parsing errors now return `None`; hosts with whitespace and invalid ports are rejected too.
- Important: `place_id` longer than 200 characters passed normalization and would fail later when the Agent request is built. It is now reported as `<field>.place_id: too_long` (names are still shortened to 200).
- Minor: `test_layering.py` now also allow-lists the `app.*` modules the domain may import (`app.domain`, `app.core.geo`, `app.core.clock`).
- Minor, open: `Accept-Language` parsing has no cap on the number of entries (the server's header size limit bounds it); revisit if profiling shows a cost.

Final verification: ruff format/check clean, mypy clean, all tests passed (see the step report), Docker stack healthy, Linux container rejects the same timezone names as Windows.
