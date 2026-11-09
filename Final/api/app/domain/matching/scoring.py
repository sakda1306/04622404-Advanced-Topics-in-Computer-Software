"""Match % in plain Python (Design.md §4.3, PRD FR-18a – FR-20).

Works on the saved profile, so a role's score never needs the LLM. `reason_th` and `next_steps`
stay empty for the explain step (FR-20a).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from app.domain.matching.roles import RoleProfile
from app.domain.matching.skills import SkillTaxonomy

WEIGHT_REQUIRED = 0.70
WEIGHT_NICE = 0.15
WEIGHT_SOFT = 0.10
WEIGHT_WORK_STYLE = 0.05
NEUTRAL_WORK_STYLE = 0.5  # the user gave no preference, so it neither helps nor hurts
CLOSEST_ROLES = 3  # shown when none pass (FR-19a)
_GAP_ORDER = {"missing_skill": 0, "below_level": 1, "soft_skill": 2}


def _name(skill_id: str, taxonomy: SkillTaxonomy) -> str:
    known = taxonomy.get(skill_id)
    return known.name_th if known else skill_id


def _percent(share: float) -> int:
    # Half rounds up, as in the web mock; the inner round() removes float noise such as 72.4999.
    return math.floor(round(100 * share, 6) + 0.5)


def _work_style_share(role: RoleProfile, preferences: dict[str, float]) -> float:
    given = [trait for trait in role.work_style if trait in preferences]
    if not given:
        return NEUTRAL_WORK_STYLE
    distance = sum(abs(preferences[t] - role.work_style[t]) for t in given) / len(given)
    return 1 - distance


def _matched_item(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill_id": skill["skill_id"],
        "name_th": skill["name_th"],
        "evidence_ids": skill["evidence_ids"],
    }


def score_role(
    role: RoleProfile, profile: dict[str, Any], taxonomy: SkillTaxonomy
) -> dict[str, Any]:
    """The Contract `RoleMatch` for one role."""
    hard = {skill["skill_id"]: skill for skill in profile["hard_skills"]}
    soft = {skill["skill_id"] for skill in profile["soft_skills"]}
    matched: list[dict[str, Any]] = []
    gaps: list[tuple[int, int, dict[str, Any]]] = []  # (kind order, -weight, gap)

    earned = 0.0
    for index, need in enumerate(role.required):
        have = [hard[skill_id] for skill_id in need.skills if skill_id in hard]
        gap_id = f"{role.role_id}-req-{index}"
        if not have:
            names = " / ".join(_name(skill_id, taxonomy) for skill_id in need.skills)
            gap = {
                "gap_id": gap_id,
                "kind": "missing_skill",
                "skill_id": need.skills[0],
                "name_th": names,
                "required_level": need.min_level,
            }
            gaps.append((_GAP_ORDER["missing_skill"], -need.weight, gap))
            continue
        best = max(have, key=lambda skill: skill["level"])
        matched.append(_matched_item(best))
        earned += need.weight * min(best["level"] / need.min_level, 1)
        if best["level"] < need.min_level:
            gap = {
                "gap_id": gap_id,
                "kind": "below_level",
                "skill_id": best["skill_id"],
                "name_th": best["name_th"],
                "required_level": need.min_level,
                "user_level": best["level"],
            }
            gaps.append((_GAP_ORDER["below_level"], -need.weight, gap))

    nice = [hard[skill_id] for skill_id in role.nice_to_have if skill_id in hard]
    matched.extend(_matched_item(skill) for skill in nice)
    soft_have = 0
    for skill_id in role.soft_skills:
        if skill_id in soft:
            soft_have += 1
        else:
            gap = {
                "gap_id": f"{role.role_id}-soft-{skill_id}",
                "kind": "soft_skill",
                "skill_id": skill_id,
                "name_th": _name(skill_id, taxonomy),
            }
            gaps.append((_GAP_ORDER["soft_skill"], 0, gap))

    hard_required = earned / sum(need.weight for need in role.required)
    hard_nice = len(nice) / len(role.nice_to_have) if role.nice_to_have else 0.0
    soft_share = soft_have / len(role.soft_skills) if role.soft_skills else 0.0
    work_style = _work_style_share(role, profile["preferences"].get("work_style", {}))
    share = (
        WEIGHT_REQUIRED * hard_required
        + WEIGHT_NICE * hard_nice
        + WEIGHT_SOFT * soft_share
        + WEIGHT_WORK_STYLE * work_style
    )
    gaps.sort(key=lambda item: item[:2])
    return {
        "role_id": role.role_id,
        "title_th": role.title_th,
        "match_pct": _percent(share),
        "breakdown": {
            "hard_required": round(hard_required, 4),
            "hard_nice": round(hard_nice, 4),
            "soft": round(soft_share, 4),
            "work_style": round(work_style, 4),
        },
        "matched": matched,
        "gaps": [gap for *_, gap in gaps],
        "reason_th": None,
        "next_steps": [],
        "explanations_stale": False,  # True makes the web wait for an explain step
    }


def match_list(
    catalogue: Sequence[RoleProfile],
    profile: dict[str, Any],
    *,
    taxonomy: SkillTaxonomy,
    threshold: int,
    top_n: int,
) -> dict[str, Any]:
    """The Contract `MatchList`: the best at or above the threshold, else the closest (FR-19a)."""
    scored = [score_role(role, profile, taxonomy) for role in catalogue]
    # sorted() is stable: equal scores keep the catalogue order, so the list never reshuffles.
    scored = sorted(scored, key=lambda s: (-s["match_pct"], -s["breakdown"]["hard_required"]))
    passing = [s for s in scored if s["match_pct"] >= threshold]
    return {
        "profile_version": profile["profile_version"],
        "threshold": threshold,
        "below_threshold": not passing,
        "roles": passing[:top_n] if passing else scored[:CLOSEST_ROLES],
    }
