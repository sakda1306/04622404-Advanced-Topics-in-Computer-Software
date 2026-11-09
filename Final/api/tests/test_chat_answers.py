"""Chat answers per route (PRD FR-11, FR-12, FR-16, FR-17; Design.md §4.6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import Container
from app.core.clock import utcnow
from app.domain.chat_answers import find_roles, load_salary_reference, salary_answer
from app.domain.matching.roles import load_catalogue
from app.infra.jev import JevClient
from app.infra.models import ChatMessage, RoleCache
from app.services.market_service import DISCLAIMER_TH
from tests.test_profile import LLM_SECTIONS, Groq, _ready

CATALOGUE = load_catalogue("../data")
SALARY = load_salary_reference("../data")
TITLES = {role.role_id: role for role in CATALOGUE}
GOOD_CLAIM = {"text_th": "Python ของคุณอยู่ระดับ 3", "evidence_ids": ["cv-2"]}


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {
        "groq_api_key": "k",
        "groq_model": "main-model",
        "groq_router_model": "router-model",
        "groq_fallback_model": "router-model",
        "quota_daily_requests": 20,
        "quota_daily_tokens": 5000,
        "data_dir": "../data",
    }


@pytest.fixture
def groq(container: Container) -> Groq:
    return Groq(container)


@pytest.fixture
async def with_profile(container: Container, user: httpx.AsyncClient, groq: Groq) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    groq.requests.clear()


async def _ask(user: httpx.AsyncClient, message: str) -> dict[str, Any]:
    response = await user.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def _sent(groq: Groq) -> dict[str, Any]:
    return json.loads(groq.requests[-1]["messages"][1]["content"])


# --- naming a role


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("เงินเดือน QA เท่าไหร่", ["qa-engineer"]),
        ("ai engineer ได้เท่าไหร่", ["ai-engineer"]),
        ("เงินเดือนนักวิเคราะห์ข้อมูลเท่าไหร่", ["data-analyst"]),
        ("full stack developer", ["fullstack-developer"]),
        ("full-stack ได้เท่าไหร่", ["fullstack-developer"]),
        ("machine learning engineer", ["ml-engineer"]),
        ("ML ได้เท่าไหร่", ["ml-engineer"]),
        ("devops กับ cloud engineer", ["devops-engineer", "cloud-engineer"]),
    ],
)
def test_a_role_is_found_in_the_message(message: str, expected: list[str]) -> None:
    assert find_roles(message, CATALOGUE) == expected


@pytest.mark.parametrize(
    "message",
    ["เงินเดือนเท่าไหร่", "ส่ง email ให้หน่อย", "engineer ได้เท่าไหร่", "data ได้เท่าไหร่"],
)
def test_no_clear_role_finds_nothing(message: str) -> None:
    assert find_roles(message, CATALOGUE) == []


def test_at_most_three_roles_are_found() -> None:
    message = "qa devops cloud frontend backend"
    assert len(find_roles(message, CATALOGUE)) == 3


# --- the salary text


def test_salary_gives_the_range_measure_source_and_date() -> None:
    answer = salary_answer(["qa-engineer"], SALARY, TITLES)
    assert "฿22,000 – ฿40,000 / เดือน (ฐานเงินเดือน)" in answer.text
    assert "ระดับเริ่มต้น" in answer.text
    assert "Jobsdb ไทย" in answer.text
    assert "8 มิ.ย. 2569" in answer.text
    assert "จัดทำโดยทีมผู้พัฒนา" in answer.text
    assert "[1]" in answer.text
    [source] = answer.sources
    assert source["n"] == 1
    assert source["evidence_id"] == "salary-qa-engineer"
    assert source["url"].startswith("https://th.jobsdb.com/")


def test_a_figure_from_a_related_role_says_so() -> None:
    proxy = next(row.role_id for row in SALARY.values() if row.match == "proxy")
    assert "ตำแหน่งใกล้เคียง" in salary_answer([proxy], SALARY, TITLES).text
    assert "ตำแหน่งใกล้เคียง" not in salary_answer(["qa-engineer"], SALARY, TITLES).text


def test_a_role_with_no_figure_says_so_and_invents_nothing() -> None:
    missing = next(role.role_id for role in CATALOGUE if role.role_id not in SALARY)
    answer = salary_answer([missing], SALARY, TITLES)
    assert "ยังไม่มีข้อมูลเงินเดือน" in answer.text
    assert "฿" not in answer.text
    assert answer.sources == []


# --- salary and market through the API


async def test_salary_needs_no_profile_and_no_llm(user: httpx.AsyncClient, groq: Groq) -> None:
    body = await _ask(user, "เงินเดือน QA เท่าไหร่")
    assert body["route"] == "salary"
    assert "฿22,000" in body["answer"]
    assert body["sources"][0]["evidence_id"] == "salary-qa-engineer"
    assert body["tokens_used"] == 0
    assert groq.requests == []


async def test_salary_with_no_role_and_no_profile_asks_which_role(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    body = await _ask(user, "เงินเดือนเท่าไหร่")
    assert body["route"] == "salary"
    assert "ตำแหน่งไหน" in body["answer"]
    assert body["sources"] == []
    assert groq.requests == []


async def test_salary_with_no_role_uses_the_best_match(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(user, "เงินเดือนเท่าไหร่")
    matches = (await user.get("/api/roles/matches")).json()
    top = matches["roles"][0]
    assert top["title_th"] in body["answer"]
    assert groq.requests == []


async def test_salary_with_no_role_prefers_the_role_the_user_wants(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    response = await user.put(
        "/api/questionnaire/answers/go_interested_roles", json={"value": ["qa-engineer"]}
    )
    assert response.status_code == 200, response.text
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    body = await _ask(user, "เงินเดือนเท่าไหร่")
    assert body["sources"][0]["evidence_id"] == "salary-qa-engineer"


async def _seed_market(container: Container, role_id: str = "qa-engineer", **cache: object) -> None:
    values: dict[str, object] = {
        "role_id": role_id,
        "fetched_at": utcnow(),
        "demand": {
            "posting_count": 4,
            "trending_skills": [
                {"skill_id": "sql", "name_th": "SQL", "count": 3},
                {"skill_id": "python", "name_th": "Python", "count": 2},
            ],
        },
        "salary_advertised": {
            "min_thb": 30000,
            "max_thb": 50000,
            "measure": "monthly_base",
            "source": "JobThai (ประกาศงาน)",
            "source_type": "advertised",
            "sample_size": 2,
            "as_of": "2026-11-03",
        },
    }
    async with container.sessions() as db:
        db.add(RoleCache(**{**values, **cache}))
        await db.commit()


async def test_market_with_no_data_says_so_and_makes_nothing_up(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    body = await _ask(user, "ตลาดงาน AI Engineer เป็นยังไง")
    assert body["route"] == "market"
    assert "ยังไม่มีข้อมูลประกาศงาน" in body["answer"]
    assert not any(character.isdigit() for character in body["answer"])
    assert body["sources"] == []
    assert body["tokens_used"] == 0
    assert groq.requests == []


async def test_market_gives_the_seeded_figures_with_their_source(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(container)
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert body["route"] == "market"
    assert "ข้อมูลกรุงเทพฯ" in body["answer"]
    assert "พบ 4 ประกาศ" in body["answer"]
    assert "SQL 3 ประกาศ, Python 2 ประกาศ" in body["answer"]
    assert "฿30,000 – ฿50,000 / เดือน (ฐานเงินเดือน) จาก 2 ประกาศ" in body["answer"]
    assert "[1]" in body["answer"]
    assert "ไม่ใช่จำนวนงานที่เปิดรับทั้งหมด" in body["answer"]
    assert DISCLAIMER_TH in body["answer"]
    assert "อาจไม่เป็นปัจจุบัน" not in body["answer"]
    [source] = body["sources"]
    assert source["n"] == 1
    assert source["evidence_id"] == "market-qa-engineer"
    assert source["label_th"].startswith("JobThai (ประกาศงาน)")
    assert body["tokens_used"] == 0
    assert groq.requests == []


async def test_market_with_no_fitting_postings_does_not_claim_there_is_no_demand(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(
        container, demand={"posting_count": 0, "trending_skills": []}, salary_advertised=None
    )
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert "รอบล่าสุดไม่พบประกาศที่ตรงกับตำแหน่งนี้" in body["answer"]
    assert "฿" not in body["answer"]
    assert "ทักษะ" not in body["answer"]


async def test_market_names_only_the_top_five_skills(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    skills = [
        {"skill_id": f"s{n}", "name_th": f"ทักษะแถว{chr(0x0E01 + n)}", "count": 9 - n}
        for n in range(6)
    ]
    await _seed_market(container, demand={"posting_count": 9, "trending_skills": skills})
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert skills[4]["name_th"] in body["answer"]
    assert skills[5]["name_th"] not in body["answer"]


async def test_market_with_no_advertised_salary_shows_no_figure(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(container, salary_advertised=None)
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert "พบ 4 ประกาศ" in body["answer"]
    assert "฿" not in body["answer"]


async def test_old_market_data_says_its_bangkok_date_and_may_be_out_of_date(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(container, fetched_at=datetime(2026, 1, 31, 18, 0, tzinfo=UTC))
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert "อัปเดตล่าสุด 1 ก.พ. 2569" in body["answer"]
    assert "อาจไม่เป็นปัจจุบัน" in body["answer"]


async def test_market_with_a_failed_refresh_may_be_out_of_date(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(container, last_error="timeout")
    body = await _ask(user, "ตลาดงาน QA เป็นยังไง")
    assert "พบ 4 ประกาศ" in body["answer"]
    assert "อาจไม่เป็นปัจจุบัน" in body["answer"]


async def test_market_answers_each_role_named_with_its_own_source(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_market(container, "devops-engineer")
    await _seed_market(container, "cloud-engineer")
    body = await _ask(user, "ตลาดงาน devops กับ cloud engineer เป็นยังไง")
    assert [s["evidence_id"] for s in body["sources"]] == [
        "market-devops-engineer",
        "market-cloud-engineer",
    ]
    assert body["answer"].count(DISCLAIMER_TH) == 1


async def test_market_with_no_role_and_no_profile_asks_which_role(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    body = await _ask(user, "ตลาดงานเป็นยังไงบ้าง")
    assert body["route"] == "market"
    assert "ตลาดงานของตำแหน่งไหน" in body["answer"]
    assert body["sources"] == []
    assert groq.requests == []


async def test_market_with_no_role_uses_the_best_match(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    top = (await user.get("/api/roles/matches")).json()["roles"][0]
    await _seed_market(container, top["role_id"])
    body = await _ask(user, "ตลาดงานเป็นยังไงบ้าง")
    assert body["sources"][0]["evidence_id"] == f"market-{top['role_id']}"
    assert groq.requests == []


# --- answers from the saved profile, no LLM


async def test_experience_cites_the_saved_summary_without_an_llm_call(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(user, "ประสบการณ์ของผมเป็นยังไง")
    assert body["route"] == "experience"
    assert "ฝึกงานที่ ABC 6 เดือน [1]" in body["answer"]
    assert "6 เดือน" in body["answer"]
    assert body["sources"][0]["evidence_id"] == "cv-5"
    assert body["sources"][0]["label_th"] == "CV บรรทัด 5"
    assert groq.requests == []


async def test_work_style_is_self_reported_with_the_disclaimer(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(user, "สไตล์การทำงานของผมเป็นยังไง")
    assert body["route"] == "work_style"
    assert "ไม่ใช่การวินิจฉัยบุคลิกภาพ" in body["answer"]
    assert groq.requests == []


# --- answers the LLM words


async def test_skill_assessment_cites_the_claims_that_hold_up(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": [GOOD_CLAIM]}, tokens=70)
    body = await _ask(user, "ทักษะของผมเป็นยังไง")
    assert body["route"] == "skill_assessment"
    assert body["answer"] == "- Python ของคุณอยู่ระดับ 3 [1]"
    assert body["sources"] == [{"n": 1, "evidence_id": "cv-2", "label_th": "CV บรรทัด 2"}]
    assert body["tokens_used"] == 70
    assert groq.requests[-1]["model"] == "main-model"


async def test_the_same_evidence_keeps_one_number(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": [GOOD_CLAIM, {"text_th": "ใช้ Python ได้ดี", "evidence_ids": ["cv-2"]}]})
    body = await _ask(user, "ทักษะของผมเป็นยังไง")
    assert body["answer"].count("[1]") == 2
    assert len(body["sources"]) == 1


async def test_only_the_needed_facts_go_to_the_llm(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": [GOOD_CLAIM]})
    await _ask(user, "ทักษะของผมเป็นยังไง")
    raw = groq.requests[-1]["messages"][1]["content"]
    sent = json.loads(raw)
    assert sent["question"] == "ทักษะของผมเป็นยังไง"
    names = " ".join(s["name"] for s in sent["facts"]["hard_skills"])
    assert all(skill in names for skill in ("Python", "SQL", "Docker"))
    for private in ("Somchai", "Intern at ABC", "BSc", "go_salary", "37500"):
        assert private not in raw


@pytest.mark.parametrize(
    "claim",
    [
        {"text_th": "เก่ง Python", "evidence_ids": ["made-up"]},
        {"text_th": "เก่ง Python", "evidence_ids": []},
        {"text_th": "ใช้ Python มา 99 ปี", "evidence_ids": ["cv-2"]},
        {"text_th": "เก่ง Kubernetes มาก", "evidence_ids": ["cv-2"]},
    ],
)
async def test_a_claim_that_does_not_hold_up_falls_back_to_the_facts(
    user: httpx.AsyncClient, groq: Groq, with_profile: None, claim: dict[str, Any]
) -> None:
    groq.reply({"claims": [claim]})
    body = await _ask(user, "ทักษะของผมเป็นยังไง")
    assert "Kubernetes" not in body["answer"]
    assert "99" not in body["answer"]
    assert "Python ระดับ 3 [" in body["answer"]
    assert {s["evidence_id"] for s in body["sources"]} >= {"cv-2", "cv-3", "cv-4"}


async def test_a_skill_named_only_in_the_question_cannot_enter_a_claim(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": [{"text_th": "คุณเก่ง Kubernetes", "evidence_ids": ["cv-2"]}]})
    body = await _ask(user, "ทักษะ Kubernetes ของผมเป็นยังไง")
    assert "Kubernetes" not in body["answer"]


async def test_blind_spots_use_the_gaps_of_the_top_roles(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": [{"text_th": "ยังขาดทักษะบางอย่าง", "evidence_ids": ["cv-4"]}]})
    body = await _ask(user, "จุดอ่อนของผมคืออะไร")
    assert body["route"] == "blind_spots"
    facts = _sent(groq)["facts"]
    assert facts["saved_blind_spots"][0]["evidence_ids"] == ["cv-4"]
    assert len(facts["top_roles"]) <= 3
    assert facts["top_roles"][0]["gaps"]
    assert "ยังขาดทักษะบางอย่าง [1]" in body["answer"]


async def test_blind_spots_fall_back_to_saved_text_and_computed_gaps(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": []})
    body = await _ask(user, "จุดอ่อนของผมคืออะไร")
    assert LLM_SECTIONS["blind_spots"][0]["text_th"] in body["answer"]
    assert "ยังขาด" in body["answer"]
    assert any(s["evidence_id"].startswith("role-") for s in body["sources"])


async def test_job_matching_percentages_come_from_scoring_not_the_llm(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    top = (await user.get("/api/roles/matches")).json()["roles"][0]
    groq.reply(
        {
            "claims": [
                {"text_th": "ตรงกับคุณถึง 99%", "evidence_ids": [f"role-{top['role_id']}"]},
                {"text_th": "มี Python ตรงกับงานนี้", "evidence_ids": ["cv-2"]},
            ]
        }
    )
    body = await _ask(user, "ผมควรเรียนอะไรต่อ")
    assert body["route"] == "job_matching"
    assert f"{top['title_th']} ตรง {top['match_pct']}%" in body["answer"]
    assert "99%" not in body["answer"]
    assert "มี Python ตรงกับงานนี้" in body["answer"]
    assert "ไม่ใช่การรับประกันการได้งาน" in body["answer"]
    assert top["gaps"][0]["name_th"] in body["answer"]
    role_source = next(s for s in body["sources"] if s["evidence_id"].startswith("role-"))
    assert role_source["url"].startswith("http")


async def test_job_matching_without_valid_claims_still_answers(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"claims": "not a list"})
    body = await _ask(user, "ผมควรเรียนอะไรต่อ")
    assert "%" in body["answer"]


# --- failures, quota, history


async def test_llm_failure_refunds_and_saves_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = (await user.get("/api/quota")).json()["requests_used"]
    groq.fail()
    # The edit step has nothing computed to fall back on; the answer routes do (test_chat_quality).
    response = await user.post("/api/chat", json={"message": "แก้ระดับ Python เป็น 4"})
    assert response.status_code == 503
    assert (await user.get("/api/quota")).json()["requests_used"] == before
    assert (await user.get("/api/chat/history")).json()["messages"] == []


async def test_answer_tokens_count_toward_the_quota(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = (await user.get("/api/quota")).json()["tokens_used"]
    groq.reply({"claims": [GOOD_CLAIM]}, tokens=70)
    await _ask(user, "ทักษะของผมเป็นยังไง")
    assert (await user.get("/api/quota")).json()["tokens_used"] == before + 70


async def test_history_keeps_the_sources(user: httpx.AsyncClient, groq: Groq) -> None:
    sent = await _ask(user, "เงินเดือน QA เท่าไหร่")
    [mine, reply] = (await user.get("/api/chat/history")).json()["messages"]
    assert mine["sources"] == []
    assert reply["sources"] == sent["sources"] != []


async def test_a_new_message_row_has_empty_sources(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ask(user, "งวดนี้หวยออกอะไร")
    async with container.sessions() as db:
        rows = list(await db.scalars(select(ChatMessage)))
    assert [row.sources for row in rows] == [[], []]


# --- found by testing the running system


@pytest.mark.parametrize(
    "message",
    ["what salary is required for a junior", "demand for quick learners"],
)
def test_a_role_name_is_not_found_inside_another_word(message: str) -> None:
    assert find_roles(message, CATALOGUE) == []


def test_a_longer_role_name_wins_over_the_shorter_one_inside_it() -> None:
    role_ids = find_roles("เงินเดือนผู้ดูแลระบบฐานข้อมูลเท่าไหร่", CATALOGUE)
    assert role_ids == ["database-administrator"]


async def test_a_job_not_in_the_catalogue_says_the_figure_is_for_another_role(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(user, "เงินเดือนหมอเท่าไหร่")
    assert body["route"] == "salary"
    assert body["answer"].startswith("ไม่พบสายงานที่ระบุในข้อความ")


# --- work style: Jev picks the one aspect a question is about


def _jev_says(
    container: Container, choice: str, confidence: float = 0.9, status: int = 200
) -> list[Any]:
    """The router's question gets "work_style"; the aspect question gets `choice`."""
    asked: list[Any] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        if "work_style" in sent["questions"]["route"]["criteria"]:
            answer = {"choice": "work_style", "confidence": 0.9}
            return httpx.Response(200, json={"answers": {"route": answer}})
        asked.append(sent)
        answer = {"choice": choice, "confidence": confidence}
        return httpx.Response(status, json={"answers": {"route": answer}})

    container.jev = JevClient(
        container.settings, container.sessions, transport=httpx.MockTransport(handler)
    )
    return asked


async def _answer_teamwork(user: httpx.AsyncClient, value: int) -> None:
    response = await user.put("/api/questionnaire/answers/ws_teamwork", json={"value": value})
    assert response.status_code == 200, response.text


async def _ask_work_style(user: httpx.AsyncClient, message: str) -> str:
    body = await _ask(user, message)
    assert body["route"] == "work_style"
    return str(body["answer"])


async def test_a_question_about_one_aspect_is_answered_about_that_aspect(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    await _answer_teamwork(user, 1)
    groq.reply(LLM_SECTIONS)
    assert (await user.post("/api/profile/generate")).status_code == 200
    groq.requests.clear()
    asked = _jev_says(container, "teamwork")
    text = await _ask_work_style(user, "ฉันเหมาะกับการทำงานแบบเดี่ยวหรือเป็นทีม")
    first = text.split("\n")[0]
    assert "การทำงานคนเดียวหรือกับทีม" in first
    assert "ทำงานคนเดียวเป็นหลัก" in first
    assert "(teamwork)" not in first
    assert "การทำงานคนเดียวหรือกับทีม (teamwork)" in text  # the teamwork note, cited
    assert "บทบาทในทีม" not in text  # no other aspect's note
    assert "ไม่ใช่การวินิจฉัยบุคลิกภาพ" in text
    assert asked[0]["state"] == {"question": "ฉันเหมาะกับการทำงานแบบเดี่ยวหรือเป็นทีม"}
    assert groq.requests == []


async def test_an_aspect_the_user_has_not_answered_says_so(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    _jev_says(container, "leadership")
    text = await _ask_work_style(user, "ฉันชอบนำทีมหรือชอบรับผิดชอบงานของตัวเอง")
    assert text.startswith("ด้านบทบาทในทีม: คุณยังไม่ได้ตอบคำถามด้านนี้ในแบบสอบถาม")
    assert "บทบาทในทีม (leadership)" in text


@pytest.mark.parametrize(
    ("choice", "confidence", "status"),
    [("overall", 0.9, 200), ("teamwork", 0.39, 200), ("teamwork", 0.9, 500)],
    ids=["overall", "unsure", "failed"],
)
async def test_otherwise_the_whole_work_style_is_shown(
    container: Container,
    user: httpx.AsyncClient,
    groq: Groq,
    with_profile: None,
    choice: str,
    confidence: float,
    status: int,
) -> None:
    _jev_says(container, choice, confidence, status)
    whole = await _ask_work_style(user, "สไตล์การทำงานของผมเป็นยังไง")
    container.jev = None
    assert whole == await _ask_work_style(user, "สไตล์การทำงานของผมเป็นยังไง")
