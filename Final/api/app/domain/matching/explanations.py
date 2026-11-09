"""Match reasons and next steps (Design.md §4.3, PRD FR-19, FR-20a).

Scoring decides the gaps and their order; the LLM only words them. Every shown gap gets a step:
an action that does not hold up is replaced by a computed one, so a step can never lose its gap.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.matching.roles import RoleProfile
from app.domain.matching.skills import SkillTaxonomy
from app.domain.profile import parse_claims

MAX_STEPS = 5  # Contract.md `NextStep.priority` runs from 1 to 5
_MAX_NAMES_IN_REASON = 3
_MAX_PATH_CHARS = 800  # bounds the tokens of one call
_MAX_NOTE_CHARS = 400
_STEP_NUMBER = re.compile(r"^\d+\.\s*", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Explanation:
    reason_th: str
    next_steps: list[dict[str, Any]]


def basis(match: Mapping[str, Any]) -> str:
    """Changes when the skills behind a role's wording change, so old wording can be spotted."""
    gaps = [
        [gap["gap_id"], gap["skill_id"], gap.get("required_level"), gap.get("user_level")]
        for gap in match["gaps"]
    ]
    matched = sorted(skill["skill_id"] for skill in match["matched"])
    text = json.dumps([gaps, matched], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _shown_gaps(match: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return match["gaps"][:MAX_STEPS]


def _computed_action(gap: Mapping[str, Any]) -> str:
    name = gap["name_th"]
    if gap["kind"] == "missing_skill":
        return f"เรียนรู้ {name} ให้ถึงระดับ {gap['required_level']} แล้วเพิ่มผลงานที่ใช้ทักษะนี้ลงใน CV"
    if gap["kind"] == "below_level":
        return f"ฝึก {name} จากระดับ {gap['user_level']} ให้ถึงระดับ {gap['required_level']}"
    return f"ฝึก{name} แล้วเพิ่มตัวอย่างการใช้จริงลงใน CV"


def _computed_reason(match: Mapping[str, Any]) -> str:
    names = [skill["name_th"] for skill in match["matched"][:_MAX_NAMES_IN_REASON]]
    if not names:
        return f"ยังไม่พบทักษะที่ตรงกับ {match['title_th']} ในโปรไฟล์ของคุณ"
    return f"คุณมี {', '.join(names)} ซึ่งตรงกับทักษะของ {match['title_th']}"


def _steps(match: Mapping[str, Any], actions: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "gap_id": gap["gap_id"],
            "action_th": actions.get(gap["gap_id"]) or _computed_action(gap),
            "priority": priority,
        }
        for priority, gap in enumerate(_shown_gaps(match), start=1)
    ]


def computed(match: Mapping[str, Any]) -> Explanation:
    """The wording with no LLM call."""
    return Explanation(_computed_reason(match), _steps(match, {}))


def _matched_facts(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": skill["name_th"], "evidence_ids": skill["evidence_ids"]}
        for skill in match["matched"]
    ]


def _gap_facts(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = ("gap_id", "name_th", "kind", "required_level", "user_level")
    return [{key: gap[key] for key in keys if key in gap} for gap in _shown_gaps(match)]


def role_facts(
    match: Mapping[str, Any],
    role: RoleProfile,
    *,
    learning_path: str | None = None,
    soft_skill_notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Skill names, levels and evidence ids only: no CV text reaches the LLM (FR-12).

    `learning_path` and the notes come from retrieval; with no index, the path comes from the
    role file.
    """
    path = learning_path or role.learning_path_th
    facts: dict[str, Any] = {
        "role_id": match["role_id"],
        "title": match["title_th"],
        "matched": _matched_facts(match),
        "gaps": _gap_facts(match),
        # No step numbers: the user does not see this list, so "step 4" would mean nothing to them.
        "learning_path": _STEP_NUMBER.sub("", path)[:_MAX_PATH_CHARS],
    }
    if soft_skill_notes:
        facts["soft_skill_notes"] = [note[:_MAX_NOTE_CHARS] for note in soft_skill_notes]
    return facts


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _reason(item: Mapping[str, Any], match: Mapping[str, Any], taxonomy: SkillTaxonomy) -> str:
    """Checked against the matched skills alone, so a reason cannot claim a missing skill."""
    matched = _matched_facts(match)
    claims = parse_claims(
        [item.get("reason")],
        evidence={i for skill in matched for i in skill["evidence_ids"]},
        facts_text=json.dumps(matched, ensure_ascii=False),
        taxonomy=taxonomy,
        own_skills={skill["skill_id"] for skill in match["matched"]},
    )
    return claims[0]["text_th"] if claims else _computed_reason(match)


def _actions(
    item: Mapping[str, Any], facts: Mapping[str, Any], taxonomy: SkillTaxonomy
) -> dict[str, str]:
    """An action needs a gap of this role, and may use only the skills and numbers in its facts."""
    gap_ids = {gap["gap_id"] for gap in facts["gaps"]}
    facts_text = json.dumps(facts, ensure_ascii=False)
    actions: dict[str, str] = {}
    for step in _as_list(item.get("next_steps")):
        if not isinstance(step, dict):
            continue
        claims = parse_claims(
            [{"text_th": step.get("action_th"), "evidence_ids": [step.get("gap_id")]}],
            evidence=gap_ids,
            facts_text=facts_text,
            taxonomy=taxonomy,
            own_skills=set(),
        )
        if claims:
            actions.setdefault(claims[0]["evidence_ids"][0], claims[0]["text_th"])
    return actions


def parse_explanations(
    data: Mapping[str, Any] | None,
    matches: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Mapping[str, Any]],
    taxonomy: SkillTaxonomy,
) -> dict[str, Explanation]:
    """One explanation per match. What the LLM left out or got wrong is computed instead."""
    items = {
        item["role_id"]: item
        for item in _as_list((data or {}).get("roles"))
        if isinstance(item, dict) and isinstance(item.get("role_id"), str)
    }
    out: dict[str, Explanation] = {}
    for match in matches:
        role_id = match["role_id"]
        item = items.get(role_id, {})
        actions = _actions(item, facts[role_id], taxonomy)
        out[role_id] = Explanation(_reason(item, match, taxonomy), _steps(match, actions))
    return out
