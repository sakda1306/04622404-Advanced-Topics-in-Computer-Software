"""Small sums and warning rules for the admin dashboard (PRD FR-43, FR-44). Pure Python."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

LLM_LATENCY_TARGET_MS = 15_000


def share(part: int, whole: int) -> float:
    """A rate from 0 to 1. With nothing to count, the rate is 0."""
    return round(part / whole, 3) if whole else 0.0


def percentile(sorted_values: Sequence[int], percent: int) -> int:
    """Nearest rank: a value that really happened. With nothing to count, 0."""
    if not sorted_values:
        return 0
    return sorted_values[math.ceil(len(sorted_values) * percent / 100) - 1]


def _warning(panel: str, code: str, message_th: str) -> dict[str, str]:
    return {"panel": panel, "code": code, "message_th": message_th}


def warnings(
    *,
    health: dict[str, Any],
    llm_models: Sequence[dict[str, Any]],
    cache: dict[str, Any],
    llm_pct: int,
    error_pct: int,
    max_age_days: int,
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for model in llm_models:
        used = max(
            model["tokens_used"] / model["tokens_limit"],
            model["requests_used"] / model["requests_limit"],
        )
        if used * 100 > llm_pct:
            found.append(
                _warning(
                    "llm",
                    "LLM_NEAR_LIMIT",
                    f"โมเดล {model['model']} ใช้โควตาวันนี้ไปแล้ว {round(used * 100)}% (เกิน {llm_pct}%)",
                )
            )
    rate = health["error_rate"] * 100
    if rate > error_pct:
        found.append(
            _warning("health", "ERROR_RATE_HIGH", f"อัตราข้อผิดพลาด {rate:.1f}% (เกิน {error_pct}%)")
        )
    roles = cache["roles"]
    old = [r for r in roles if r["age_days"] is not None and r["age_days"] >= max_age_days]
    if old:
        found.append(
            _warning(
                "cache",
                "CACHE_STALE",
                f"ข้อมูลตลาดงาน {len(old)} สายงานเก่าถึง {max_age_days} วันแล้ว",
            )
        )
    for role in roles:
        if role["last_error"]:
            found.append(
                _warning(
                    "cache",
                    "CACHE_ERROR",
                    f"ดึงข้อมูล {role['title_th']} ไม่สำเร็จ ({role['last_error']}) ระบบยังใช้ข้อมูลเดิม",
                )
            )
    runs, budget = cache["apify_runs_this_week"], cache["apify_runs_budget"]
    if runs > budget:
        found.append(
            _warning(
                "cache", "APIFY_OVER_BUDGET", f"ใช้ Apify {runs} ครั้งในสัปดาห์นี้ เกินงบ {budget} ครั้ง"
            )
        )
    return found
