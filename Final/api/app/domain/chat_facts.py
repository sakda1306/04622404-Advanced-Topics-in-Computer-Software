"""Check what the LLM extracted from one chat message (Design.md §4.1, FR-8).

The model's answer is untrusted: wrong shapes are dropped, a skill must really be in the user's
message or in the question they are answering, and a level must be a number or words the user wrote.
Levels drive the match score, and the model was seen making them up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.domain.matching.skills import SkillTaxonomy

_MAX_ITEMS = 10
_MAX_TEXT = 200
_LEVELS = frozenset({1, 2, 3, 4})
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# "ใช้ Docker มา 3 ปี" counts years: the 3 is not a level.
_COUNTED = re.compile(
    r"(?<!\d)\d+\s*(?:ปี|เดือน|สัปดาห์|อาทิตย์|วัน|ครั้ง|คน|ตัว|งาน|โปรเจกต์|โครงการ|บาท"
    r"|years?|yrs?|months?|weeks?|days?|times?|people|projects?)",
    re.IGNORECASE,
)
_DENIED_LEVEL = re.compile(r"ไม่(?:ค่อย)?\s*(?:เก่ง|คล่อง|ชำนาญ|เชี่ยวชาญ)")
_LEVEL_WORDS = {
    1: re.compile(r"ระดับ\s*หนึ่ง|พื้นฐาน|นิดหน่อย|เล็กน้อย|เพิ่งเริ่ม|เริ่มต้น|มือใหม่|beginner|basic", re.I),
    2: re.compile(r"ระดับ\s*สอง|พอใช้|ใช้งานได้|ใช้ได้|ปานกลาง|intermediate", re.I),
    3: re.compile(r"ระดับ\s*สาม|เก่ง|คล่อง|ชำนาญ|advanced|strong", re.I),
    4: re.compile(r"ระดับ\s*สี่|เก่งมาก|เชี่ยวชาญ|expert", re.I),
}
_ABOUT_EXPERIENCE = re.compile(
    r"ประสบการณ์|ทำงาน|ฝึกงาน|โปรเจกต์|โครงงาน|เคยทำ|project|intern|experience|\bjob\b", re.I
)
_EXPERIENCE_QUESTION_WORD = "ประสบการณ์"


@dataclass(frozen=True, slots=True)
class ChatFact:
    kind: str  # skill, experience, education, preference, soft_skill, goal
    value: dict[str, Any]


def _text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:_MAX_TEXT]


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:_MAX_ITEMS]


def _whole_number(value: Any) -> int | None:
    is_number = isinstance(value, int) and not isinstance(value, bool)
    return value if is_number and value >= 0 else None


def _user_gave_level(level: Any, message: str) -> bool:
    if not isinstance(level, int) or isinstance(level, bool) or level not in _LEVELS:
        return False
    text = _COUNTED.sub(" ", message.translate(_THAI_DIGITS))
    if re.search(rf"(?<!\d){level}(?!\d)", text):
        return True
    return _LEVEL_WORDS[level].search(_DENIED_LEVEL.sub(" ", text)) is not None


def _skill_facts(
    data: dict[str, Any], *, message: str, last_question: str, taxonomy: SkillTaxonomy
) -> list[ChatFact]:
    said = f"{message}\n{last_question}"
    said_ids = taxonomy.find(said)
    facts = []
    for item in _items(data.get("skills")):
        name = _text(item.get("name"))
        if name is None:
            continue
        found = taxonomy.find(name)
        skill_id = found[0] if found else taxonomy.closest(name)
        if name.casefold() not in said.casefold() and skill_id not in said_ids:
            continue
        known = taxonomy.get(skill_id) if skill_id else None
        if known is not None and known.type == "soft":
            facts.append(ChatFact("soft_skill", {"name": name, "example": None}))
            continue
        level = item.get("level")
        level = level if _user_gave_level(level, message) else None
        value = {"name": name, "skill_id": skill_id, "level": level}
        facts.append(ChatFact("skill", value))
    return facts


def _experience_facts(data: dict[str, Any], *, message: str, last_question: str) -> list[ChatFact]:
    facts = []
    for item in _items(data.get("experience")):
        title = _text(item.get("title"))
        if title is not None:
            value = {
                "title": title,
                "company": _text(item.get("company")),
                "months": _whole_number(item.get("months")),
            }
            facts.append(ChatFact("experience", value))
    # "ยังไม่มีทักษะ" is not "no experience", and this slot is required, so the model is not trusted.
    about_it = _EXPERIENCE_QUESTION_WORD in last_question or _ABOUT_EXPERIENCE.search(message)
    if not facts and data.get("no_experience") is True and about_it:
        facts.append(ChatFact("experience", {"none": True}))
    return facts


def _education_facts(data: dict[str, Any]) -> list[ChatFact]:
    facts = []
    for item in _items(data.get("education")):
        value = {key: _text(item.get(key)) for key in ("degree", "field", "institution")}
        if any(value.values()):
            facts.append(ChatFact("education", value))
    return facts


def _soft_skill_facts(data: dict[str, Any]) -> list[ChatFact]:
    facts = []
    for item in _items(data.get("soft_skills")):
        name = _text(item.get("name"))
        if name is not None:
            value = {"name": name, "example": _text(item.get("example"))}
            facts.append(ChatFact("soft_skill", value))
    return facts


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_text(item) for item in value[:_MAX_ITEMS]) if text]


def _goal_facts(data: dict[str, Any]) -> list[ChatFact]:
    goals = data.get("goals")
    if not isinstance(goals, dict):
        return []
    value = {
        "roles": _text_list(goals.get("roles")),
        "locations": _text_list(goals.get("locations")),
        "desired_salary_thb": _whole_number(goals.get("desired_salary_thb")) or None,
    }
    return [ChatFact("goal", value)] if any(value.values()) else []


def _preference_facts(data: dict[str, Any]) -> list[ChatFact]:
    text = _text(data.get("work_style"))
    return [ChatFact("preference", {"text": text})] if text else []


def parse_facts(
    data: dict[str, Any], *, message: str, last_question: str, taxonomy: SkillTaxonomy
) -> list[ChatFact]:
    return [
        *_skill_facts(data, message=message, last_question=last_question, taxonomy=taxonomy),
        *_experience_facts(data, message=message, last_question=last_question),
        *_education_facts(data),
        *_soft_skill_facts(data),
        *_goal_facts(data),
        *_preference_facts(data),
    ]
