"""Completeness meter (Design.md §4.1). Pure Python; returns the Contract `Completeness` shape.

The CV, the questionnaire and facts from chat feed it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MIN_HARD_SKILLS = 3
MIN_SOFT_SKILLS = 3

# (slot, points, required, what to add next) in the order of Design.md §4.1.
SLOTS: list[tuple[str, int, bool, str]] = [
    ("hard_skills", 35, True, "ทักษะด้านเทคนิคอย่างน้อย 3 รายการ พร้อมระดับ"),
    ("experience", 15, True, "ประสบการณ์ทำงานหรือฝึกงาน (หรือบอกว่ายังไม่มีประสบการณ์)"),
    ("soft_skills", 15, False, "ทักษะด้านการทำงานร่วมกับผู้อื่นอย่างน้อย 3 รายการ พร้อมตัวอย่าง"),
    ("goals", 15, False, "เป้าหมาย: สายงานที่สนใจ เงินเดือนที่ต้องการ หรือพื้นที่ทำงาน"),
    ("work_style", 10, False, "รูปแบบการทำงานที่ชอบ"),
    ("education", 10, False, "ประวัติการศึกษา"),
]


@dataclass
class CvInput:
    confirmed: bool
    skills: list[dict[str, Any]] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class QuestionnaireInput:
    """What at least one saved answer contributes (domain.questionnaire.summarize)."""

    done: bool  # every required question is answered
    skills: list[dict[str, Any]] = field(default_factory=list)
    no_experience: bool = False
    education: bool = False
    goals: bool = False
    work_style: bool = False
    soft_skills_high: int = 0
    soft_skills_example: bool = False


@dataclass
class ChatInput:
    """Facts the user gave in chat, oldest first (services.completeness_service)."""

    skills: list[dict[str, Any]] = field(default_factory=list)
    has_experience: bool = False
    no_experience: bool = False
    soft_skills: list[dict[str, Any]] = field(default_factory=list)
    goals: bool = False
    work_style: bool = False
    education: bool = False


def _skill_key(skill: dict[str, Any]) -> str:
    # The same skill from any source counts once. Free-text skills have no id yet.
    return skill.get("skill_id") or skill["name"].lower()


def _rated(
    cv: CvInput | None, questionnaire: QuestionnaireInput | None, chat: ChatInput | None
) -> set[str]:
    rated = {_skill_key(s) for s in (cv.skills if cv and cv.confirmed else []) if s.get("level")}
    rated |= {s["skill_id"] for s in (questionnaire.skills if questionnaire else [])}
    # A chat skill the taxonomy cannot place scores nothing (Design.md §4.2), so it does not count.
    rated |= {
        s["skill_id"] for s in (chat.skills if chat else []) if s.get("level") and s.get("skill_id")
    }
    return rated


def rated_skill_count(
    *, cv: CvInput | None, questionnaire: QuestionnaireInput | None, chat: ChatInput | None
) -> int:
    return len(_rated(cv if cv is not None and cv.confirmed else None, questionnaire, chat))


def _filled(
    cv: CvInput | None, questionnaire: QuestionnaireInput | None, chat: ChatInput | None
) -> dict[str, bool]:
    q = questionnaire or QuestionnaireInput(done=False)
    c = chat or ChatInput()
    cv = cv if cv is not None and cv.confirmed else None  # a draft is not used (FR-3)
    soft_count = q.soft_skills_high + len({s["name"].lower() for s in c.soft_skills})
    soft_example = q.soft_skills_example or any(s.get("example") for s in c.soft_skills)
    return {
        "hard_skills": len(_rated(cv, q, c)) >= MIN_HARD_SKILLS,
        "experience": (
            bool(cv and cv.experience) or q.no_experience or c.has_experience or c.no_experience
        ),
        "soft_skills": soft_count >= MIN_SOFT_SKILLS and soft_example,
        "goals": q.goals or c.goals,
        "work_style": q.work_style or c.work_style,
        "education": bool(cv and cv.education) or q.education or c.education,
    }


def unrated_skills(
    *, cv: CvInput | None, questionnaire: QuestionnaireInput | None, chat: ChatInput | None
) -> list[str]:
    """Names of skills the user has, but with no level from any source yet."""
    rated = _rated(cv, questionnaire, chat)
    known = [s for s in (chat.skills if chat else []) if s.get("skill_id")]
    skills = [*(cv.skills if cv and cv.confirmed else []), *known]
    names = {_skill_key(s): s["name"] for s in skills if _skill_key(s) not in rated}
    return list(names.values())


def missing_slots(meter: dict[str, Any]) -> list[str]:
    """Empty slots: required first, then the most points (Design.md §4.1)."""
    missing = [s for s in meter["slots"] if not s["filled"]]
    missing.sort(key=lambda s: (not s["required"], -s["max_points"]))
    return [s["slot"] for s in missing]


def next_slot(meter: dict[str, Any]) -> str | None:
    """The slot to ask about."""
    missing = missing_slots(meter)
    return missing[0] if missing else None


def compute_completeness(
    *,
    cv: CvInput | None,
    questionnaire: QuestionnaireInput | None = None,
    chat: ChatInput | None = None,
    threshold: int,
) -> dict[str, Any]:
    filled = _filled(cv, questionnaire, chat)
    slots = [
        {
            "slot": name,
            "filled": filled[name],
            "required": required,
            "points": points if filled[name] else 0,
            "max_points": points,
        }
        for name, points, required, _ in SLOTS
    ]
    score = sum(s["points"] for s in slots)
    missing_required = [name for name, _, required, _ in SLOTS if required and not filled[name]]
    cv_done = cv is not None and cv.confirmed
    has_input = cv_done or questionnaire is not None
    can_generate = has_input and not missing_required and score >= threshold
    questionnaire_status = "skipped"
    if questionnaire is not None:
        questionnaire_status = "done" if questionnaire.done else "partial"
    # Required slots first, then by points (Design.md §4.1, gap_question order).
    missing = sorted(
        (slot for slot in SLOTS if not filled[slot[0]]), key=lambda s: (not s[2], -s[1])
    )
    return {
        "score": score,
        "can_generate": can_generate,
        "slots": slots,
        "missing_required": missing_required,
        "inputs": {
            "cv": "done" if cv_done else "skipped",
            "questionnaire": questionnaire_status,
            "chat": "done" if can_generate else "needed",
        },
        "missing_th": [text for *_, text in missing],
    }
