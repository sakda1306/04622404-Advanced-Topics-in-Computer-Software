"""Questionnaire endpoints (Contract.md §2.3, PRD FR-5 – FR-7) on the real data file."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.deps import Container
from app.infra.models import Answer
from tests.conftest import ClientFactory, assert_problem, register
from tests.pdf_fixtures import make_pdf
from tests.test_cv_parser import CV_EN

SKILLS = [
    {"skill_id": "python", "level": 2},
    {"skill_id": "sql", "level": 3},
    {"skill_id": "docker", "level": 1},
]


async def _put(client: httpx.AsyncClient, question_id: str, value: Any) -> httpx.Response:
    return await client.put(f"/api/questionnaire/answers/{question_id}", json={"value": value})


def _questions(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {q["question_id"]: q for s in body["sections"] for q in s["questions"]}


async def test_every_endpoint_needs_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/questionnaire"), 401, "UNAUTHENTICATED")
    assert_problem(await client.get("/api/questionnaire/answers"), 401, "UNAUTHENTICATED")
    assert_problem(await _put(client, "ed_level", "bachelor"), 401, "UNAUTHENTICATED")


async def test_questions_hide_file_only_fields(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/questionnaire")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"]
    assert [s["id"] for s in body["sections"]] == ["skills", "work_style", "soft_skills", "goals"]
    questions = _questions(body)
    assert len(questions) == 22
    for question in questions.values():
        assert not {"slot", "trait", "skill_id", "source_ids", "options_source"} & set(question)


async def test_contract_fields_are_sent(user: httpx.AsyncClient) -> None:
    questions = _questions((await user.get("/api/questionnaire")).json())
    assert questions["mo_drivers"]["max_choices"] == 3
    assert questions["ws_teamwork"]["scale"]["min_label_th"] == "ทำงานคนเดียวเป็นหลัก"
    assert questions["ss_example"]["optional"] is True
    assert {"value": "none", "label_th": "ยังไม่มีประสบการณ์"} in questions["ex_it_experience"][
        "options"
    ]


async def test_options_source_becomes_options(user: httpx.AsyncClient) -> None:
    questions = _questions((await user.get("/api/questionnaire")).json())

    roles = questions["go_interested_roles"]["options"]
    assert len(roles) == 26
    assert {
        "value": "software-engineer",
        "label_th": "วิศวกรซอฟต์แวร์",
        "label_en": "Software Engineer",
    } in roles
    assert all(o["label_en"] for o in roles)

    skills = {o["value"] for o in questions["sk_tech_stack"]["options"]}
    assert "python" in skills
    assert "communication" not in skills  # the checklist is hard skills only (soft skills: ss_*)


async def test_attribution_lists_only_licensed_sources(user: httpx.AsyncClient) -> None:
    attribution = (await user.get("/api/questionnaire")).json()["attribution"]
    assert "O*NET" in attribution["text_th"]
    assert len(attribution["sources"]) == 2  # the team's own source has no licence to credit
    for source in attribution["sources"]:
        assert set(source) == {"title", "url", "license", "license_url", "attribution"}
        assert source["license"] == "CC BY 4.0"


async def test_answers_start_empty(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/questionnaire/answers")
    assert response.status_code == 200
    assert response.json() == {"answers": {}, "answered": 0, "total": 22}


async def test_saved_answers_can_be_resumed(user: httpx.AsyncClient) -> None:
    assert (await _put(user, "sk_tech_stack", SKILLS)).status_code == 200
    assert (await _put(user, "ws_teamwork", 4)).status_code == 200
    assert (await _put(user, "mo_drivers", ["learning", "income"])).status_code == 200
    assert (await _put(user, "ss_example", "  แก้บั๊กกับทีม  ")).status_code == 200
    assert (await user.get("/api/questionnaire/answers")).json() == {
        "answers": {
            "sk_tech_stack": SKILLS,
            "ws_teamwork": 4,
            "mo_drivers": ["learning", "income"],
            "ss_example": "แก้บั๊กกับทีม",
        },
        "answered": 4,
        "total": 22,
    }


async def test_answering_again_replaces_the_answer(
    container: Container, user: httpx.AsyncClient
) -> None:
    await _put(user, "ed_level", "bachelor")
    await _put(user, "ed_level", "postgraduate")
    answers = (await user.get("/api/questionnaire/answers")).json()["answers"]
    assert answers == {"ed_level": "postgraduate"}
    async with container.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Answer)) == 1


async def test_users_only_see_their_own_answers(client_factory: ClientFactory) -> None:
    alice, bob = client_factory(), client_factory()
    await register(alice, "alice@example.com")
    await register(bob, "bob@example.com")
    await _put(alice, "ed_level", "bachelor")
    await _put(bob, "ed_level", "diploma")
    assert (await alice.get("/api/questionnaire/answers")).json()["answers"] == {
        "ed_level": "bachelor"
    }
    assert (await bob.get("/api/questionnaire/answers")).json()["answers"] == {
        "ed_level": "diploma"
    }


async def test_clearing_an_answer_leaves_other_users_alone(client_factory: ClientFactory) -> None:
    alice, bob = client_factory(), client_factory()
    await register(alice, "alice@example.com")
    await register(bob, "bob@example.com")
    await _put(alice, "ss_example", "ของอลิซ")
    await _put(bob, "ss_example", "ของบ็อบ")
    await _put(alice, "ss_example", "")
    assert (await alice.get("/api/questionnaire/answers")).json()["answers"] == {}
    assert (await bob.get("/api/questionnaire/answers")).json()["answers"] == {
        "ss_example": "ของบ็อบ"
    }


async def test_unknown_question(user: httpx.AsyncClient) -> None:
    assert_problem(await _put(user, "no_such_question", "x"), 404, "QUESTION_NOT_FOUND")


@pytest.mark.parametrize(
    ("question_id", "value"),
    [
        ("ed_level", "not-an-option"),
        ("ed_level", 1),
        ("ed_level", None),
        ("ed_level", ""),
        ("ws_teamwork", 0),
        ("ws_teamwork", 6),
        ("ws_teamwork", "3"),
        ("ws_teamwork", 3.5),
        ("ws_teamwork", True),
        ("mo_drivers", "learning"),
        ("mo_drivers", ["learning", "not-an-option"]),
        ("mo_drivers", ["learning", "learning"]),
        ("mo_drivers", ["learning", "challenge", "impact", "income"]),  # over max_choices (3)
        ("go_interested_roles", ["not-a-role"]),
        ("sk_tech_stack", "python"),
        ("sk_tech_stack", ["python"]),
        ("sk_tech_stack", [{"skill_id": "python"}]),
        ("sk_tech_stack", [{"skill_id": "python", "level": 0}]),
        ("sk_tech_stack", [{"skill_id": "python", "level": 5}]),
        ("sk_tech_stack", [{"skill_id": "python", "level": True}]),
        ("sk_tech_stack", [{"skill_id": "python", "level": 2, "extra": 1}]),
        ("sk_tech_stack", [{"skill_id": "not-a-skill", "level": 2}]),
        ("sk_tech_stack", [{"skill_id": "communication", "level": 2}]),  # a soft skill
        ("sk_tech_stack", [{"skill_id": "python", "level": 2}, {"skill_id": "python", "level": 3}]),
        ("ss_example", 5),
        ("ss_example", "ก" * 1001),
    ],
)
async def test_value_must_fit_the_question(
    user: httpx.AsyncClient, question_id: str, value: Any
) -> None:
    body = assert_problem(await _put(user, question_id, value), 422, "VALIDATION_ERROR")
    assert body["details"]["fields"][0]["field"] == "value"
    assert (await user.get("/api/questionnaire/answers")).json()["answered"] == 0


async def test_rejected_value_is_not_echoed(user: httpx.AsyncClient) -> None:
    response = await _put(user, "ed_level", "secret-text-from-user")
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert "secret-text-from-user" not in response.text


@pytest.mark.parametrize(
    ("question_id", "first", "empty"),
    [
        ("ss_example", "ตัวอย่าง", "   "),
        ("go_interested_roles", ["ai-engineer"], []),
        ("sk_tech_stack", SKILLS, []),
    ],
)
async def test_empty_value_clears_the_answer(
    user: httpx.AsyncClient, question_id: str, first: Any, empty: Any
) -> None:
    await _put(user, question_id, first)
    response = await _put(user, question_id, empty)
    assert response.status_code == 200, response.text
    assert response.json()["saved"] is True
    assert (await user.get("/api/questionnaire/answers")).json()["answers"] == {}


async def test_each_answer_returns_updated_completeness(user: httpx.AsyncClient) -> None:
    first = (await _put(user, "sk_tech_stack", SKILLS)).json()
    assert first["saved"] is True
    assert first["completeness"]["score"] == 35
    assert first["completeness"]["inputs"]["questionnaire"] == "partial"
    assert first["completeness"]["missing_required"] == ["experience"]

    second = (await _put(user, "ex_it_experience", "none")).json()
    assert second["completeness"]["score"] == 50
    assert second["completeness"]["missing_required"] == []
    assert second["completeness"]["can_generate"] is False

    third = (await _put(user, "go_location", "bangkok")).json()
    assert third["completeness"]["score"] == 65
    assert third["completeness"]["can_generate"] is True


async def test_cv_confirm_counts_the_questionnaire_too(user: httpx.AsyncClient) -> None:
    await _put(user, "go_location", "bangkok")
    await user.post("/api/cv", files={"file": ("cv.pdf", make_pdf(CV_EN), "application/pdf")})
    response = await user.put(
        "/api/cv/confirm",
        json={
            "skills": [
                {"name": "Python", "skill_id": "python", "level": 2, "line_no": 1},
                {"name": "SQL", "skill_id": "sql", "level": 2, "line_no": 1},
                {"name": "Docker", "skill_id": "docker", "level": 2, "line_no": 1},
            ],
            "education": [],
            "experience": [{"title": "Backend Developer"}],
        },
    )
    assert response.status_code == 200, response.text
    completeness = response.json()["completeness"]
    assert completeness["score"] == 65  # 35 + 15 from the CV, 15 goals from the questionnaire
    assert completeness["can_generate"] is True
    assert completeness["inputs"]["cv"] == "done"
    assert completeness["inputs"]["questionnaire"] == "partial"


async def test_answering_uses_no_quota(user: httpx.AsyncClient) -> None:
    response = await _put(user, "ed_level", "bachelor")
    assert response.headers["x-quota-requests-remaining"] == "40"


async def test_deleting_the_account_removes_answers(
    container: Container, user: httpx.AsyncClient
) -> None:
    await _put(user, "ed_level", "bachelor")
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text
    async with container.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Answer)) == 0
