"""Completeness meter from the CV (Design.md §4.1 table; questionnaire and chat come later)."""

from __future__ import annotations

from typing import Any

from app.domain.completeness import CvInput, compute_completeness


def _skills(n: int, level: int | None = 2) -> list[dict[str, Any]]:
    return [{"name": f"s{i}", "skill_id": None, "level": level, "line_no": 0} for i in range(n)]


def _slot(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in result["slots"] if s["slot"] == name)


def test_nothing_yet() -> None:
    result = compute_completeness(cv=None, threshold=65)
    assert result["score"] == 0
    assert result["can_generate"] is False
    assert result["missing_required"] == ["hard_skills", "experience"]
    assert result["inputs"] == {"cv": "skipped", "questionnaire": "skipped", "chat": "needed"}
    assert [s["slot"] for s in result["slots"]] == [
        "hard_skills",
        "experience",
        "soft_skills",
        "goals",
        "work_style",
        "education",
    ]
    assert result["missing_th"][0].startswith("ทักษะ")


def test_confirmed_cv_with_everything_from_a_cv() -> None:
    cv = CvInput(
        confirmed=True,
        skills=_skills(3),
        experience=[{"title": "Dev"}],
        education=[{"school": "KU"}],
    )
    result = compute_completeness(cv=cv, threshold=65)
    assert result["score"] == 60  # 35 + 15 + 10
    assert result["missing_required"] == []
    assert result["can_generate"] is False  # below 65: one more slot is needed (Design §4.1)
    assert result["inputs"]["cv"] == "done"
    assert _slot(result, "education")["filled"] is True


def test_hard_skills_need_three_with_levels() -> None:
    cv = CvInput(
        confirmed=True, skills=_skills(3, level=None) + _skills(2), experience=[], education=[]
    )
    assert _slot(compute_completeness(cv=cv, threshold=65), "hard_skills")["filled"] is False


def test_free_text_skills_repeated_in_a_cv_count_once() -> None:
    repeated = [{"name": n, "skill_id": None, "level": 2, "line_no": 0} for n in ("Go", "go", "GO")]
    cv = CvInput(confirmed=True, skills=repeated)
    assert _slot(compute_completeness(cv=cv, threshold=65), "hard_skills")["filled"] is False


def test_draft_cv_does_not_count() -> None:
    cv = CvInput(confirmed=False, skills=_skills(5), experience=[{"title": "Dev"}], education=[])
    result = compute_completeness(cv=cv, threshold=65)
    assert result["score"] == 0
    assert result["inputs"]["cv"] == "skipped"


def test_can_generate_when_threshold_is_lower() -> None:
    cv = CvInput(confirmed=True, skills=_skills(3), experience=[{"title": "Dev"}], education=[])
    result = compute_completeness(cv=cv, threshold=50)
    assert result["can_generate"] is True
    assert result["inputs"]["chat"] == "done"
