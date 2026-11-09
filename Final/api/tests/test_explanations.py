"""Match reasons and next steps (Contract.md §2.6, Design.md §4.3, PRD FR-19, FR-20a, FR-32)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from app.api.deps import Container
from app.domain.matching import explanations
from app.infra.models import MatchExplanation, Profile
from tests.conftest import assert_problem
from tests.test_profile import LLM_SECTIONS, Groq, _ready


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


def _matches_from_facts(groq: Groq) -> list[dict[str, Any]]:
    return json.loads(groq.requests[-1]["messages"][1]["content"])["roles"]


def _wording_for(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Good wording for every role the app sent."""
    return {
        "roles": [
            {
                "role_id": role["role_id"],
                "reason": {
                    "text_th": f"คุณมีทักษะที่ตรงกับ {role['title']}",
                    "evidence_ids": role["matched"][0]["evidence_ids"][:1],
                },
                "next_steps": [
                    {"gap_id": gap["gap_id"], "action_th": f"ลงมือฝึกข้อ {gap['name_th']}"}
                    for gap in role["gaps"]
                ],
            }
            for role in facts
            if role["matched"]
        ]
    }


async def _generate(container: Container, user: httpx.AsyncClient, groq: Groq) -> dict[str, Any]:
    """The profile with no LLM wording: the second call fails, so the wording is computed."""
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    return response.json()


async def _word_everything(user: httpx.AsyncClient, groq: Groq) -> dict[str, Any]:
    """Generate wrote nothing, so explain writes all shown roles."""
    facts = _matches_from_facts(groq)
    groq.requests.clear()
    groq.reply(_wording_for(facts), tokens=90)
    response = await user.post("/api/roles/matches/explain")
    assert response.status_code == 200, response.text
    return response.json()


async def _drop_a_skill(container: Container, skill_id: str = "python") -> None:
    async with container.sessions() as db:
        row = (await db.scalars(select(Profile))).one()
        sections = dict(row.sections)
        sections["hard_skills"] = [
            s for s in row.sections["hard_skills"] if s["skill_id"] != skill_id
        ]
        await db.execute(update(Profile).values(sections=sections))
        await db.commit()


# --- wording during generate


async def test_generate_words_every_shown_role_under_one_request(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS, tokens=100)
    before = (await user.get("/api/quota")).json()
    # The facts are known only once the app sends them, so this reply names no role yet.
    groq.reply({"roles": []}, tokens=50)
    body = (await user.post("/api/profile/generate")).json()
    after = (await user.get("/api/quota")).json()
    assert after["requests_used"] == before["requests_used"] + 1
    assert after["tokens_used"] == before["tokens_used"] + 150
    assert len(groq.requests) == 2
    assert groq.requests[1]["model"] == "main-model"
    for match in body["matches"]["roles"]:
        assert match["reason_th"]
        assert match["explanations_stale"] is False
        assert [s["gap_id"] for s in match["next_steps"]] == [
            g["gap_id"] for g in match["gaps"][:5]
        ]


async def test_a_failed_wording_call_does_not_fail_generate(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    body = await _generate(container, user, groq)
    assert body["profile"]["profile_version"] == 1
    top = body["matches"]["roles"][0]
    assert top["reason_th"]
    assert top["explanations_stale"] is False
    assert top["next_steps"][0]["priority"] == 1
    assert top["next_steps"][0]["gap_id"] == top["gaps"][0]["gap_id"]


async def test_no_tokens_left_skips_the_wording_call(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS, tokens=5000)
    body = (await user.post("/api/profile/generate")).json()
    assert len(groq.requests) == 1
    assert body["matches"]["roles"][0]["next_steps"]


# --- what goes to the LLM


async def test_only_names_levels_and_evidence_ids_go_to_the_llm(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    raw = groq.requests[-1]["messages"][1]["content"]
    role = json.loads(raw)["roles"][0]
    assert set(role) == {"role_id", "title", "matched", "gaps", "learning_path"}
    assert len(role["gaps"]) <= 5
    assert "match_pct" not in raw
    assert not re.search(r"^\d+\.", role["learning_path"], re.MULTILINE)
    for private in ("Somchai", "Intern at ABC", "BSc", "37500"):
        assert private not in raw


# --- checking what the LLM wrote


def _match() -> dict[str, Any]:
    return {
        "role_id": "qa-engineer",
        "title_th": "QA",
        "matched": [{"skill_id": "python", "name_th": "Python", "evidence_ids": ["cv-2"]}],
        "gaps": [
            {
                "gap_id": "g0",
                "kind": "missing_skill",
                "skill_id": "sql",
                "name_th": "SQL",
                "required_level": 2,
            },
            {
                "gap_id": "g1",
                "kind": "below_level",
                "skill_id": "python",
                "name_th": "Python",
                "required_level": 3,
                "user_level": 1,
            },
            {"gap_id": "g2", "kind": "soft_skill", "skill_id": "teamwork", "name_th": "ทำงานเป็นทีม"},
        ],
    }


@pytest.fixture
def parse(container: Container) -> Any:
    from app.domain.matching.roles import load_catalogue
    from app.services import cv_service

    role = next(r for r in load_catalogue("../data") if r.role_id == "qa-engineer")
    taxonomy = cv_service.taxonomy_for(container.settings)
    facts = {"qa-engineer": explanations.role_facts(_match(), role)}

    def run(item: dict[str, Any]) -> explanations.Explanation:
        data = {"roles": [{"role_id": "qa-engineer", **item}]}
        return explanations.parse_explanations(data, [_match()], facts, taxonomy)["qa-engineer"]

    return run


def test_good_wording_is_kept_in_the_order_scoring_gave(parse: Any) -> None:
    out = parse(
        {
            "reason": {"text_th": "คุณใช้ Python ได้", "evidence_ids": ["cv-2"]},
            "next_steps": [
                {"gap_id": "g1", "action_th": "ฝึก Python เพิ่ม"},
                {"gap_id": "g0", "action_th": "ทำโปรเจกต์ด้วย SQL"},
            ],
        }
    )
    assert out.reason_th == "คุณใช้ Python ได้"
    assert out.next_steps[0] == {"gap_id": "g0", "action_th": "ทำโปรเจกต์ด้วย SQL", "priority": 1}
    assert out.next_steps[1] == {"gap_id": "g1", "action_th": "ฝึก Python เพิ่ม", "priority": 2}
    assert "ทำงานเป็นทีม" in out.next_steps[2]["action_th"]  # left out, so computed


@pytest.mark.parametrize(
    "step",
    [
        {"gap_id": "made-up", "action_th": "ฝึกอะไรก็ได้"},
        {"action_th": "ไม่มี gap"},
        {"gap_id": "g0", "action_th": ""},
        {"gap_id": "g0", "action_th": "เรียน SQL 99 ชั่วโมง"},
        {"gap_id": "g0", "action_th": "เรียน Kubernetes ก่อน"},
        "not a step",
    ],
)
def test_an_action_that_does_not_hold_up_is_computed_instead(parse: Any, step: Any) -> None:
    out = parse({"next_steps": [step]})
    assert [s["gap_id"] for s in out.next_steps] == ["g0", "g1", "g2"]
    assert out.next_steps[0]["action_th"].startswith("เรียนรู้ SQL ให้ถึงระดับ 2")
    assert "99" not in out.next_steps[0]["action_th"]
    assert "Kubernetes" not in out.next_steps[0]["action_th"]


@pytest.mark.parametrize(
    "reason",
    [
        {"text_th": "คุณเก่ง SQL", "evidence_ids": ["cv-2"]},
        {"text_th": "คุณใช้ Python ได้", "evidence_ids": ["made-up"]},
        {"text_th": "ตรงกับคุณ 99%", "evidence_ids": ["cv-2"]},
        "not a reason",
        None,
    ],
)
def test_a_reason_that_does_not_hold_up_is_computed_instead(parse: Any, reason: Any) -> None:
    assert parse({"reason": reason}).reason_th == "คุณมี Python ซึ่งตรงกับทักษะของ QA"


def test_rubbish_from_the_llm_still_gives_a_step_for_every_gap(container: Container) -> None:
    computed = explanations.computed(_match())
    assert [s["priority"] for s in computed.next_steps] == [1, 2, 3]
    assert computed.next_steps[1]["action_th"] == "ฝึก Python จากระดับ 1 ให้ถึงระดับ 3"


def test_at_most_five_steps() -> None:
    match = _match()
    match["gaps"] = [{**match["gaps"][2], "gap_id": f"g{n}"} for n in range(8)]
    assert len(explanations.computed(match).next_steps) == 5


def test_no_matched_skills_says_so() -> None:
    match = {**_match(), "matched": []}
    assert explanations.computed(match).reason_th == "ยังไม่พบทักษะที่ตรงกับ QA ในโปรไฟล์ของคุณ"


# --- reading and explain


async def test_reading_matches_uses_no_llm_and_no_quota(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    generated = await _generate(container, user, groq)
    groq.requests.clear()
    before = (await user.get("/api/quota")).json()
    matches = (await user.get("/api/roles/matches")).json()
    assert matches == generated["matches"]
    role_id = matches["roles"][0]["role_id"]
    detail = (await user.get(f"/api/roles/{role_id}")).json()
    assert detail["match"]["next_steps"] == matches["roles"][0]["next_steps"]
    assert groq.requests == []
    assert (await user.get("/api/quota")).json() == before


async def test_explain_saves_the_wording_and_counts(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    before = (await user.get("/api/quota")).json()
    body = await _word_everything(user, groq)
    after = (await user.get("/api/quota")).json()
    assert after["requests_used"] == before["requests_used"] + 1
    assert after["tokens_used"] == before["tokens_used"] + 90
    top = body["roles"][0]
    assert top["reason_th"].startswith("คุณมีทักษะที่ตรงกับ")
    assert top["next_steps"][0]["action_th"].startswith("ลงมือฝึกข้อ")
    assert (await user.get("/api/roles/matches")).json() == body
    detail = (await user.get(f"/api/roles/{top['role_id']}")).json()
    assert detail["match"]["reason_th"] == top["reason_th"]


async def test_explain_with_nothing_to_do_costs_nothing(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    await _word_everything(user, groq)
    groq.requests.clear()
    before = (await user.get("/api/quota")).json()
    response = await user.post("/api/roles/matches/explain")
    assert response.status_code == 200
    assert groq.requests == []
    assert (await user.get("/api/quota")).json() == before


async def test_a_changed_profile_makes_listed_wording_stale_until_explain(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    await _word_everything(user, groq)
    await _drop_a_skill(container)
    matches = (await user.get("/api/roles/matches")).json()
    stale = [m for m in matches["roles"] if m["explanations_stale"]]
    assert stale
    assert all(m["reason_th"] is None and m["next_steps"] == [] for m in stale)

    groq.requests.clear()
    groq.reply({"roles": []}, tokens=40)
    explained = (await user.post("/api/roles/matches/explain")).json()
    assert {m["role_id"] for m in stale} <= {f["role_id"] for f in _matches_from_facts(groq)}
    assert not any(m["explanations_stale"] for m in explained["roles"])
    assert all(m["reason_th"] for m in explained["roles"])


async def test_a_role_outside_the_list_with_old_wording_is_not_stuck_stale(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    words = await _word_everything(user, groq)
    listed = {m["role_id"] for m in words["roles"]}
    catalogue = (await user.get("/api/roles")).json()["roles"]
    outside = next(r["role_id"] for r in catalogue if r["role_id"] not in listed)
    async with container.sessions() as db:
        db.add(
            MatchExplanation(
                user_id=(await db.scalars(select(Profile))).one().user_id,
                role_id=outside,
                basis="an older basis",
                reason_th="ข้อความเก่า",
                next_steps=[],
                updated_at=(await db.scalars(select(Profile))).one().updated_at,
            )
        )
        await db.commit()
    match = (await user.get(f"/api/roles/{outside}")).json()["match"]
    assert match["explanations_stale"] is False
    assert match["reason_th"] != "ข้อความเก่า"


async def test_regenerating_replaces_the_old_wording(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    await _word_everything(user, groq)
    groq.requests.clear()
    groq.reply(LLM_SECTIONS)
    groq.reply({"roles": []})
    body = (await user.post("/api/profile/generate")).json()
    top = body["matches"]["roles"][0]
    assert not top["reason_th"].startswith("คุณมีทักษะที่ตรงกับ")
    async with container.sessions() as db:
        rows = list(await db.scalars(select(MatchExplanation)))
    assert {row.role_id for row in rows} == {m["role_id"] for m in body["matches"]["roles"]}


async def test_explain_before_a_profile_is_not_found(user: httpx.AsyncClient) -> None:
    assert_problem(await user.post("/api/roles/matches/explain"), 404, "PROFILE_NOT_FOUND")


async def test_explain_needs_a_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.post("/api/roles/matches/explain"), 401, "UNAUTHENTICATED")


async def test_a_failed_explain_refunds_and_keeps_the_wording(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    before = (await user.get("/api/quota")).json()
    groq.fail()
    assert_problem(await user.post("/api/roles/matches/explain"), 503, "LLM_UNAVAILABLE")
    assert (await user.get("/api/quota")).json()["requests_used"] == before["requests_used"]
    assert (await user.get("/api/roles/matches")).json()["roles"][0]["next_steps"]


async def test_explain_with_no_quota_left_is_refused_before_any_call(
    container: Container, user: httpx.AsyncClient, groq: Groq, settings_overrides: dict[str, Any]
) -> None:
    await _generate(container, user, groq)
    async with container.sessions() as db:
        from app.infra.models import QuotaUsage

        await db.execute(update(QuotaUsage).values(requests=20))
        await db.commit()
    groq.requests.clear()
    assert_problem(await user.post("/api/roles/matches/explain"), 429, "QUOTA_EXCEEDED")
    assert groq.requests == []


async def test_deleting_the_account_deletes_the_wording(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _generate(container, user, groq)
    await _word_everything(user, groq)
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200
    async with container.sessions() as db:
        assert list(await db.scalars(select(MatchExplanation))) == []
