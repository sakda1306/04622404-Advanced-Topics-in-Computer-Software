"""POST /api/profile/generate and GET /api/profile (Contract.md §2.5, PRD FR-14 – FR-17)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import Container
from app.core.clock import utcnow
from app.domain.matching.skills import load_taxonomy
from app.domain.profile import ChatRow, build_draft, facts_as_text, parse_claims
from app.domain.questionnaire import Questionnaire, load_questionnaire
from app.infra.llm import GroqClient
from app.infra.models import CvDocument, Evidence, Fact, Profile, RemovedSkill, User
from app.services import profile_service
from app.services.profile_service import load_roles
from tests.conftest import ClientFactory, assert_problem, register

TAXONOMY = load_taxonomy("../data")
QUESTIONNAIRE = load_questionnaire("../data")
ROLES = load_roles("../data")
CV_LINES = ["Somchai", "Python 3 years", "SQL", "Docker", "Intern at ABC", "BSc Computer"]
CV_PARSED: dict[str, Any] = {
    "skills": [
        {"name": "Python", "skill_id": "python", "level": 3, "line_no": 2},
        {"name": "SQL", "skill_id": "sql", "level": 2, "line_no": 3},
        {"name": "Docker", "skill_id": "docker", "level": 1, "line_no": 4},
    ],
    "experience": [{"title": "Intern", "company": "ABC", "months": 6, "line_no": 5}],
    "education": [{"school": "KU", "degree": "BSc", "line_no": 6}],
    "warnings_th": [],
}
LLM_SECTIONS: dict[str, Any] = {
    "experience_summary": [{"text_th": "ฝึกงานที่ ABC 6 เดือน", "evidence_ids": ["cv-5"]}],
    "blind_spots": [{"text_th": "ทักษะ Docker ยังอยู่ระดับพื้นฐาน", "evidence_ids": ["cv-4"]}],
}


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
            # Unscripted calls fail, so a test only scripts the calls it is about.
            return self.script.pop(0) if self.script else httpx.Response(500, json={})

        async def no_wait(_seconds: float) -> None:
            return None

        container.llm = GroqClient(
            container.settings,
            container.sessions,
            transport=httpx.MockTransport(handler),
            sleep=no_wait,
        )

    def reply(self, sections: dict[str, Any], tokens: int = 100) -> None:
        self.script.append(
            httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(sections)}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": tokens - 10, "completion_tokens": 10},
                },
            )
        )

    def fail(self) -> None:
        self.script.extend(httpx.Response(500, json={}) for _ in range(3))


@pytest.fixture
def groq(container: Container) -> Groq:
    return Groq(container)


async def _user_id(container: Container, email: str = "user@example.com") -> str:
    async with container.sessions() as db:
        found = await db.scalar(select(User.id).where(User.email == email))
    assert found is not None
    return found


async def _seed_cv(
    container: Container, *, email: str = "user@example.com", status: str = "confirmed"
) -> None:
    user_id = await _user_id(container, email)
    async with container.sessions() as db:
        db.add(
            CvDocument(
                user_id=user_id,
                filename="cv.pdf",
                text_lines=CV_LINES,
                status=status,
                confirmed_at=utcnow(),
                parsed=CV_PARSED,
            )
        )
        await db.commit()


async def _ready(container: Container, client: httpx.AsyncClient) -> None:
    await _seed_cv(container)
    answer = {"value": "30k_45k"}
    response = await client.put("/api/questionnaire/answers/go_salary", json=answer)
    assert response.status_code == 200, response.text


def _draft(
    *,
    parsed: dict[str, Any] | None = None,
    lines: list[str] | None = None,
    answers: dict[str, Any] | None = None,
    chat: list[ChatRow] | None = None,
) -> Any:
    return build_draft(
        cv=parsed,
        cv_lines=lines if lines is not None else [],
        answers=answers or {},
        chat=chat or [],
        questionnaire=QUESTIONNAIRE,
        taxonomy=TAXONOMY,
        roles=ROLES,
    )


def _chat(kind: str, value: dict[str, Any], evidence_id: str = "e1") -> ChatRow:
    return ChatRow(kind=kind, value=value, evidence_id=evidence_id, excerpt="ข้อความ")


def _skill(skills: list[dict[str, Any]], skill_id: str) -> dict[str, Any]:
    return next(s for s in skills if s["skill_id"] == skill_id)


# --- hard skills


def test_cv_skills_cite_their_line() -> None:
    draft = _draft(parsed=CV_PARSED, lines=CV_LINES)
    python = _skill(draft.hard_skills, "python")
    assert python["level"] == 3
    assert python["kind"] == "hard"
    assert python["edited_by_user"] is False
    assert python["evidence_ids"] == ["cv-2"]
    assert draft.evidence["cv-2"] == {
        "id": "cv-2",
        "kind": "cv_line",
        "label_th": "CV บรรทัด 2",
        "excerpt": "Python 3 years",
    }


def test_taxonomy_names_are_used() -> None:
    python = _skill(_draft(parsed=CV_PARSED, lines=CV_LINES).hard_skills, "python")
    known = TAXONOMY.get("python")
    assert known is not None
    assert (python["name_th"], python["name_en"]) == (known.name_th, known.name_en)


@pytest.mark.parametrize("line_no", [0, 99])
def test_a_skill_without_a_real_line_cites_the_confirmed_cv(line_no: int) -> None:
    parsed = {
        **CV_PARSED,
        "skills": [{"name": "Go", "skill_id": "go", "level": 2, "line_no": line_no}],
    }
    draft = _draft(parsed=parsed, lines=CV_LINES)
    [skill] = draft.hard_skills
    [evidence_id] = skill["evidence_ids"]
    assert draft.evidence[evidence_id]["kind"] == "cv_line"
    assert draft.evidence[evidence_id]["label_th"] == "CV ที่คุณยืนยัน"
    assert draft.evidence[evidence_id]["excerpt"] == "Go"


def test_the_same_skill_from_three_sources_is_one_skill_citing_all() -> None:
    draft = _draft(
        parsed=CV_PARSED,
        lines=CV_LINES,
        answers={"sk_tech_stack": [{"skill_id": "python", "level": 2}]},
        chat=[_chat("skill", {"name": "Python", "skill_id": "python", "level": 4})],
    )
    python = _skill(draft.hard_skills, "python")
    assert python["evidence_ids"] == ["cv-2", "answer-sk_tech_stack", "e1"]
    assert sum(s["skill_id"] == "python" for s in draft.hard_skills) == 1


def test_the_questionnaire_rating_beats_the_cv_rule() -> None:
    draft = _draft(
        parsed=CV_PARSED,
        lines=CV_LINES,
        answers={"sk_tech_stack": [{"skill_id": "python", "level": 2}]},
    )
    assert _skill(draft.hard_skills, "python")["level"] == 2


def test_the_latest_chat_level_wins() -> None:
    draft = _draft(
        chat=[
            _chat("skill", {"name": "Python", "skill_id": "python", "level": 2}),
            _chat("skill", {"name": "Python", "skill_id": "python", "level": 4}),
        ],
    )
    assert _skill(draft.hard_skills, "python")["level"] == 4


def test_a_later_mention_without_a_level_keeps_the_level() -> None:
    draft = _draft(
        chat=[
            _chat("skill", {"name": "Python", "skill_id": "python", "level": 3}),
            _chat("skill", {"name": "Python", "skill_id": "python", "level": None}, "e2"),
        ],
    )
    python = _skill(draft.hard_skills, "python")
    assert python["level"] == 3
    assert python["evidence_ids"] == ["e1", "e2"]


def test_one_message_naming_a_skill_twice_cites_it_once() -> None:
    fact = _chat("skill", {"name": "Python", "skill_id": "python", "level": 3})
    assert _skill(_draft(chat=[fact, fact]).hard_skills, "python")["evidence_ids"] == ["e1"]


def test_a_skill_with_no_level_anywhere_is_basic() -> None:
    draft = _draft(chat=[_chat("skill", {"name": "Python", "skill_id": "python", "level": None})])
    assert _skill(draft.hard_skills, "python")["level"] == 1


def test_a_skill_outside_the_taxonomy_keeps_the_users_words() -> None:
    draft = _draft(chat=[_chat("skill", {"name": "Zig/99", "skill_id": None, "level": 2})])
    [skill] = draft.hard_skills
    assert skill["name_th"] == skill["name_en"] == "Zig/99"
    assert skill["skill_id"].startswith("custom-")
    assert "/" not in skill["skill_id"]  # DELETE /api/profile/skills/{skill_id}


def test_free_text_spelled_differently_is_one_custom_skill() -> None:
    draft = _draft(
        chat=[
            _chat("skill", {"name": "Zig", "skill_id": None, "level": 2}),
            _chat("skill", {"name": "ZIG", "skill_id": None, "level": None}),
        ],
    )
    assert len(draft.hard_skills) == 1


def test_a_soft_skill_id_in_the_cv_goes_to_soft_skills() -> None:
    parsed = {
        **CV_PARSED,
        "skills": [{"name": "Teamwork", "skill_id": "teamwork", "level": None, "line_no": 2}],
    }
    draft = _draft(parsed=parsed, lines=CV_LINES)
    assert draft.hard_skills == []
    assert _skill(draft.soft_skills, "teamwork")["kind"] == "soft"


# --- soft skills


@pytest.mark.parametrize(("answer", "level"), [(4, 3), (5, 4)])
def test_a_high_self_rating_adds_the_soft_skill(answer: int, level: int) -> None:
    draft = _draft(answers={"ss_communication": answer})
    skill = _skill(draft.soft_skills, "communication")
    assert skill["level"] == level
    assert skill["evidence_ids"] == ["answer-ss_communication"]
    assert draft.evidence["answer-ss_communication"]["kind"] == "answer"
    assert draft.evidence["answer-ss_communication"]["label_th"].startswith("แบบสอบถามข้อ ")


def test_a_low_self_rating_adds_nothing() -> None:
    assert _draft(answers={"ss_communication": 3}).soft_skills == []


def test_a_chat_soft_skill_maps_to_the_taxonomy() -> None:
    fact = _chat("soft_skill", {"name": "Communication", "example": "อธิบายให้ลูกค้าฟัง"})
    skill = _skill(_draft(chat=[fact]).soft_skills, "communication")
    assert skill["level"] == 2
    assert skill["evidence_ids"] == ["e1"]


def test_a_chat_soft_skill_outside_the_taxonomy_is_kept() -> None:
    fact = _chat("soft_skill", {"name": "การอธิบายระบบ", "example": None})
    [skill] = _draft(chat=[fact]).soft_skills
    assert skill["name_th"] == "การอธิบายระบบ"


# --- work style


def test_work_style_comes_from_the_scale_answers() -> None:
    draft = _draft(answers={"ws_teamwork": 5, "ws_structure": 1, "ws_ambiguity": 3})
    traits = {t["trait"]: t for t in draft.work_style["traits"]}
    assert set(traits) == {"teamwork", "structure", "ambiguity"}
    assert traits["teamwork"]["value"] == 1.0
    assert traits["structure"]["value"] == 0.0
    assert traits["ambiguity"]["value"] == 0.5
    scale = QUESTIONNAIRE.question("ws_teamwork")["scale"]  # type: ignore[index]
    assert traits["teamwork"]["label_th"] == scale["max_label_th"]
    low = QUESTIONNAIRE.question("ws_structure")["scale"]  # type: ignore[index]
    assert traits["structure"]["label_th"] == low["min_label_th"]
    assert "กึ่งกลาง" in traits["ambiguity"]["label_th"]
    assert draft.preferences["work_style"] == {"teamwork": 1.0, "structure": 0.0, "ambiguity": 0.5}


@pytest.mark.parametrize(("answer", "key"), [(2, "min_label_th"), (4, "max_label_th")])
def test_a_near_end_answer_is_not_stated_as_the_extreme(answer: int, key: str) -> None:
    [trait] = _draft(answers={"ws_teamwork": answer}).work_style["traits"]
    question = QUESTIONNAIRE.question("ws_teamwork")
    assert question is not None
    assert trait["label_th"] == f"ค่อนไปทาง “{question['scale'][key]}”"


def test_soft_skill_scales_are_not_work_style_traits() -> None:
    assert _draft(answers={"ss_communication": 5}).work_style["traits"] == []


def test_work_style_is_shown_as_self_reported() -> None:
    work_style = _draft(answers={"ws_teamwork": 5}).work_style
    assert work_style["disclaimer_th"] == "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ"
    assert "คุณระบุว่า" in work_style["summary_th"]


def test_work_style_from_chat_is_quoted_in_the_summary() -> None:
    draft = _draft(chat=[_chat("preference", {"text": "ชอบทำงานเป็นทีม"})])
    assert "ชอบทำงานเป็นทีม" in draft.work_style["summary_th"]
    assert draft.work_style["traits"] == []


def test_no_work_style_says_so() -> None:
    assert "ยังไม่ได้ระบุ" in _draft().work_style["summary_th"]


# --- experience


def test_total_months_adds_up_cv_and_chat() -> None:
    fact = _chat("experience", {"title": "Dev", "company": "XYZ", "months": 12})
    assert _draft(parsed=CV_PARSED, lines=CV_LINES, chat=[fact]).total_months == 18


def test_the_same_job_told_twice_counts_once() -> None:
    fact = _chat("experience", {"title": "intern", "company": "abc", "months": 6})
    draft = _draft(parsed=CV_PARSED, lines=CV_LINES, chat=[fact])
    assert draft.total_months == 6
    assert len(draft.fallback_experience) == 1
    assert draft.fallback_experience[0]["evidence_ids"] == ["cv-5", "e1"]


def test_the_same_title_at_two_companies_is_two_jobs() -> None:
    draft = _draft(
        chat=[
            _chat("experience", {"title": "Dev", "company": "A", "months": 6}),
            _chat("experience", {"title": "Dev", "company": "B", "months": 12}),
        ]
    )
    assert draft.total_months == 18
    assert len(draft.fallback_experience) == 2


def test_an_entry_beats_the_questionnaire_range_in_the_fallback() -> None:
    draft = _draft(parsed=CV_PARSED, lines=CV_LINES, answers={"ex_it_experience": "1_3y"})
    assert [c["evidence_ids"] for c in draft.fallback_experience] == [["cv-5"]]


def test_an_entry_without_months_adds_nothing() -> None:
    fact = _chat("experience", {"title": "Dev", "company": None, "months": None})
    assert _draft(chat=[fact]).total_months == 0


@pytest.mark.parametrize(
    ("answer", "months"), [("none", 0), ("projects", 0), ("lt_1y", 0), ("1_3y", 12), ("gt_3y", 36)]
)
def test_the_questionnaire_range_gives_the_floor(answer: str, months: int) -> None:
    assert _draft(answers={"ex_it_experience": answer}).total_months == months


def test_stated_months_beat_a_lower_floor() -> None:
    draft = _draft(parsed=CV_PARSED, lines=CV_LINES, answers={"ex_it_experience": "gt_3y"})
    assert draft.total_months == 36
    fact = _chat("experience", {"title": "Dev", "company": None, "months": 48})
    assert _draft(answers={"ex_it_experience": "gt_3y"}, chat=[fact]).total_months == 48


def test_fallback_claim_for_an_entry() -> None:
    [claim] = _draft(parsed=CV_PARSED, lines=CV_LINES).fallback_experience
    assert claim == {
        "text_th": "Intern ที่ ABC (6 เดือน)",
        "evidence_ids": ["cv-5"],
        "edited_by_user": False,
    }


def test_fallback_claim_from_the_questionnaire() -> None:
    [claim] = _draft(answers={"ex_it_experience": "1_3y"}).fallback_experience
    assert claim["evidence_ids"] == ["answer-ex_it_experience"]
    assert "ประสบการณ์" in claim["text_th"]


def test_an_experience_names_the_skills_said_in_the_same_message() -> None:
    draft = _draft(
        chat=[
            _chat("skill", {"name": "Python", "skill_id": "python", "level": None}, "e1"),
            _chat("skill", {"name": "SQL", "skill_id": "sql", "level": None}, "e2"),
            _chat("experience", {"title": "ระบบจองห้องเรียน", "company": None, "months": 6}, "e1"),
        ]
    )
    assert draft.llm_facts["experience"][0]["skills_used"] == ["Python"]


def test_an_experience_never_names_a_removed_skill() -> None:
    draft = build_draft(
        cv=None,
        cv_lines=[],
        answers={},
        chat=[
            _chat("skill", {"name": "Python", "skill_id": "python", "level": None}, "e1"),
            _chat("experience", {"title": "ระบบจองห้องเรียน", "company": None, "months": 6}, "e1"),
        ],
        questionnaire=QUESTIONNAIRE,
        taxonomy=TAXONOMY,
        roles=ROLES,
        removed=frozenset({"python"}),
    )
    assert draft.llm_facts["experience"][0]["skills_used"] == []


def test_fallback_claim_for_no_experience_from_chat() -> None:
    [claim] = _draft(chat=[_chat("experience", {"none": True})]).fallback_experience
    assert claim["evidence_ids"] == ["e1"]
    assert "ยังไม่มีประสบการณ์" in claim["text_th"]


def test_a_real_job_beats_no_experience() -> None:
    draft = _draft(parsed=CV_PARSED, lines=CV_LINES, chat=[_chat("experience", {"none": True})])
    assert [c["evidence_ids"] for c in draft.fallback_experience] == [["cv-5"]]


# --- preferences


def test_preferences_from_the_questionnaire() -> None:
    draft = _draft(
        answers={
            "go_interested_roles": ["web-developer"],
            "go_salary": "30k_45k",
            "go_location": "bangkok",
        }
    )
    assert draft.preferences["interested_roles"] == ["web-developer"]
    assert draft.preferences["desired_salary_thb"] == 37500
    question = QUESTIONNAIRE.question("go_location")
    assert question is not None
    bangkok = next(o for o in question["options"] if o["value"] == "bangkok")
    assert draft.preferences["locations"] == [bangkok["label_th"]]


def test_unsure_salary_is_left_out() -> None:
    assert "desired_salary_thb" not in _draft(answers={"go_salary": "unsure"}).preferences


def test_chat_goals_beat_the_questionnaire_salary_and_add_to_the_rest() -> None:
    draft = _draft(
        answers={"go_salary": "20k_30k", "go_interested_roles": ["web-developer"]},
        chat=[
            _chat(
                "goal",
                {
                    "roles": ["Software Engineer"],
                    "locations": ["เชียงใหม่"],
                    "desired_salary_thb": 35000,
                },
            )
        ],
    )
    assert draft.preferences["desired_salary_thb"] == 35000
    assert draft.preferences["interested_roles"] == ["web-developer", "software-engineer"]
    assert "เชียงใหม่" in draft.preferences["locations"]


@pytest.mark.parametrize("text", ["นักทำอาหาร", "e"])
def test_a_role_not_in_the_list_is_left_out(text: str) -> None:
    fact = _chat("goal", {"roles": [text], "locations": [], "desired_salary_thb": None})
    assert _draft(chat=[fact]).preferences["interested_roles"] == []


def test_a_word_shared_by_many_roles_names_no_role() -> None:
    fact = _chat("goal", {"roles": ["engineer"], "locations": [], "desired_salary_thb": None})
    assert _draft(chat=[fact]).preferences["interested_roles"] == []


def test_a_short_role_name_matching_one_role_is_accepted() -> None:
    fact = _chat("goal", {"roles": ["Web Dev"], "locations": [], "desired_salary_thb": None})
    assert _draft(chat=[fact]).preferences["interested_roles"] == ["web-developer"]


def test_an_answer_to_a_question_no_longer_in_the_file_is_ignored() -> None:
    def read(name: str) -> Any:
        return json.loads((Path("../data") / name).read_text(encoding="utf-8"))

    raw = read("questionnaire.json")
    for section in raw["sections"]:
        section["questions"] = [
            q for q in section["questions"] if q["question_id"] != "ex_it_experience"
        ]
    questionnaire = Questionnaire(raw, read("skills.json"), read("roles.json"))
    draft = build_draft(
        cv=None,
        cv_lines=[],
        answers={"ex_it_experience": "gt_3y"},
        chat=[],
        questionnaire=questionnaire,
        taxonomy=TAXONOMY,
        roles=ROLES,
    )
    assert draft.total_months == 0
    assert draft.evidence == {}


# --- what the LLM sees


def test_llm_facts_carry_evidence_ids_and_keep_excerpts_short() -> None:
    long_line = "Python " + "x" * 500
    parsed = {
        **CV_PARSED,
        "skills": [{"name": "Python", "skill_id": "python", "level": 3, "line_no": 1}],
    }
    draft = _draft(parsed=parsed, lines=[long_line])
    assert len(draft.evidence["cv-1"]["excerpt"]) <= 200
    assert draft.llm_facts["hard_skills"][0]["evidence_ids"] == ["cv-1"]
    assert draft.llm_facts["hard_skills"][0]["level"] == 3


def test_llm_facts_include_education_and_the_example_answer() -> None:
    draft = _draft(
        parsed=CV_PARSED,
        lines=CV_LINES,
        answers={"ss_example": "แก้บั๊กกับทีม", "ed_level": "bachelor"},
    )
    assert draft.llm_facts["education"][0]["evidence_ids"] == ["cv-6"]
    assert draft.llm_facts["education"][1]["evidence_ids"] == ["answer-ed_level"]
    assert draft.llm_facts["examples"] == [
        {"text": "แก้บั๊กกับทีม", "evidence_ids": ["answer-ss_example"]}
    ]


def test_llm_facts_are_capped() -> None:
    skills = [{"name": f"T{i}", "skill_id": None, "level": 1, "line_no": 0} for i in range(60)]
    assert (
        len(_draft(parsed={**CV_PARSED, "skills": skills}, lines=[]).llm_facts["hard_skills"]) == 30
    )


# --- checking what the LLM wrote


def _claims(items: Any, *, names_skills: bool = False) -> list[dict[str, Any]]:
    return parse_claims(
        items,
        evidence={"cv-1", "cv-2"},
        facts_text="Python 6 เดือน",
        taxonomy=TAXONOMY,
        own_skills={"python"} if names_skills else None,
    )


def test_a_good_claim_is_kept() -> None:
    assert _claims([{"text_th": "ใช้ Python", "evidence_ids": ["cv-1"]}]) == [
        {"text_th": "ใช้ Python", "evidence_ids": ["cv-1"], "edited_by_user": False}
    ]


@pytest.mark.parametrize(
    "item",
    [
        {"text_th": "x", "evidence_ids": ["made-up"]},
        {"text_th": "x", "evidence_ids": []},
        {"text_th": "x"},
        {"text_th": "x", "evidence_ids": "cv-1"},
        {"text_th": "", "evidence_ids": ["cv-1"]},
        {"text_th": "   ", "evidence_ids": ["cv-1"]},
        {"text_th": 5, "evidence_ids": ["cv-1"]},
        {"evidence_ids": ["cv-1"]},
        "ข้อความ",
        None,
    ],
)
def test_a_claim_without_real_evidence_or_text_is_dropped(item: Any) -> None:
    assert _claims([item]) == []


@pytest.mark.parametrize("items", [None, "x", {"text_th": "x"}, 5])
def test_a_section_that_is_not_a_list_is_empty(items: Any) -> None:
    assert _claims(items) == []


def test_made_up_ids_are_removed_from_a_good_claim() -> None:
    [claim] = _claims([{"text_th": "x", "evidence_ids": ["cv-1", "nope", "cv-1", 5, "cv-2"]}])
    assert claim["evidence_ids"] == ["cv-1", "cv-2"]


def test_a_number_not_in_the_facts_is_dropped() -> None:
    assert _claims([{"text_th": "ทำงาน 5 ปี", "evidence_ids": ["cv-1"]}]) == []
    assert _claims([{"text_th": "ฝึกงาน 6 เดือน", "evidence_ids": ["cv-1"]}])


def test_a_skill_the_user_does_not_have_is_dropped_when_checked() -> None:
    item = {"text_th": "เชี่ยวชาญ Kubernetes", "evidence_ids": ["cv-1"]}
    assert _claims([item], names_skills=True) == []
    assert _claims([item], names_skills=False)  # a blind spot may name a missing skill
    good = {"text_th": "ใช้ Python", "evidence_ids": ["cv-1"]}
    assert _claims([good], names_skills=True)


def test_claims_are_capped_and_long_text_cut() -> None:
    items = [{"text_th": "ก" * 900, "evidence_ids": ["cv-1"]} for _ in range(9)]
    claims = _claims(items)
    assert len(claims) == 5
    assert len(claims[0]["text_th"]) == 300


# --- POST /api/profile/generate


async def test_generate_returns_the_contract_shape(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    body = response.json()
    profile = body["profile"]
    assert profile["profile_version"] == 1
    assert profile["generated_at"] == profile["updated_at"]
    assert [s["skill_id"] for s in profile["hard_skills"]] == ["python", "sql", "docker"]
    assert profile["soft_skills"] == []
    assert profile["experience"]["total_months"] == 6
    assert profile["experience"]["summary"][0]["text_th"] == "ฝึกงานที่ ABC 6 เดือน"
    assert profile["blind_spots"][0]["evidence_ids"] == ["cv-4"]
    assert profile["preferences"]["desired_salary_thb"] == 37500
    assert set(profile["work_style"]) == {"summary_th", "traits", "disclaimer_th"}
    assert body["matches"]["profile_version"] == 1


async def _changes(client: httpx.AsyncClient) -> list[str]:
    response = await client.get("/api/profile/completeness")
    assert response.status_code == 200, response.text
    return response.json()["profile_changes"]


async def test_no_profile_means_no_changes_to_report(
    container: Container, user: httpx.AsyncClient
) -> None:
    await _ready(container, user)
    assert await _changes(user) == []


async def test_the_meter_names_the_inputs_changed_since_generating(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    assert (await user.post("/api/profile/generate")).status_code == 200
    assert await _changes(user) == []

    saved = await user.put("/api/questionnaire/answers/ws_teamwork", json={"value": 4})
    assert saved.json()["completeness"]["profile_changes"] == ["work_style"]
    fields = {k: CV_PARSED[k] for k in ("skills", "education", "experience")}
    fields["skills"] = [
        {**skill, "level": 3} if skill["skill_id"] == "sql" else skill for skill in fields["skills"]
    ]
    confirmed = await user.put("/api/cv/confirm", json=fields)
    assert confirmed.status_code == 200, confirmed.text
    assert await _changes(user) == ["cv", "work_style"]


async def test_putting_an_answer_back_is_not_a_change(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    await user.put("/api/questionnaire/answers/go_salary", json={"value": "45k_60k"})
    assert await _changes(user) == ["goals"]
    await user.put("/api/questionnaire/answers/go_salary", json={"value": "30k_45k"})
    assert await _changes(user) == []


async def test_generating_again_clears_the_changes(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    await user.put("/api/questionnaire/answers/ws_teamwork", json={"value": 4})
    groq.reply(LLM_SECTIONS)
    assert (await user.post("/api/profile/generate")).status_code == 200
    assert await _changes(user) == []


async def test_removing_a_skill_needs_no_new_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    """The remove button edits the profile itself, so matches change at once."""
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    removed = await user.delete("/api/profile/skills/docker")
    assert removed.status_code == 200, removed.text
    assert "docker" not in [s["skill_id"] for s in removed.json()["profile"]["hard_skills"]]
    assert await _changes(user) == []


async def test_every_cited_id_is_in_the_evidence_map(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    profile = (await user.post("/api/profile/generate")).json()["profile"]
    cited = [i for s in profile["hard_skills"] for i in s["evidence_ids"]]
    cited += [
        i
        for c in profile["experience"]["summary"] + profile["blind_spots"]
        for i in c["evidence_ids"]
    ]
    assert cited
    assert all(i in profile["evidence"] for i in cited)


async def test_the_prompt_uses_the_main_model_and_json(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    request = groq.requests[0]  # the second call words the matches
    assert request["model"] == "main-model"
    assert request["response_format"] == {"type": "json_object"}
    facts = json.loads(request["messages"][1]["content"])
    assert facts["hard_skills"][0]["evidence_ids"] == ["cv-2"]
    system = request["messages"][0]["content"]
    assert "evidence_ids" in system
    assert "data" in system  # text from the CV must not act as instructions


async def test_a_claim_with_a_made_up_id_does_not_reach_the_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(
        {
            "experience_summary": [{"text_th": "เคยเป็น CTO", "evidence_ids": ["fake"]}],
            "blind_spots": [{"text_th": "อ้างลอย ๆ", "evidence_ids": []}],
        }
    )
    profile = (await user.post("/api/profile/generate")).json()["profile"]
    assert profile["blind_spots"] == []
    # With nothing usable from the model, the summary is plain facts from the entries.
    assert profile["experience"]["summary"][0]["text_th"] == "Intern ที่ ABC (6 เดือน)"


async def test_experience_naming_a_skill_the_user_lacks_is_dropped(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(
        {
            "experience_summary": [
                {"text_th": "ใช้ Kubernetes ที่ ABC", "evidence_ids": ["cv-5"]},
                {"text_th": "ใช้ Python ที่ ABC", "evidence_ids": ["cv-5"]},
            ],
        }
    )
    summary = (await user.post("/api/profile/generate")).json()["profile"]["experience"]["summary"]
    assert [c["text_th"] for c in summary] == ["ใช้ Python ที่ ABC"]


async def test_a_job_title_naming_a_skill_is_not_a_made_up_skill(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    user_id = await _user_id(container)
    parsed = {
        **CV_PARSED,
        "experience": [{"title": "Machine Learning Engineer", "months": 36, "line_no": 5}],
    }
    async with container.sessions() as db:
        db.add(
            CvDocument(
                user_id=user_id,
                filename="cv.pdf",
                text_lines=CV_LINES,
                status="confirmed",
                confirmed_at=utcnow(),
                parsed=parsed,
            )
        )
        await db.commit()
    await user.put("/api/questionnaire/answers/go_salary", json={"value": "30k_45k"})
    text = "เป็น Machine Learning Engineer มา 36 เดือน"
    groq.reply({"experience_summary": [{"text_th": text, "evidence_ids": ["cv-5"]}]})
    summary = (await user.post("/api/profile/generate")).json()["profile"]["experience"]["summary"]
    assert [c["text_th"] for c in summary] == [text]


async def test_the_prompt_keeps_the_summary_to_work_done(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    assert "not skills or education" in groq.requests[0]["messages"][0]["content"]


async def test_regenerating_raises_the_version_and_keeps_one_row(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    first = (await user.post("/api/profile/generate")).json()["profile"]
    groq.reply(LLM_SECTIONS)
    second = (await user.post("/api/profile/generate")).json()
    assert second["profile"]["profile_version"] == 2
    assert second["matches"]["profile_version"] == 2
    assert second["profile"]["generated_at"] >= first["generated_at"]
    async with container.sessions() as db:
        assert len(list(await db.scalars(select(Profile)))) == 1


async def test_not_ready_lists_missing_slots_and_makes_no_llm_call(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    body = assert_problem(await user.post("/api/profile/generate"), 409, "PROFILE_NOT_READY")
    assert body["details"]["missing_required"] == ["hard_skills", "experience"]
    assert body["details"]["missing"][:3] == ["hard_skills", "experience", "soft_skills"]
    assert groq.requests == []
    assert (await user.get("/api/quota")).json()["requests_used"] == 0


async def test_a_draft_cv_is_not_enough(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_cv(container, status="draft")
    assert_problem(await user.post("/api/profile/generate"), 409, "PROFILE_NOT_READY")
    assert groq.requests == []


async def test_a_draft_cv_adds_nothing_when_the_questionnaire_is_enough(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _seed_cv(container, status="draft")
    answers = {
        "sk_tech_stack": [{"skill_id": s, "level": 2} for s in ("git", "html", "css")],
        "ex_it_experience": "none",
        "go_salary": "30k_45k",
    }
    for question_id, value in answers.items():
        url = f"/api/questionnaire/answers/{question_id}"
        response = await user.put(url, json={"value": value})
        assert response.status_code == 200, response.text
    groq.reply({})
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    profile = response.json()["profile"]
    assert [s["skill_id"] for s in profile["hard_skills"]] == ["git", "html", "css"]
    assert not [i for i in profile["evidence"] if i.startswith("cv-")]


async def test_generate_counts_one_request_and_the_tokens(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS, tokens=120)
    await user.post("/api/profile/generate")
    quota = (await user.get("/api/quota")).json()
    assert quota["requests_used"] == 1
    assert quota["tokens_used"] == 120


async def test_no_quota_means_no_llm_call(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    for _ in range(5):
        groq.reply(LLM_SECTIONS, tokens=10)
        assert (await user.post("/api/profile/generate")).status_code == 200
    calls = len(groq.requests)
    assert_problem(await user.post("/api/profile/generate"), 429, "QUOTA_EXCEEDED")
    assert len(groq.requests) == calls


async def test_a_failed_llm_refunds_and_saves_nothing(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.fail()
    assert_problem(await user.post("/api/profile/generate"), 503, "LLM_UNAVAILABLE")
    assert (await user.get("/api/quota")).json()["requests_used"] == 0
    assert (await user.get("/api/profile")).json() == {"profile": None}


async def test_a_failed_regeneration_keeps_the_old_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    groq.fail()
    await user.post("/api/profile/generate")
    assert (await user.get("/api/profile")).json()["profile"]["profile_version"] == 1


# --- GET /api/profile


async def test_get_before_generate_is_null(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {"profile": None}


async def test_get_returns_what_generate_saved(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    saved = (await user.post("/api/profile/generate")).json()["profile"]
    assert (await user.get("/api/profile")).json()["profile"] == saved


async def test_profile_needs_a_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/profile"), 401, "UNAUTHENTICATED")
    assert_problem(await client.post("/api/profile/generate"), 401, "UNAUTHENTICATED")


async def test_another_users_profile_is_not_visible(
    container: Container, client_factory: ClientFactory, groq: Groq
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="user@example.com")
    await register(second, email="b@example.com")
    await _ready(container, first)
    groq.reply(LLM_SECTIONS)
    await first.post("/api/profile/generate")
    assert (await second.get("/api/profile")).json() == {"profile": None}


async def test_another_users_chat_facts_are_not_used(
    container: Container, client_factory: ClientFactory, groq: Groq
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="user@example.com")
    await register(second, email="b@example.com")
    other = await _user_id(container, "b@example.com")
    async with container.sessions() as db:
        db.add(Evidence(id="other-e", user_id=other, kind="chat", ref="m", excerpt="ลับ"))
        db.add(
            Fact(
                user_id=other,
                kind="skill",
                value={"name": "Rust", "skill_id": "rust", "level": 4},
                evidence_id="other-e",
            )
        )
        await db.commit()
    await _ready(container, first)
    groq.reply(LLM_SECTIONS)
    profile = (await first.post("/api/profile/generate")).json()["profile"]
    assert "other-e" not in profile["evidence"]
    assert all(s["name_en"] != "Rust" for s in profile["hard_skills"])


async def test_chat_facts_reach_the_profile_with_the_chat_evidence(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    user_id = await _user_id(container)
    async with container.sessions() as db:
        db.add(
            Evidence(id="ev-1", user_id=user_id, kind="chat", ref="m", excerpt="ผมใช้ Git ระดับ 3")
        )
        db.add(
            Fact(
                user_id=user_id,
                kind="skill",
                value={"name": "Git", "skill_id": "git", "level": 3},
                evidence_id="ev-1",
            )
        )
        await db.commit()
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    profile = (await user.post("/api/profile/generate")).json()["profile"]
    assert _skill(profile["hard_skills"], "git")["evidence_ids"] == ["ev-1"]
    assert profile["evidence"]["ev-1"]["kind"] == "chat"
    assert profile["evidence"]["ev-1"]["excerpt"] == "ผมใช้ Git ระดับ 3"


async def test_the_latest_chat_level_reaches_the_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    user_id = await _user_id(container)
    async with container.sessions() as db:
        db.add(Evidence(id="ev-1", user_id=user_id, kind="chat", ref="m", excerpt="Git 1"))
        for level in (1, 4):
            db.add(
                Fact(
                    user_id=user_id,
                    kind="skill",
                    value={"name": "Git", "skill_id": "git", "level": level},
                    evidence_id="ev-1",
                )
            )
            await db.flush()
        await db.commit()
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    profile = (await user.post("/api/profile/generate")).json()["profile"]
    assert _skill(profile["hard_skills"], "git")["level"] == 4


# --- removing data


async def test_deleting_the_cv_removes_the_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    assert (await user.delete("/api/cv")).status_code == 200
    assert (await user.get("/api/profile")).json() == {"profile": None}


async def test_deleting_the_account_removes_the_profile(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200
    async with container.sessions() as db:
        assert list(await db.scalars(select(Profile))) == []


# --- chat knows about the profile


async def test_chat_uses_the_router_after_a_profile_exists(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    groq.reply({"claims": []})
    message = {"message": "ฉันเหมาะกับสายงานไหน"}
    body = (await user.post("/api/chat", json=message)).json()
    assert body["route"] == "job_matching"
    assert "ตรง" in body["answer"]


async def test_another_users_profile_does_not_change_my_chat(
    container: Container, client_factory: ClientFactory, groq: Groq
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="user@example.com")
    await register(second, email="b@example.com")
    await _ready(container, first)
    groq.reply(LLM_SECTIONS)
    await first.post("/api/profile/generate")
    groq.reply({})
    body = (await second.post("/api/chat", json={"message": "ฉันเหมาะกับสายงานไหน"})).json()
    assert body["route"] == "gap_question"


async def test_chat_asks_gap_questions_before_a_profile(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({})
    body = (await user.post("/api/chat", json={"message": "ฉันเหมาะกับสายงานไหน"})).json()
    assert body["route"] == "gap_question"


# --- ids must not reach the user


@pytest.mark.parametrize(
    "text",
    [
        'เตรียม Python ให้พร้อม (evidence_ids: ["role-backend-developer"])',
        'เตรียม Python ให้พร้อม (evidence_ids: ["role-backend-developer", "cv-1"])',
        "เตรียม Python ให้พร้อม evidence_ids: ['role-backend-developer']",
        'เตรียม Python ให้พร้อม [evidence_id: "cv-1"]',
        "เตรียม Python ให้พร้อม (evidence_ids=[cv-1])",
    ],
)
def test_a_copied_id_field_is_cut_from_the_sentence(text: str) -> None:
    claims = parse_claims(
        [{"text_th": text, "evidence_ids": ["cv-1"]}],
        evidence={"cv-1", "role-backend-developer"},
        facts_text="",
        taxonomy=TAXONOMY,
    )
    assert [c["text_th"] for c in claims] == ["เตรียม Python ให้พร้อม"]
    assert claims[0]["evidence_ids"] == ["cv-1"]


@pytest.mark.parametrize(
    "text",
    [
        "เตรียม Python ให้พร้อม จาก role-backend-developer",
        "เตรียม Python ให้พร้อม [cv-1]",
        "ดู evidence เพิ่มเติม",
        '(evidence_ids: ["cv-1"])',
    ],
)
def test_a_sentence_that_still_shows_an_id_is_dropped(text: str) -> None:
    claims = parse_claims(
        [{"text_th": text, "evidence_ids": ["cv-1"]}],
        evidence={"cv-1", "role-backend-developer"},
        facts_text="",
        taxonomy=TAXONOMY,
    )
    assert claims == []


def test_a_number_inside_a_copied_id_does_not_fail_the_number_check() -> None:
    claims = parse_claims(
        [{"text_th": 'ฝึก Python (evidence_ids: ["cv-7"])', "evidence_ids": ["cv-7"]}],
        evidence={"cv-7"},
        facts_text="",
        taxonomy=TAXONOMY,
    )
    assert [c["text_th"] for c in claims] == ["ฝึก Python"]


def test_an_id_inside_a_longer_word_is_kept() -> None:
    claims = parse_claims(
        [{"text_th": "ฝึก abcv-1x", "evidence_ids": ["cv-1"]}],
        evidence={"cv-1"},
        facts_text="1",
        taxonomy=TAXONOMY,
    )
    assert [c["text_th"] for c in claims] == ["ฝึก abcv-1x"]


# --- projects in the CV

PROJECT_LINES = [
    "Test Candidate",
    "PROJECTS",
    "Course Tracker: web app with React, deployed with Docker",
    "EDUCATION",
    "B.Sc. Computer Science",
]


def test_project_lines_reach_the_llm_with_their_cv_line() -> None:
    draft = _draft(parsed=CV_PARSED, lines=PROJECT_LINES)
    assert draft.llm_facts["projects"] == [
        {"text": PROJECT_LINES[2], "evidence_ids": ["cv-3"]},
    ]
    assert draft.evidence["cv-3"]["excerpt"] == PROJECT_LINES[2]


def test_no_cv_means_no_project_facts() -> None:
    assert _draft().llm_facts["projects"] == []


def test_a_project_line_naming_a_removed_skill_stays_out() -> None:
    draft = build_draft(
        cv=CV_PARSED,
        cv_lines=[*PROJECT_LINES, "PROJECTS", "Notes app in Python"],
        answers={},
        chat=[],
        questionnaire=QUESTIONNAIRE,
        taxonomy=TAXONOMY,
        roles=ROLES,
        removed=frozenset({"docker"}),
    )
    assert [p["text"] for p in draft.llm_facts["projects"]] == ["Notes app in Python"]
    assert "Docker" not in facts_as_text(draft.llm_facts["projects"])


def test_project_facts_are_capped_and_short() -> None:
    lines = ["PROJECTS", *[f"Project {i} " + "x" * 300 for i in range(20)]]
    projects = _draft(parsed=CV_PARSED, lines=lines).llm_facts["projects"]
    assert len(projects) == 10
    assert all(len(p["text"]) <= 150 for p in projects)


# --- found by testing the running system


def test_a_hand_added_skill_is_mapped_to_the_taxonomy() -> None:
    parsed = {"skills": [{"name": "Kubernetes", "line_no": 0, "level": 3}]}
    assert _skill(_draft(parsed=parsed).hard_skills, "kubernetes")["level"] == 3


def test_a_duplicate_in_the_cv_is_one_skill_with_the_higher_level() -> None:
    parsed = {
        "skills": [
            {"name": "Python", "skill_id": "python", "level": 3, "line_no": 2},
            {"name": "python", "line_no": 0, "level": 1},
        ]
    }
    draft = _draft(parsed=parsed, lines=CV_LINES)
    assert [s["skill_id"] for s in draft.hard_skills] == ["python"]
    assert draft.hard_skills[0]["level"] == 3


def test_free_text_naming_two_skills_stays_custom() -> None:
    parsed = {"skills": [{"name": "Python and SQL", "line_no": 0, "level": 2}]}
    assert _draft(parsed=parsed).hard_skills[0]["skill_id"].startswith("custom-")


def test_every_skill_from_one_question_finds_itself_in_the_citation() -> None:
    answers = {
        "sk_tech_stack": [
            {"skill_id": "python", "level": 2},
            {"skill_id": "sql", "level": 2},
            {"skill_id": "git", "level": 2},
        ]
    }
    excerpt = _draft(answers=answers).evidence["answer-sk_tech_stack"]["excerpt"].casefold()
    assert all(name in excerpt for name in ("python", "sql", "git"))


def test_a_summary_naming_a_removed_skill_stays_away_from_the_llm() -> None:
    parsed = {
        "skills": [{"name": "SQL", "skill_id": "sql", "level": 2, "line_no": 3}],
        "experience": [
            {"title": "Intern", "summary": "สร้าง REST APIs ด้วย Python", "line_no": 5},
            {"title": "Analyst", "summary": "เขียนรายงานยอดขาย", "line_no": 6},
        ],
    }
    draft = build_draft(
        cv=parsed,
        cv_lines=CV_LINES,
        answers={},
        chat=[],
        questionnaire=QUESTIONNAIRE,
        taxonomy=TAXONOMY,
        roles=ROLES,
        removed=frozenset({"python"}),
    )
    text = facts_as_text(draft.llm_facts)
    assert "Python" not in text
    assert "เขียนรายงานยอดขาย" in text


def test_an_example_naming_a_removed_skill_stays_away_from_the_llm() -> None:
    draft = build_draft(
        cv=None,
        cv_lines=[],
        answers={"ss_example": "สอนเพื่อนใช้ Python"},
        chat=[],
        questionnaire=QUESTIONNAIRE,
        taxonomy=TAXONOMY,
        roles=ROLES,
        removed=frozenset({"python"}),
    )
    assert "Python" not in facts_as_text(draft.llm_facts)


def test_contact_details_stay_away_from_the_llm() -> None:
    parsed = {
        "skills": [],
        "experience": [
            {
                "title": "Intern",
                "summary": "งานวิเคราะห์ โทร 081-234-5678 pat@example.com",
                "line_no": 5,
            }
        ],
        "education": [{"school": "pat@example-university.ac.th", "line_no": 6}],
    }
    text = facts_as_text(_draft(parsed=parsed, lines=CV_LINES).llm_facts)
    assert "081-234-5678" not in text
    assert "pat@" not in text
    assert "งานวิเคราะห์" in text


async def test_a_skill_removed_while_generating_stays_removed(
    container: Container,
    user: httpx.AsyncClient,
    groq: Groq,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ready(container, user)
    user_id = await _user_id(container)
    write = profile_service._write_sections

    async def remove_during_the_llm_call(*args: Any, **kwargs: Any) -> Any:
        result = await write(*args, **kwargs)
        async with container.sessions() as db:
            db.add(
                RemovedSkill(
                    user_id=user_id,
                    skill_id="python",
                    skill={"skill_id": "python", "name_th": "Python", "evidence_ids": []},
                    removed_at=utcnow(),
                )
            )
            await db.commit()
        return result

    monkeypatch.setattr(profile_service, "_write_sections", remove_during_the_llm_call)
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    assert "python" not in {s["skill_id"] for s in response.json()["profile"]["hard_skills"]}
