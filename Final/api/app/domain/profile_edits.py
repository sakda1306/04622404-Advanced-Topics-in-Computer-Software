"""Profile edits: check what was asked, then apply it (Design.md §4.5, PRD FR-27 – FR-34).

Pure Python. The LLM only suggests changes: `propose_changes` keeps those on the allow-list and
fills the old value from the saved profile, and nothing is applied until the user confirms.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.chat_answers import find_roles
from app.domain.matching.roles import RoleProfile
from app.domain.matching.skills import SkillTaxonomy
from app.domain.profile import UNRATED_LEVELS, relabel_trait, trait_label
from app.domain.questionnaire import Questionnaire

MIN_LEVEL, MAX_LEVEL = 1, 4
MAX_YEARS = 50
MIN_SALARY, MAX_SALARY = 1_000, 1_000_000
MAX_LOCATIONS = 10
MAX_LOCATION_CHARS = 100
MAX_CHANGES = 10
_MAX_NAME_CHARS = 100
ROLES = "preferences.interested_roles"
SALARY = "preferences.desired_salary_thb"
LOCATIONS = "preferences.locations"
WORK_STYLE = "preferences.work_style."
SKILLS = "skills"
EDITED_PREFERENCES = "edited_preferences"  # kept out of the Contract `Profile`, see profile_service


def all_skills(sections: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [*sections["hard_skills"], *sections["soft_skills"]]


def _skill(sections: Mapping[str, Any], skill_id: str | None) -> dict[str, Any] | None:
    return next((s for s in all_skills(sections) if s["skill_id"] == skill_id), None)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def trait_names(questionnaire: Questionnaire) -> set[str]:
    return {q["trait"] for q in questionnaire.questions() if "trait" in q}


def valid_salary(value: Any) -> bool:
    return _is_int(value) and MIN_SALARY <= value <= MAX_SALARY


def valid_locations(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= MAX_LOCATIONS
        and all(isinstance(v, str) and 0 < len(v.strip()) <= MAX_LOCATION_CHARS for v in value)
    )


def valid_trait(value: Any) -> bool:
    return _is_number(value) and 0 <= value <= 1


class _Proposer:
    def __init__(
        self,
        sections: Mapping[str, Any],
        removed: Mapping[str, Mapping[str, Any]],
        taxonomy: SkillTaxonomy,
        catalogue: Sequence[RoleProfile],
        questionnaire: Questionnaire,
    ) -> None:
        self.sections = sections
        self.removed = removed
        self.taxonomy = taxonomy
        self.catalogue = catalogue
        self.traits = trait_names(questionnaire)
        self.changes: dict[tuple[str, str | None], dict[str, Any]] = {}
        self.problems: list[str] = []
        self.questions: list[str] = []

    def _keep(self, change: dict[str, Any]) -> None:
        self.changes[(change["field"], change.get("skill_id"))] = change

    def _resolve(self, name: str) -> str | None:
        """A skill id for this name: the user's own skills first, then the taxonomy."""
        wanted = name.strip().casefold()
        known = [*all_skills(self.sections), *self.removed.values()]
        for skill in known:
            if wanted in (skill["name_th"].casefold(), skill["name_en"].casefold()):
                return str(skill["skill_id"])
        found = self.taxonomy.find(name)
        return found[0] if found else None

    def _suggest(self, name: str) -> str | None:
        """A skill outside the taxonomy is never scored, so chat asks instead of adding it."""
        written = name.strip()
        skill_id = self.taxonomy.suggest(written)
        known = self.taxonomy.get(skill_id) if skill_id else None
        if known is None:
            self.problems.append(f"ไม่พบทักษะ “{written}” ในระบบ จึงไม่ได้เพิ่มลงโปรไฟล์")
            return None
        self.questions.append(
            f"ไม่พบทักษะ “{written}” ในระบบ คุณอาจหมายถึง “{known.name_th}” หรือไม่ ถ้าไม่ใช่ กดยกเลิก"
        )
        return known.id

    def _add_skill(self, skill_id: str, level: Any) -> None:
        removed = self.removed.get(skill_id)
        if removed:
            name_th, fallback = removed["name_th"], removed["level"]
        else:
            known = self.taxonomy.get(skill_id)
            assert known is not None  # `_resolve` and `_suggest` give only these two kinds of id
            name_th, fallback = known.name_th, UNRATED_LEVELS[known.type]
        change = {
            "op": "add",
            "field": SKILLS,
            "skill_id": skill_id,
            "old_value": None,
            "new_value": {"name_th": name_th, "level": level or fallback},
        }
        if removed:
            change["restores_removed_skill"] = True
        self._keep(change)

    def _set_skill_field(self, skill: Mapping[str, Any], name: str, value: Any) -> None:
        if skill.get(name) != value:
            self._keep(
                {
                    "op": "set",
                    "field": f"{SKILLS}.{skill['skill_id']}.{name}",
                    "skill_id": skill["skill_id"],
                    "old_value": skill.get(name),
                    "new_value": value,
                }
            )

    def skill(self, item: Mapping[str, Any]) -> None:
        op, name = item.get("op"), item.get("skill")
        if not isinstance(name, str) or not name.strip() or len(name) > _MAX_NAME_CHARS:
            return
        level, years = item.get("level"), item.get("years")
        if level is not None and not (_is_int(level) and MIN_LEVEL <= level <= MAX_LEVEL):
            self.problems.append(f"ระดับของ {name.strip()} ต้องอยู่ระหว่าง 1 ถึง 4")
            return
        if years is not None and not (_is_number(years) and 0 <= years <= MAX_YEARS):
            return
        skill_id = self._resolve(name)
        if skill_id is None and (op == "add" or (op == "set" and level is not None)):
            skill_id = self._suggest(name)
            if skill_id is None:
                return
        skill = _skill(self.sections, skill_id)
        if op == "remove":
            if skill is not None:
                old = {"name_th": skill["name_th"], "level": skill["level"]}
                self._keep(
                    {
                        "op": "remove",
                        "field": SKILLS,
                        "skill_id": skill["skill_id"],
                        "old_value": old,
                        "new_value": None,
                    }
                )
            else:
                self.problems.append(f"ไม่พบทักษะ {name.strip()} ในโปรไฟล์")
        elif op in ("add", "set"):
            if skill is None:
                # A level for a skill not listed adds it. No id: only years for an unknown skill.
                if skill_id is not None and (op == "add" or level is not None):
                    self._add_skill(skill_id, level)
                return
            if level is not None:
                self._set_skill_field(skill, "level", level)
            if years is not None:
                self._set_skill_field(skill, "years", years)

    def _set_list(self, field: str, op: Any, values: list[str]) -> None:
        old = list(self.sections["preferences"].get(field.rsplit(".", 1)[1], []))
        key = (field, None)
        # One message can add and remove on the same list, so build on what it changed so far.
        current = self.changes[key]["new_value"] if key in self.changes else old
        if op == "add":
            new = list(dict.fromkeys([*current, *values]))
        elif op == "remove":
            new = [value for value in current if value not in values]
        elif op == "set":
            new = list(dict.fromkeys(values))
        else:
            return
        if new != old:
            self._keep({"op": "set", "field": field, "old_value": old, "new_value": new})
        else:
            self.changes.pop(key, None)

    def roles(self, item: Mapping[str, Any]) -> None:
        values = item.get("values")
        if isinstance(values, list):
            found = []
            for value in values:
                if not isinstance(value, str):
                    continue
                roles = find_roles(value, self.catalogue)
                if not roles:
                    self.problems.append(f"ยังไม่มีสายงาน “{value.strip()}” ในระบบ")
                found.extend(roles)
            if found:
                self._set_list(ROLES, item.get("op"), found)

    def locations(self, item: Mapping[str, Any]) -> None:
        values = item.get("values")
        if valid_locations(values):
            names = [v.strip() for v in values]
            if item.get("op") == "remove":
                listed = self.sections["preferences"].get("locations", [])
                for name in names:
                    if name not in listed:
                        self.problems.append(f"ไม่พบพื้นที่ “{name}” ในโปรไฟล์")
            self._set_list(LOCATIONS, item.get("op"), names)

    def salary(self, item: Mapping[str, Any]) -> None:
        value = item.get("value")
        old = self.sections["preferences"].get("desired_salary_thb")
        if valid_salary(value) and value != old:
            self._keep({"op": "set", "field": SALARY, "old_value": old, "new_value": value})

    def work_style(self, item: Mapping[str, Any]) -> None:
        trait, score = item.get("trait"), item.get("score")
        if not isinstance(trait, str) or trait not in self.traits:
            return
        if not (_is_int(score) and 1 <= score <= 5):
            return
        value = (score - 1) / 4
        old = self.sections["preferences"].get("work_style", {}).get(trait)
        if value != old:
            field = f"{WORK_STYLE}{trait}"
            self._keep({"op": "set", "field": field, "old_value": old, "new_value": value})


def propose_changes(
    items: Any,
    *,
    sections: Mapping[str, Any],
    removed: Mapping[str, Mapping[str, Any]],
    taxonomy: SkillTaxonomy,
    catalogue: Sequence[RoleProfile],
    questionnaire: Questionnaire,
) -> list[dict[str, Any]]:
    """Contract `EditChange`s from what the LLM suggested. Anything else is dropped."""
    changes, _problems, _questions = review_changes(
        items,
        sections=sections,
        removed=removed,
        taxonomy=taxonomy,
        catalogue=catalogue,
        questionnaire=questionnaire,
    )
    return changes


def review_changes(
    items: Any,
    *,
    sections: Mapping[str, Any],
    removed: Mapping[str, Mapping[str, Any]],
    taxonomy: SkillTaxonomy,
    catalogue: Sequence[RoleProfile],
    questionnaire: Questionnaire,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """The changes that hold up, then in Thai what could not be done and which names are guesses."""
    if not isinstance(items, list):
        return [], [], []
    proposer = _Proposer(sections, removed, taxonomy, catalogue, questionnaire)
    handlers = {
        "skill": proposer.skill,
        "interested_roles": proposer.roles,
        "locations": proposer.locations,
        "desired_salary": proposer.salary,
        "work_style": proposer.work_style,
    }
    for item in items:
        target = item.get("target") if isinstance(item, dict) else None
        handler = handlers.get(target) if isinstance(target, str) else None
        if handler is not None:
            handler(item)
    changes = list(proposer.changes.values())
    gone = {c["skill_id"] for c in changes if c["op"] == "remove"}
    # Removing a skill wins over changing it in the same message.
    kept = [c for c in changes if c["op"] == "remove" or c.get("skill_id") not in gone]
    return kept[:MAX_CHANGES], proposer.problems, proposer.questions


def _role_names(role_ids: Sequence[str], catalogue: Sequence[RoleProfile]) -> str:
    names = {role.role_id: role.title_th for role in catalogue}
    return ", ".join(names.get(r, r) for r in role_ids) or "ไม่มี"


def _describe(
    change: Mapping[str, Any],
    sections: Mapping[str, Any],
    catalogue: Sequence[RoleProfile],
    questionnaire: Questionnaire,
) -> str:
    field, new = change["field"], change["new_value"]
    if change["op"] == "add":
        start = "เพิ่มทักษะที่คุณเคยลบกลับมา:" if change.get("restores_removed_skill") else "เพิ่มทักษะ"
        return f"{start} {new['name_th']} ระดับ {new['level']}"
    if change["op"] == "remove":
        return f"ลบทักษะ {change['old_value']['name_th']}"
    if field == SALARY:
        return f"เปลี่ยนเงินเดือนที่ต้องการเป็น ฿{new:,}"
    if field == ROLES:
        return f"เปลี่ยนสายงานที่สนใจเป็น {_role_names(new, catalogue)}"
    if field == LOCATIONS:
        return f"เปลี่ยนพื้นที่ทำงานเป็น {', '.join(new) or 'ไม่มี'}"
    if field.startswith(WORK_STYLE):
        return f"เปลี่ยนรูปแบบการทำงานเป็น: {trait_label(questionnaire, field.rsplit('.', 1)[1], new)}"
    skill = _skill(sections, change["skill_id"])
    name = skill["name_th"] if skill else change["skill_id"]
    if field.endswith(".years"):
        return f"เปลี่ยนประสบการณ์ {name} เป็น {new} ปี"
    return f"เปลี่ยนระดับ {name} จาก {change['old_value']} เป็น {new}"


def summary_th(
    changes: Sequence[Mapping[str, Any]],
    sections: Mapping[str, Any],
    catalogue: Sequence[RoleProfile],
    questionnaire: Questionnaire,
) -> str:
    return " · ".join(_describe(c, sections, catalogue, questionnaire) for c in changes)


def _preference_value(sections: Mapping[str, Any], field: str) -> Any:
    preferences = sections["preferences"]
    if field.startswith(WORK_STYLE):
        return preferences.get("work_style", {}).get(field.rsplit(".", 1)[1])
    default: list[str] | None = None if field == SALARY else []
    return preferences.get(field.rsplit(".", 1)[1], default)


def has_conflict(sections: Mapping[str, Any], change: Mapping[str, Any]) -> bool:
    """True when the profile no longer has what the change was proposed against."""
    skill = _skill(sections, change.get("skill_id"))
    if change["op"] == "add":
        return skill is not None
    if change["op"] == "remove":
        return skill is None
    if change["field"].startswith(f"{SKILLS}."):
        name = change["field"].rsplit(".", 1)[1]
        return skill is None or skill.get(name) != change["old_value"]
    return bool(_preference_value(sections, change["field"]) != change["old_value"])


def _mark_edited(skill: dict[str, Any], evidence_id: str) -> None:
    skill["edited_by_user"] = True
    if evidence_id not in skill["evidence_ids"]:
        skill["evidence_ids"] = [*skill["evidence_ids"], evidence_id]


def _insert_skill(sections: dict[str, Any], skill: dict[str, Any]) -> None:
    sections["soft_skills" if skill["kind"] == "soft" else "hard_skills"].append(skill)


def remove_skill(sections: dict[str, Any], skill_id: str) -> None:
    for name in ("hard_skills", "soft_skills"):
        sections[name] = [s for s in sections[name] if s["skill_id"] != skill_id]


def set_preference(
    sections: dict[str, Any], field: str, value: Any, questionnaire: Questionnaire
) -> None:
    """Sets one preference and remembers it, so generating the profile again keeps it (FR-33)."""
    preferences = sections["preferences"]
    if field.startswith(WORK_STYLE):
        trait = field.rsplit(".", 1)[1]
        preferences["work_style"] = {**preferences.get("work_style", {}), trait: value}
        relabel_trait(sections["work_style"], trait, value, questionnaire)
    else:
        preferences[field.rsplit(".", 1)[1]] = value
    sections.setdefault(EDITED_PREFERENCES, {})[field] = value


def apply_changes(
    sections: Mapping[str, Any],
    changes: Sequence[Mapping[str, Any]],
    *,
    removed: Mapping[str, Mapping[str, Any]],
    taxonomy: SkillTaxonomy,
    questionnaire: Questionnaire,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """A new copy of the sections with every change applied, citing the user's action (FR-33)."""
    out = copy.deepcopy(dict(sections))
    evidence_id = str(evidence["id"])
    out["evidence"][evidence_id] = dict(evidence)
    for change in changes:
        skill_id, new = change.get("skill_id"), change["new_value"]
        if change["op"] == "remove":
            remove_skill(out, str(skill_id))
        elif change["op"] == "add":
            base = removed.get(str(skill_id))
            known = taxonomy.get(str(skill_id))
            skill = copy.deepcopy(dict(base)) if base else _new_skill(skill_id, new, known)
            skill["level"] = new["level"]
            # Its source may be gone by now, such as a deleted CV.
            skill["evidence_ids"] = [i for i in skill["evidence_ids"] if i in out["evidence"]]
            _mark_edited(skill, evidence_id)
            _insert_skill(out, skill)
        elif change["field"].startswith(f"{SKILLS}."):
            skill = _skill(out, skill_id)
            assert skill is not None  # checked by has_conflict
            skill[change["field"].rsplit(".", 1)[1]] = new
            _mark_edited(skill, evidence_id)
        else:
            set_preference(out, change["field"], new, questionnaire)
    return out


def _new_skill(skill_id: Any, new: Mapping[str, Any], known: Any) -> dict[str, Any]:
    return {
        "skill_id": skill_id,
        "name_th": known.name_th if known else new["name_th"],
        "name_en": known.name_en if known else new["name_th"],
        "kind": known.type if known else "hard",
        "level": new["level"],
        "evidence_ids": [],
        "edited_by_user": False,
    }


def keep_user_edits(
    sections: dict[str, Any],
    previous: Mapping[str, Any],
    questionnaire: Questionnaire,
    removed: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """What the user edited survives generating the profile again (FR-31, FR-33)."""
    for evidence_id, item in previous["evidence"].items():
        if item.get("kind") == "user_action":
            sections["evidence"][evidence_id] = item
    # The source may be gone by now, such as a replaced CV: a skill must still cite something.
    kept = [s for s in all_skills(previous) if s.get("edited_by_user")]
    for skill in [*kept, *removed]:
        for evidence_id in skill["evidence_ids"]:
            if evidence_id in previous["evidence"]:
                sections["evidence"].setdefault(evidence_id, previous["evidence"][evidence_id])
    for old in all_skills(previous):
        if not old.get("edited_by_user"):
            continue
        skill = _skill(sections, old["skill_id"])
        if skill is None:
            _insert_skill(sections, copy.deepcopy(old))
            continue
        skill["level"] = old["level"]
        if "years" in old:
            skill["years"] = old["years"]
        skill["edited_by_user"] = True
        cited = [i for i in old["evidence_ids"] if i not in skill["evidence_ids"]]
        skill["evidence_ids"] = [*skill["evidence_ids"], *cited]
    for field, value in previous.get(EDITED_PREFERENCES, {}).items():
        set_preference(sections, field, value, questionnaire)
    return sections
