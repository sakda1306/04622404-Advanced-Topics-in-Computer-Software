"""From saved answers to the completeness meter (Design.md §4.1), on the real questionnaire."""

from __future__ import annotations

from typing import Any

from app.domain.completeness import CvInput, compute_completeness
from app.domain.questionnaire import load_questionnaire

THREE_SKILLS = [
    {"skill_id": "python", "level": 2},
    {"skill_id": "sql", "level": 2},
    {"skill_id": "docker", "level": 1},
]
ALL_TRAITS = {
    "ws_teamwork": 3,
    "ws_structure": 3,
    "ws_ambiguity": 3,
    "ws_pressure": 3,
    "ws_innovation": 3,
    "ws_leadership": 3,
}


def _meter(answers: dict[str, Any], cv: CvInput | None = None, threshold: int = 65) -> Any:
    summary = load_questionnaire("../data").summarize(answers)
    return compute_completeness(cv=cv, questionnaire=summary, threshold=threshold)


def _filled(result: dict[str, Any]) -> set[str]:
    return {s["slot"] for s in result["slots"] if s["filled"]}


def test_no_answers_is_skipped() -> None:
    result = _meter({})
    assert result["score"] == 0
    assert result["inputs"]["questionnaire"] == "skipped"
    assert result["can_generate"] is False


def test_status_is_done_once_every_required_question_is_answered() -> None:
    everything_required = {
        **ALL_TRAITS,
        "sk_tech_stack": THREE_SKILLS,
        "ex_it_experience": "none",
        "ed_level": "bachelor",
        "mo_drivers": ["learning"],
        "ss_adaptability": 4,
        "ss_collaboration": 4,
        "ss_communication": 4,
        "ss_growth": 4,
        "ss_prioritization": 4,
        "ss_perseverance": 4,
        "ss_attention_to_detail": 4,
        "ss_analytical_thinking": 4,
        "go_salary": "unsure",
        "go_location": "any",
    }
    assert _meter(everything_required)["inputs"]["questionnaire"] == "done"
    del everything_required["ws_teamwork"]
    assert _meter(everything_required)["inputs"]["questionnaire"] == "partial"


def test_hard_skills_need_three() -> None:
    assert "hard_skills" not in _filled(_meter({"sk_tech_stack": THREE_SKILLS[:2]}))
    assert "hard_skills" in _filled(_meter({"sk_tech_stack": THREE_SKILLS}))


def test_only_stating_no_experience_fills_the_experience_slot() -> None:
    # Design §4.1: entries, or "no experience" stated. Entries for the others come from chat.
    assert "experience" in _filled(_meter({"ex_it_experience": "none"}))
    for has_experience in ("projects", "lt_1y", "1_3y", "gt_3y"):
        assert "experience" not in _filled(_meter({"ex_it_experience": has_experience}))


def test_education_is_filled_by_its_question() -> None:
    assert "education" in _filled(_meter({"ed_level": "bachelor"}))


def test_any_goal_fills_the_goals_slot() -> None:
    assert "goals" in _filled(_meter({"go_location": "bangkok"}))
    assert "goals" in _filled(_meter({"go_salary": "20k_30k"}))
    assert "goals" in _filled(_meter({"go_interested_roles": ["ai-engineer"]}))


def test_work_style_needs_all_six_traits() -> None:
    assert "work_style" in _filled(_meter(ALL_TRAITS))
    one_short = {k: v for k, v in ALL_TRAITS.items() if k != "ws_leadership"}
    assert "work_style" not in _filled(_meter(one_short))
    # Motivation is not a trait the scoring reads, so it cannot stand in for one.
    assert "work_style" not in _filled(_meter({**one_short, "mo_drivers": ["learning"]}))


def test_soft_skills_need_three_rated_four_or_five_and_an_example() -> None:
    three_high = {"ss_adaptability": 4, "ss_collaboration": 5, "ss_growth": 4}
    assert "soft_skills" in _filled(_meter({**three_high, "ss_example": "ตัวอย่าง"}))
    assert "soft_skills" not in _filled(_meter(three_high))  # no example
    two_high_one_low = {**three_high, "ss_growth": 3, "ss_example": "ตัวอย่าง"}
    assert "soft_skills" not in _filled(_meter(two_high_one_low))


def test_questionnaire_only_user_can_generate() -> None:
    result = _meter(
        {"sk_tech_stack": THREE_SKILLS, "ex_it_experience": "none", "go_location": "any"}
    )
    assert result["score"] == 65
    assert result["can_generate"] is True
    assert result["inputs"]["cv"] == "skipped"


def test_cv_and_questionnaire_skills_are_counted_once_each() -> None:
    cv = CvInput(
        confirmed=True,
        skills=[{"name": "Python", "skill_id": "python", "level": 2, "line_no": 1}],
    )
    same_skill = {"sk_tech_stack": [{"skill_id": "python", "level": 3}]}
    assert "hard_skills" not in _filled(_meter(same_skill, cv=cv))
    two_more = {
        "sk_tech_stack": [{"skill_id": "python", "level": 3}, *THREE_SKILLS[1:]],
    }
    assert "hard_skills" in _filled(_meter(two_more, cv=cv))


def test_draft_cv_adds_nothing_to_the_questionnaire() -> None:
    draft = CvInput(confirmed=False, experience=[{"title": "Dev"}], education=[{"school": "KU"}])
    result = _meter({"ed_level": "bachelor"}, cv=draft)
    assert result["score"] == 10
    assert result["inputs"]["cv"] == "skipped"


def test_cv_alone_still_blocks_until_one_more_slot_and_questionnaire_adds_it() -> None:
    cv = CvInput(
        confirmed=True,
        skills=[{"name": f"s{i}", "skill_id": None, "level": 2, "line_no": 0} for i in range(3)],
        experience=[{"title": "Dev"}],
        education=[{"school": "KU"}],
    )
    assert _meter({}, cv=cv)["can_generate"] is False
    result = _meter({"go_location": "any"}, cv=cv)
    assert result["score"] == 75  # 35 + 15 + 10 from the CV, 15 goals
    assert result["can_generate"] is True


def test_answers_to_retired_questions_are_ignored() -> None:
    result = _meter({"old_question": "x"})
    assert result["inputs"]["questionnaire"] == "skipped"
