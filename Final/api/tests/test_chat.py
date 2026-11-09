"""POST /api/chat, history and the completeness meter (Contract.md §2.4, PRD FR-8, FR-9, FR-14)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import Container
from app.core.clock import utcnow
from app.domain.chat_facts import parse_facts
from app.domain.completeness import ChatInput, compute_completeness, next_slot, unrated_skills
from app.domain.matching.skills import load_taxonomy
from app.infra.jev import JevClient
from app.infra.llm import GroqClient
from app.infra.models import ChatMessage, CvDocument, Evidence, Fact, User
from tests.conftest import ClientFactory, assert_problem, register

TAXONOMY = load_taxonomy("../data")
NO_FACTS: dict[str, Any] = {}


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {
        "groq_api_key": "k",
        "groq_model": "main-model",
        "groq_router_model": "router-model",
        "groq_fallback_model": "router-model",
        "quota_daily_requests": 5,
        "quota_daily_tokens": 1000,
        "data_dir": "../data",
    }


class Groq:
    def __init__(self, container: Container) -> None:
        self.requests: list[dict[str, Any]] = []
        self.script: list[httpx.Response] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(request.content))
            return self.script.pop(0)

        async def no_wait(_seconds: float) -> None:
            return None

        container.llm = GroqClient(
            container.settings,
            container.sessions,
            transport=httpx.MockTransport(handler),
            sleep=no_wait,
        )

    def reply(self, facts: dict[str, Any], tokens: int = 50) -> None:
        self.script.append(
            httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(facts)}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": tokens - 10, "completion_tokens": 10},
                },
            )
        )


@pytest.fixture
def groq(container: Container) -> Groq:
    return Groq(container)


async def _facts(container: Container) -> list[Fact]:
    async with container.sessions() as db:
        return list(await db.scalars(select(Fact).order_by(Fact.id)))


async def _user_id(container: Container) -> str:
    async with container.sessions() as db:
        found = await db.scalar(select(User.id))
    assert found is not None
    return found


# --- a gap answer


async def test_answer_becomes_facts_and_the_next_question_follows(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(
        {
            "skills": [
                {"name": "Python", "level": 3},
                {"name": "SQL", "level": 2},
                {"name": "Docker", "level": 1},
            ]
        }
    )
    response = await user.post("/api/chat", json={"message": "Python 3, SQL 2, Docker 1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "gap_question"
    assert body["sources"] == []
    assert body["edit_proposal"] is None
    assert body["tokens_used"] == 50
    assert "ประสบการณ์" in body["answer"]  # hard skills are done; the other required slot is next
    hard = next(s for s in body["completeness"]["slots"] if s["slot"] == "hard_skills")
    assert hard["filled"] is True
    assert body["completeness"]["missing_required"] == ["experience"]
    [python, sql, docker] = await _facts(container)
    assert python.value == {"name": "Python", "skill_id": "python", "level": 3}
    assert (sql.kind, docker.kind) == ("skill", "skill")


async def test_a_fact_points_to_chat_evidence(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"skills": [{"name": "Python", "level": 3}]})
    await user.post("/api/chat", json={"message": "ผมใช้ Python ระดับ 3"})
    [fact] = await _facts(container)
    async with container.sessions() as db:
        evidence = await db.get(Evidence, fact.evidence_id)
        messages = list(await db.scalars(select(ChatMessage).order_by(ChatMessage.id)))
    assert evidence is not None
    assert (evidence.kind, evidence.excerpt) == ("chat", "ผมใช้ Python ระดับ 3")
    assert evidence.ref == messages[0].id


async def test_no_facts_asks_the_same_slot_again_without_thanks(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(NO_FACTS)
    body = (await user.post("/api/chat", json={"message": "สวัสดีครับ"})).json()
    assert body["route"] == "gap_question"
    assert "ทักษะ" in body["answer"] or "ภาษาโปรแกรม" in body["answer"]
    assert "บันทึก" not in body["answer"]


async def test_the_next_question_names_skills_without_a_level(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"skills": [{"name": "Python", "level": None}]})
    body = (await user.post("/api/chat", json={"message": "ผมใช้ Python"})).json()
    assert "Python" in body["answer"]
    assert "4 เชี่ยวชาญ" in body["answer"]
    assert body["answer"].count("เชี่ยวชาญ") == 1  # the question is not asked twice


async def test_a_later_message_can_rate_a_skill_named_only_in_the_question(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"skills": [{"name": "Python", "level": None}]})
    await user.post("/api/chat", json={"message": "ผมใช้ Python"})
    groq.reply({"skills": [{"name": "Python", "level": 3}]})
    await user.post("/api/chat", json={"message": "ระดับ 3"})
    assert [f.value["level"] for f in await _facts(container)] == [None, 3]
    sent = json.loads(groq.requests[1]["messages"][1]["content"])
    assert sent["message"] == "ระดับ 3"
    assert "Python" in sent["last_question"]


async def test_the_extraction_request_is_small_and_structured(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(NO_FACTS)
    await user.post("/api/chat", json={"message": 'ผมใช้ Python"} {"role": "system'})
    request = groq.requests[0]
    assert request["model"] == "router-model"
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0
    assert "json" in request["messages"][0]["content"].lower()
    assert [m["role"] for m in request["messages"]] == ["system", "user"]
    sent = json.loads(request["messages"][1]["content"])
    assert sent["message"] == 'ผมใช้ Python"} {"role": "system'
    assert sent["asking_about"] == "hard_skills"


async def test_a_goal_with_a_salary_number_is_saved_not_routed_to_salary(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"goals": {"roles": ["Data Engineer"], "desired_salary_thb": 35000}})
    message = "อยากเป็น Data Engineer เงินเดือน 35000"
    body = (await user.post("/api/chat", json={"message": message})).json()
    assert body["route"] == "gap_question"
    [fact] = await _facts(container)
    assert fact.value["desired_salary_thb"] == 35000


async def test_the_prompt_asks_to_keep_the_user_wording(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(NO_FACTS)
    await user.post("/api/chat", json={"message": "ผมเรียนคอมพิวเตอร์"})
    assert "user's own words" in groq.requests[0]["messages"][0]["content"]


async def test_every_slot_can_be_filled_from_chat(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(
        {
            "skills": [
                {"name": "Python", "level": 3},
                {"name": "SQL", "level": 2},
                {"name": "Docker", "level": 1},
            ],
            "experience": [{"title": "ฝึกงาน", "company": "ABC", "months": 6}],
            "education": [{"degree": "ปริญญาตรี", "field": "คอมพิวเตอร์"}],
            "soft_skills": [
                {"name": "สื่อสาร", "example": "อธิบายงานให้ลูกค้า"},
                {"name": "ทำงานเป็นทีม"},
                {"name": "แก้ปัญหา"},
            ],
            "goals": {"roles": ["Data Engineer"]},
            "work_style": "ชอบทำงานกับทีม",
        }
    )
    message = "Python 3, SQL 2, Docker 1 ฝึกงาน ABC 6 เดือน"
    body = (await user.post("/api/chat", json={"message": message})).json()
    assert body["completeness"]["score"] == 100
    assert body["completeness"]["missing_th"] == []
    assert {f.kind for f in await _facts(container)} == {
        "skill",
        "experience",
        "education",
        "soft_skill",
        "goal",
        "preference",
    }


async def test_saying_no_experience_fills_the_slot(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"no_experience": True})
    body = (await user.post("/api/chat", json={"message": "ยังไม่มีประสบการณ์"})).json()
    slot = next(s for s in body["completeness"]["slots"] if s["slot"] == "experience")
    assert slot["filled"] is True


# --- when everything is there


async def _confirmed_cv(container: Container, user_id: str) -> None:
    async with container.sessions() as db:
        db.add(
            CvDocument(
                user_id=user_id,
                filename="cv.pdf",
                text_lines=[],
                status="confirmed",
                confirmed_at=utcnow(),
                parsed={
                    "skills": [
                        {"skill_id": "python", "name": "Python", "level": 3},
                        {"skill_id": "sql", "name": "SQL", "level": 3},
                        {"skill_id": "docker", "name": "Docker", "level": None},
                    ],
                    "experience": [{"title": "Dev"}],
                    "education": [{"degree": "BSc"}],
                },
            )
        )
        await db.commit()


async def test_chat_rates_a_cv_skill_without_a_level(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _confirmed_cv(container, await _user_id(container))
    groq.reply(NO_FACTS)
    body = (await user.post("/api/chat", json={"message": "ผมเรียนคอมพิวเตอร์"})).json()
    assert "Docker" in body["answer"]
    assert body["completeness"]["can_generate"] is False
    groq.reply({"skills": [{"name": "Docker", "level": 2}], "goals": {"roles": ["QA"]}})
    body = (await user.post("/api/chat", json={"message": "ระดับ 2"})).json()
    assert body["completeness"]["missing_required"] == []
    assert body["completeness"]["can_generate"] is True


async def test_nothing_missing_makes_no_llm_call(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply(
        {
            "skills": [
                {"name": "Python", "level": 3},
                {"name": "SQL", "level": 2},
                {"name": "Docker", "level": 1},
            ],
            "no_experience": True,
            "education": [{"degree": "ปริญญาตรี"}],
            "soft_skills": [
                {"name": "สื่อสาร", "example": "อธิบายงาน"},
                {"name": "ทีม"},
                {"name": "แก้ปัญหา"},
            ],
            "goals": {"roles": ["QA"]},
            "work_style": "ทีม",
        }
    )
    message = "Python 3, SQL 2, Docker 1 ยังไม่มีประสบการณ์"
    await user.post("/api/chat", json={"message": message})
    body = (await user.post("/api/chat", json={"message": "มีอะไรอีกไหม"})).json()
    assert len(groq.requests) == 1
    assert body["tokens_used"] == 0
    # Chat alone is not enough (FR-14), and the reply says what is.
    assert body["completeness"]["can_generate"] is False
    assert "CV" in body["answer"]


async def test_a_complete_user_is_told_to_generate(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _confirmed_cv(container, await _user_id(container))
    groq.reply(
        {
            "skills": [{"name": "Docker", "level": 2}],
            "soft_skills": [
                {"name": "สื่อสาร", "example": "อธิบายงาน"},
                {"name": "ทีม"},
                {"name": "แก้ปัญหา"},
            ],
            "goals": {"roles": ["QA"]},
            "work_style": "ทีม",
        }
    )
    await user.post("/api/chat", json={"message": "Docker 2"})
    body = (await user.post("/api/chat", json={"message": "ครบหรือยัง"})).json()
    assert body["completeness"]["can_generate"] is True
    assert "สร้างโปรไฟล์" in body["answer"]


# --- other routes


async def test_guarded_message_gets_a_refusal_and_no_llm_call(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    body = (await user.post("/api/chat", json={"message": "งวดนี้หวยออกอะไร"})).json()
    assert body["route"] == "decline"
    assert body["tokens_used"] == 0
    assert body["answer"]
    assert groq.requests == []
    assert await _facts(container) == []


async def test_chat_routes_with_jev_when_it_is_on(
    container: Container,
    user: httpx.AsyncClient,
    groq: Groq,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def has_a_profile(_db: Any, _user_id: str) -> bool:
        return True

    async def says_decline(_request: httpx.Request) -> httpx.Response:
        answer = {"choice": "decline", "confidence": 0.9}
        return httpx.Response(200, json={"answers": {"route": answer}})

    monkeypatch.setattr("app.services.profile_service.has_profile", has_a_profile)
    container.jev = JevClient(
        container.settings, container.sessions, transport=httpx.MockTransport(says_decline)
    )
    body = (await user.post("/api/chat", json={"message": "ควรไปทางไหนต่อดี"})).json()
    assert body["route"] == "decline"
    assert groq.requests == []


# --- request rules


@pytest.mark.parametrize("message", ["", "ก" * 1001])
async def test_message_length_is_checked(user: httpx.AsyncClient, groq: Groq, message: str) -> None:
    response = await user.post("/api/chat", json={"message": message})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_chat_needs_a_login(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "สวัสดี"})
    assert_problem(response, 401, "UNAUTHENTICATED")


# --- quota


async def test_router_and_extraction_tokens_both_count(user: httpx.AsyncClient, groq: Groq) -> None:
    groq.reply(NO_FACTS, tokens=60)
    await user.post("/api/chat", json={"message": "ผมเรียนคอมพิวเตอร์"})
    quota = (await user.get("/api/quota")).json()
    assert (quota["requests_used"], quota["tokens_used"]) == (1, 60)


async def test_no_quota_left_is_refused_before_any_call(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    for _ in range(5):
        await user.post("/api/chat", json={"message": "งวดนี้หวยออกอะไร"})
    response = await user.post("/api/chat", json={"message": "สวัสดีครับ"})
    assert_problem(response, 429, "QUOTA_EXCEEDED")
    assert groq.requests == []


@pytest.mark.parametrize(
    ("reply", "status", "code"),
    [(401, 503, "LLM_UNAVAILABLE"), ("timeout", 504, "LLM_TIMEOUT")],
)
async def test_llm_failure_refunds_and_saves_nothing(
    container: Container, user: httpx.AsyncClient, reply: Any, status: int, code: str
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if reply == "timeout":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(reply)

    container.llm = GroqClient(
        container.settings, container.sessions, transport=httpx.MockTransport(handler)
    )
    response = await user.post("/api/chat", json={"message": "ผมเรียนคอมพิวเตอร์"})
    assert_problem(response, status, code)
    assert (await user.get("/api/quota")).json()["requests_used"] == 0
    assert (await user.get("/api/chat/history")).json()["messages"] == []
    assert await _facts(container) == []


# --- history


async def test_history_returns_both_sides_in_order(user: httpx.AsyncClient, groq: Groq) -> None:
    groq.reply(NO_FACTS)
    sent = (await user.post("/api/chat", json={"message": "สวัสดีครับ"})).json()
    [mine, reply] = (await user.get("/api/chat/history")).json()["messages"]
    assert (mine["role"], mine["text"]) == ("user", "สวัสดีครับ")
    assert mine["route"] is None
    assert (reply["role"], reply["text"]) == ("assistant", sent["answer"])
    assert reply["message_id"] == sent["message_id"]
    assert reply["route"] == "gap_question"
    assert reply["sources"] == []
    assert reply["created_at"].endswith("Z") or "+" in reply["created_at"]


async def test_history_pages_backwards(user: httpx.AsyncClient, groq: Groq) -> None:
    for _ in range(3):
        await user.post("/api/chat", json={"message": "งวดนี้หวยออกอะไร"})
    latest = (await user.get("/api/chat/history?limit=2")).json()["messages"]
    assert [m["role"] for m in latest] == ["user", "assistant"]
    older = (await user.get(f"/api/chat/history?limit=50&before={latest[0]['message_id']}")).json()[
        "messages"
    ]
    assert len(older) == 4
    assert older[-1]["message_id"] < latest[0]["message_id"]


@pytest.mark.parametrize("limit", [0, 101])
async def test_history_limit_is_checked(user: httpx.AsyncClient, limit: int) -> None:
    response = await user.get(f"/api/chat/history?limit={limit}")
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_history_is_private(client_factory: ClientFactory, groq: Groq) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="a@example.com")
    await register(second, email="b@example.com")
    await first.post("/api/chat", json={"message": "งวดนี้หวยออกอะไร"})
    assert (await second.get("/api/chat/history")).json()["messages"] == []


async def test_another_users_facts_do_not_fill_my_meter(
    client_factory: ClientFactory, groq: Groq
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="a@example.com")
    await register(second, email="b@example.com")
    groq.reply({"no_experience": True})
    await first.post("/api/chat", json={"message": "ยังไม่มีประสบการณ์"})
    assert (await first.get("/api/profile/completeness")).json()["score"] == 15
    assert (await second.get("/api/profile/completeness")).json()["score"] == 0


async def test_another_users_question_is_not_sent_for_me(
    client_factory: ClientFactory, groq: Groq
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="a@example.com")
    await register(second, email="b@example.com")
    groq.reply({"skills": [{"name": "Python", "level": None}]})
    await first.post("/api/chat", json={"message": "ผมใช้ Python"})
    groq.reply(NO_FACTS)
    await second.post("/api/chat", json={"message": "ผมเรียนคอมพิวเตอร์"})
    assert json.loads(groq.requests[1]["messages"][1]["content"])["last_question"] == ""


async def test_the_last_question_skips_other_routes(user: httpx.AsyncClient, groq: Groq) -> None:
    groq.reply({"skills": [{"name": "Python", "level": None}]})
    await user.post("/api/chat", json={"message": "ผมใช้ Python"})
    await user.post("/api/chat", json={"message": "งวดนี้หวยออกอะไร"})
    groq.reply(NO_FACTS)
    await user.post("/api/chat", json={"message": "ระดับ 3"})
    assert "Python" in json.loads(groq.requests[1]["messages"][1]["content"])["last_question"]


async def test_deleting_the_account_removes_chat_data(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({"skills": [{"name": "Python", "level": 3}]})
    await user.post("/api/chat", json={"message": "Python 3"})
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text
    async with container.sessions() as db:
        for table in (ChatMessage, Fact, Evidence):
            assert list(await db.scalars(select(table))) == []


async def test_message_text_is_not_in_the_request_log(
    container: Container, user: httpx.AsyncClient, groq: Groq, capsys: pytest.CaptureFixture[str]
) -> None:
    groq.reply(NO_FACTS)
    await user.post("/api/chat", json={"message": "ข้อความลับมาก"})
    captured = capsys.readouterr()
    assert "ข้อความลับมาก" not in captured.out + captured.err


# --- GET /api/profile/completeness


async def test_completeness_endpoint_includes_chat_facts(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    empty = (await user.get("/api/profile/completeness")).json()
    assert empty["score"] == 0
    assert empty["inputs"]["chat"] == "needed"
    groq.reply({"no_experience": True})
    await user.post("/api/chat", json={"message": "ยังไม่มีประสบการณ์"})
    after = (await user.get("/api/profile/completeness")).json()
    assert after["score"] == 15


async def test_completeness_needs_a_login(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/profile/completeness")
    assert_problem(response, 401, "UNAUTHENTICATED")


# --- checking what the LLM extracted


def _parse(data: dict[str, Any], message: str = "Python SQL", question: str = "") -> list[Any]:
    return parse_facts(data, message=message, last_question=question, taxonomy=TAXONOMY)


def test_a_skill_the_user_did_not_mention_is_dropped() -> None:
    assert _parse({"skills": [{"name": "Kubernetes", "level": 4}]}) == []


def test_a_skill_from_the_last_question_is_kept() -> None:
    [fact] = _parse(
        {"skills": [{"name": "Docker", "level": 2}]}, message="ระดับ 2", question="Docker ระดับไหน"
    )
    assert fact.value["skill_id"] == "docker"


def test_a_skill_outside_the_taxonomy_keeps_its_name() -> None:
    [fact] = _parse({"skills": [{"name": "Zig99", "level": 2}]}, message="ผมใช้ Zig99 ระดับ 2")
    assert fact.value == {"name": "Zig99", "skill_id": None, "level": 2}


@pytest.mark.parametrize("level", [0, 5, "3", True, 2.5])
def test_a_bad_level_becomes_no_level(level: Any) -> None:
    [fact] = _parse({"skills": [{"name": "Python", "level": level}]})
    assert fact.value["level"] is None


@pytest.mark.parametrize(
    "message",
    [
        "ฝึกงาน 6 เดือน ทำ Python",  # the model made up a level
        "เขียน Python ได้นิดหน่อย",  # not a level the user chose
        "ใช้ Python ตั้งแต่ปี 2023",  # part of a longer number
    ],
)
def test_a_level_the_user_did_not_give_is_dropped(message: str) -> None:
    [fact] = _parse({"skills": [{"name": "Python", "level": 2}]}, message=message)
    assert fact.value["level"] is None


def test_a_number_outside_the_levels_is_not_a_level() -> None:
    [fact] = _parse({"skills": [{"name": "Python", "level": 5}]}, message="Python ระดับ 5")
    assert fact.value["level"] is None


def test_a_level_the_user_gave_is_kept() -> None:
    [fact] = _parse({"skills": [{"name": "Python", "level": 2}]}, message="Python ระดับ 2")
    assert fact.value["level"] == 2


def test_a_soft_skill_from_the_taxonomy_is_not_a_hard_skill() -> None:
    soft = next(s for s in TAXONOMY._skills.values() if s.type == "soft")
    [fact] = _parse({"skills": [{"name": soft.name_en, "level": 2}]}, message=soft.name_en)
    assert fact.kind == "soft_skill"


@pytest.mark.parametrize(
    "data",
    [
        {"skills": "Python"},
        {"skills": ["Python"]},
        {"skills": [{"level": 3}]},
        {"skills": [{"name": 5}]},
        {"experience": [{"company": "ABC"}]},
        {"experience": "ฝึกงาน"},
        {"education": [{"field": ""}]},
        {"soft_skills": [{"name": ""}]},
        {"goals": "QA"},
        {"goals": {"roles": [5], "desired_salary_thb": -1, "locations": "BKK"}},
        {"goals": {}},
        {"work_style": 5},
        {"work_style": "  "},
        {"no_experience": "true"},
        {"no_experience": False},
    ],
)
def test_broken_shapes_are_ignored(data: dict[str, Any]) -> None:
    assert _parse(data) == []


def test_experience_entries_win_over_no_experience() -> None:
    facts = _parse({"experience": [{"title": "ฝึกงาน"}], "no_experience": True})
    assert [f.value.get("none") for f in facts] == [None]


def test_experience_months_are_checked() -> None:
    [fact] = _parse({"experience": [{"title": "ฝึกงาน", "months": -3}]})
    assert fact.value["months"] is None


@pytest.mark.parametrize("months", [True, "6", 2.5])
def test_months_must_be_a_whole_number(months: Any) -> None:
    [fact] = _parse({"experience": [{"title": "ฝึกงาน", "months": months}]})
    assert fact.value["months"] is None


def test_long_text_is_cut() -> None:
    [fact] = _parse({"work_style": "ก" * 500})
    assert len(fact.value["text"]) == 200


def test_too_many_items_are_cut() -> None:
    facts = _parse({"experience": [{"title": f"t{i}"} for i in range(50)]})
    assert len(facts) == 10


# --- the meter with chat input


def _meter(chat: ChatInput) -> dict[str, Any]:
    return compute_completeness(cv=None, chat=chat, threshold=65)


def _filled(meter: dict[str, Any], slot: str) -> bool:
    return next(s for s in meter["slots"] if s["slot"] == slot)["filled"]


def test_soft_skills_need_three_and_one_example() -> None:
    three = [{"name": n} for n in "abc"]
    assert not _filled(_meter(ChatInput(soft_skills=three)), "soft_skills")
    with_example = [{"name": "a", "example": "x"}, *three[1:]]
    assert _filled(_meter(ChatInput(soft_skills=with_example)), "soft_skills")
    assert not _filled(_meter(ChatInput(soft_skills=with_example[:2])), "soft_skills")


def test_a_later_mention_without_a_level_keeps_the_rating() -> None:
    skills = [
        {"name": "Python", "skill_id": "python", "level": 3},
        {"name": "Python", "skill_id": "python", "level": None},
        {"name": "SQL", "skill_id": "sql", "level": 2},
        {"name": "Docker", "skill_id": "docker", "level": 2},
    ]
    assert _filled(_meter(ChatInput(skills=skills)), "hard_skills")
    assert unrated_skills(cv=None, questionnaire=None, chat=ChatInput(skills=skills)) == []


def test_the_same_skill_twice_counts_once() -> None:
    skills = [{"name": "Python", "skill_id": "python", "level": n} for n in (1, 2, 3)]
    assert not _filled(_meter(ChatInput(skills=skills)), "hard_skills")


def test_next_slot_is_required_first_then_by_points() -> None:
    assert next_slot(_meter(ChatInput())) == "hard_skills"
    skills = [{"name": n, "skill_id": n, "level": 2} for n in "abc"]
    assert next_slot(_meter(ChatInput(skills=skills))) == "experience"
    done = ChatInput(skills=skills, no_experience=True)
    assert next_slot(_meter(done)) == "soft_skills"


def test_chat_alone_cannot_generate() -> None:
    skills = [{"name": n, "skill_id": n, "level": 2} for n in "abc"]
    meter = _meter(ChatInput(skills=skills, no_experience=True, goals=True, education=True))
    assert meter["missing_required"] == []
    assert meter["score"] >= 65
    assert meter["can_generate"] is False
