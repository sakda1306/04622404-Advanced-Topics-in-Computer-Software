"""The fixed questionnaire from `data/questionnaire.json` (PRD FR-5 – FR-7, Contract.md §2.3).

Pure Python: what the web may see, whether a value fits a question, and what saved answers
mean for the completeness meter (Design.md §4.1).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.completeness import QuestionnaireInput

TEXT_MAX_CHARS = 1000
MIN_LEVEL, MAX_LEVEL = 1, 4  # Design.md §6: 1 basic, 2 working, 3 strong, 4 expert
HIGH_SELF_RATING = 4  # Design.md §6: 4 or 5 adds the soft skill as self-reported
NO_EXPERIENCE = "none"

# Everything else in a question (slot, trait, skill_id, source_ids, ...) stays on the server.
_PUBLIC_FIELDS = ("question_id", "type", "text_th", "options", "scale", "max_choices", "optional")
_SOURCE_FIELDS = ("title", "url", "license", "license_url", "attribution")
_ATTRIBUTION_TH = (  # DesignSystem.md section 5
    "คำถามพัฒนาโดยทีมผู้พัฒนา โดยดัดแปลงจากมิติ Work Styles และ Skills ของ O*NET® "
    "(USDOL/ETA, CC BY 4.0) ซึ่ง USDOL/ETA ไม่ได้รับรองเนื้อหานี้"
)


class InvalidAnswer(ValueError):
    """The value does not fit the question. Never carries the submitted value."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _option_values(question: dict[str, Any]) -> set[str]:
    return {option["value"] for option in question["options"]}


def _check_single(question: dict[str, Any], value: Any) -> str:
    if not isinstance(value, str) or value not in _option_values(question):
        raise InvalidAnswer("invalid_choice", "must be one of the options")
    return value


def _check_multi(question: dict[str, Any], value: Any) -> list[str] | None:
    if not isinstance(value, list):
        raise InvalidAnswer("invalid_type", "must be a list")
    if not value:
        return None
    options = _option_values(question)
    if not all(isinstance(item, str) and item in options for item in value):
        raise InvalidAnswer("invalid_choice", "every item must be one of the options")
    if len(set(value)) != len(value):
        raise InvalidAnswer("duplicate", "items must not repeat")
    limit = question.get("max_choices")
    if limit is not None and len(value) > limit:
        raise InvalidAnswer("too_many", f"at most {limit} items")
    return value


def _check_scale(question: dict[str, Any], value: Any) -> int:
    scale = question["scale"]
    # type() and not isinstance(): JSON true would otherwise pass as 1.
    if type(value) is not int or not scale["min"] <= value <= scale["max"]:
        raise InvalidAnswer("out_of_range", f"must be a whole number {scale['min']}-{scale['max']}")
    return value


def _check_checklist(question: dict[str, Any], value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        raise InvalidAnswer("invalid_type", "must be a list")
    if not value:
        return None
    options = _option_values(question)
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"skill_id", "level"}:
            raise InvalidAnswer("invalid_type", "each item needs skill_id and level only")
        skill_id, level = item["skill_id"], item["level"]
        if not isinstance(skill_id, str) or skill_id not in options:
            raise InvalidAnswer("unknown_skill", "unknown skill id")
        if type(level) is not int or not MIN_LEVEL <= level <= MAX_LEVEL:
            raise InvalidAnswer("out_of_range", f"level must be {MIN_LEVEL}-{MAX_LEVEL}")
        if skill_id in seen:
            raise InvalidAnswer("duplicate", "a skill must not repeat")
        seen.add(skill_id)
    return value


def _check_text(_question: dict[str, Any], value: Any) -> str | None:
    if not isinstance(value, str):
        raise InvalidAnswer("invalid_type", "must be text")
    text = value.strip()
    if len(text) > TEXT_MAX_CHARS:
        raise InvalidAnswer("too_long", f"at most {TEXT_MAX_CHARS} characters")
    return text or None


_CHECKS = {
    "single": _check_single,
    "multi": _check_multi,
    "scale": _check_scale,
    "skill_checklist": _check_checklist,
    "text": _check_text,
}


def check_answer(question: dict[str, Any], value: Any) -> Any | None:
    """The value to store, or None when an empty list or blank text clears the answer.

    Clearing has to work: a user who unticks their last skill must not keep the old answer.
    """
    return _CHECKS[question["type"]](question, value)


class Questionnaire:
    def __init__(
        self, raw: dict[str, Any], skills: list[dict[str, Any]], roles: list[dict[str, Any]]
    ) -> None:
        resolved = {
            "skills.json": [
                {"value": s["id"], "label_th": s["name_th"]} for s in skills if s["type"] == "hard"
            ],
            # Roles carry the English name too, so the web can show "Thai · English".
            "roles.json": [
                {"value": r["id"], "label_th": r["name_th"], "label_en": r["name_en"]}
                for r in roles
            ],
        }
        self.version: str = raw["version"]
        self._sections = [
            {
                **section,
                "questions": [
                    {**q, "options": resolved[q["options_source"]]} if "options_source" in q else q
                    for q in section["questions"]
                ],
            }
            for section in raw["sections"]
        ]
        self._questions = {q["question_id"]: q for s in self._sections for q in s["questions"]}
        self._sources = raw["sources"]

    @classmethod
    def from_dir(cls, data_dir: Path) -> Questionnaire:
        def read(name: str) -> Any:
            return json.loads((data_dir / name).read_text(encoding="utf-8"))

        return cls(read("questionnaire.json"), read("skills.json"), read("roles.json"))

    def __len__(self) -> int:
        return len(self._questions)

    def question(self, question_id: str) -> dict[str, Any] | None:
        return self._questions.get(question_id)

    def questions(self) -> list[dict[str, Any]]:
        return list(self._questions.values())

    def number(self, question_id: str) -> int:
        """Its position in the file, from 1, for citations such as "แบบสอบถามข้อ 4"."""
        return list(self._questions).index(question_id) + 1

    def known_answers(self, answers: dict[str, Any]) -> dict[str, Any]:
        """Leaves out answers to questions that are no longer in the file."""
        return {qid: value for qid, value in answers.items() if qid in self._questions}

    def public_sections(self) -> list[dict[str, Any]]:
        return [
            {
                "id": section["id"],
                "title_th": section["title_th"],
                "questions": [
                    {f: q[f] for f in _PUBLIC_FIELDS if f in q} for q in section["questions"]
                ],
            }
            for section in self._sections
        ]

    def attribution(self) -> dict[str, Any]:
        return {
            "text_th": _ATTRIBUTION_TH,
            "sources": [
                {f: source[f] for f in _SOURCE_FIELDS}
                for source in self._sources
                if "license" in source  # the team's own questions have nothing to credit
            ],
        }

    def summarize(self, answers: dict[str, Any]) -> QuestionnaireInput | None:
        """What the answers fill in the completeness meter; None if nothing is answered."""
        answers = self.known_answers(answers)
        if not answers:
            return None

        def in_slot(slot: str) -> list[dict[str, Any]]:
            return [q for q in self._questions.values() if q.get("slot") == slot]

        def answered(slot: str) -> list[Any]:
            return [answers[q["question_id"]] for q in in_slot(slot) if q["question_id"] in answers]

        soft = in_slot("soft_skills")
        traits = [q for q in in_slot("work_style") if "trait" in q]
        required = [q for q in self._questions.values() if not q["optional"]]
        return QuestionnaireInput(
            done=all(q["question_id"] in answers for q in required),
            skills=[skill for value in answered("hard_skills") for skill in value],
            no_experience=NO_EXPERIENCE in answered("experience"),
            education=bool(answered("education")),
            goals=bool(answered("goals")),
            # All six: role scoring compares the user with the role on each trait (Design §4.3).
            work_style=all(q["question_id"] in answers for q in traits),
            soft_skills_high=sum(
                1
                for q in soft
                if "skill_id" in q and answers.get(q["question_id"], 0) >= HIGH_SELF_RATING
            ),
            soft_skills_example=any(
                q["type"] == "text" and q["question_id"] in answers for q in soft
            ),
        )


@lru_cache
def load_questionnaire(data_dir: str) -> Questionnaire:
    return Questionnaire.from_dir(Path(data_dir))
