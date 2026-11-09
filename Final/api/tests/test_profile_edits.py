"""Editing the profile (Contract.md §2.5, Design.md §4.5, PRD FR-27 – FR-34)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from app.api.deps import Container
from app.core.clock import utcnow
from app.domain.matching.skills import load_taxonomy
from app.domain.profile_edits import keep_user_edits
from app.infra.models import EditProposal, MatchExplanation, Profile, QuotaUsage, RemovedSkill
from app.services.questionnaire_service import questionnaire_for
from tests.conftest import assert_problem, register
from tests.test_profile import LLM_SECTIONS, Groq, _ready

SET_LEVEL = {"target": "skill", "op": "set", "skill": "Python", "level": 4}


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


async def _ask(user: httpx.AsyncClient, groq: Groq, *changes: dict[str, Any]) -> dict[str, Any]:
    groq.reply({"changes": list(changes)}, tokens=40)
    response = await user.post("/api/chat", json={"message": "ลบ Docker"})
    assert response.status_code == 200, response.text
    return response.json()


async def _propose(user: httpx.AsyncClient, groq: Groq, *changes: dict[str, Any]) -> dict[str, Any]:
    edit = (await _ask(user, groq, *changes))["edit_proposal"]
    assert edit is not None
    return edit


async def _confirm(user: httpx.AsyncClient, edit_id: str) -> dict[str, Any]:
    response = await user.post(f"/api/profile/edits/{edit_id}/confirm")
    assert response.status_code == 200, response.text
    return response.json()


async def _profile(user: httpx.AsyncClient) -> dict[str, Any]:
    return (await user.get("/api/profile")).json()["profile"]


def _skill(profile: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    skills = [*profile["hard_skills"], *profile["soft_skills"]]
    return next((s for s in skills if s["skill_id"] == skill_id), None)


# --- proposing


async def test_a_chat_edit_proposes_and_changes_nothing_yet(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = await _profile(user)
    body = await _ask(user, groq, SET_LEVEL)
    assert body["route"] == "profile_edit"
    assert "กดยืนยัน" in body["answer"]
    assert body["tokens_used"] == 40
    edit = body["edit_proposal"]
    assert edit["status"] == "pending"
    assert edit["summary_th"] == "เปลี่ยนระดับ Python จาก 3 เป็น 4"
    assert edit["changes"] == [
        {
            "op": "set",
            "field": "skills.python.level",
            "skill_id": "python",
            "old_value": 3,
            "new_value": 4,
        }
    ]
    assert await _profile(user) == before
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == [edit]


async def test_the_llm_gets_only_the_message_and_the_cheap_model(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await _ask(user, groq, SET_LEVEL)
    request = groq.requests[-1]
    assert request["model"] == "router-model"
    sent = json.loads(request["messages"][1]["content"])
    assert set(sent) == {"message", "current"}
    assert sent["message"] == "ลบ Docker"
    assert set(sent["current"]) == {"interested_roles", "locations", "desired_salary"}


@pytest.mark.parametrize(
    "change",
    [
        {"target": "email", "value": "a@b.c"},
        {"target": "profile_version", "value": 99},
        {"target": "skill", "op": "set", "skill": "Python", "level": 9},
        {"target": "skill", "op": "set", "skill": "Python", "level": True},
        {"target": "skill", "op": "set", "skill": "Python", "years": -1},
        {"target": "skill", "op": "set", "skill": "Python", "level": 3},  # already 3
        {"target": "skill", "op": "explode", "skill": "Python"},
        {"target": "skill", "op": "remove", "skill": "Kubernetes"},  # not in the profile
        {"target": "skill", "op": "set", "skill": "Kubernetes", "years": 2},
        {"target": "desired_salary", "value": 5},
        {"target": "desired_salary", "value": "lots"},
        {"target": "interested_roles", "op": "set", "values": ["no such role"]},
        {"target": "locations", "op": "set", "values": [""]},
        {"target": "work_style", "trait": "made-up", "score": 3},
        {"target": "work_style", "trait": "teamwork", "score": 9},
        "not a change",
    ],
)
async def test_what_is_off_the_allow_list_proposes_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None, change: Any
) -> None:
    body = await _ask(user, groq, change)
    assert body["route"] == "profile_edit"
    assert body["edit_proposal"] is None
    assert "แก้ได้เฉพาะ" in body["answer"]
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == []


async def test_a_reply_that_is_not_a_list_proposes_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    groq.reply({"changes": "ลบทุกอย่าง"})
    body = (await user.post("/api/chat", json={"message": "ลบ Docker"})).json()
    assert body["edit_proposal"] is None


async def test_an_edit_before_a_profile_is_treated_as_filling_gaps(
    user: httpx.AsyncClient, groq: Groq
) -> None:
    groq.reply({})
    response = await user.post("/api/chat", json={"message": "ลบ Docker"})
    assert response.status_code == 200
    assert response.json()["route"] == "gap_question"
    assert response.json()["edit_proposal"] is None


async def test_a_failed_llm_refunds_and_saves_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = (await user.get("/api/quota")).json()["requests_used"]
    groq.fail()
    response = await user.post("/api/chat", json={"message": "ลบ Docker"})
    assert response.status_code == 503
    assert (await user.get("/api/quota")).json()["requests_used"] == before
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == []


# --- confirming


async def test_confirm_applies_and_labels_the_skill(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = await _profile(user)
    edit = await _propose(user, groq, SET_LEVEL)
    body = await _confirm(user, edit["edit_id"])
    profile = body["profile"]
    assert profile == await _profile(user)
    assert profile["profile_version"] == before["profile_version"] + 1
    python = _skill(profile, "python")
    assert python is not None
    assert python["level"] == 4
    assert python["edited_by_user"] is True
    evidence_id = f"ua-{edit['edit_id']}"
    assert evidence_id in python["evidence_ids"]
    assert profile["evidence"][evidence_id]["kind"] == "user_action"
    assert profile["evidence"][evidence_id]["label_th"] == "คุณแก้ไขเอง"
    assert body["matches"] == (await user.get("/api/roles/matches")).json()
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == []


async def test_confirm_works_with_no_quota_left(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, SET_LEVEL)
    async with container.sessions() as db:
        await db.execute(update(QuotaUsage).values(requests=20, tokens=5000))
        await db.commit()
    await _confirm(user, edit["edit_id"])


async def test_every_kind_of_change_applies(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(
        user,
        groq,
        {"target": "skill", "op": "add", "skill": "Figma", "level": 2},
        {"target": "skill", "op": "set", "skill": "SQL", "years": 2},
        {"target": "skill", "op": "remove", "skill": "Docker"},
        {"target": "desired_salary", "value": 45000},
        {"target": "interested_roles", "op": "set", "values": ["QA Engineer"]},
        {"target": "locations", "op": "add", "values": ["เชียงใหม่"]},
        {"target": "work_style", "trait": "teamwork", "score": 5},
    )
    assert "teamwork" not in edit["summary_th"]
    profile = (await _confirm(user, edit["edit_id"]))["profile"]
    figma = next(s for s in profile["hard_skills"] if "Figma" in s["name_en"])
    assert figma["level"] == 2
    assert figma["edited_by_user"] is True
    sql = _skill(profile, "sql")
    assert sql is not None
    assert sql["years"] == 2
    assert _skill(profile, "docker") is None
    preferences = profile["preferences"]
    assert preferences["desired_salary_thb"] == 45000
    assert preferences["interested_roles"] == ["qa-engineer"]
    assert "เชียงใหม่" in preferences["locations"]
    assert preferences["work_style"]["teamwork"] == 1
    trait = next(t for t in profile["work_style"]["traits"] if t["trait"] == "teamwork")
    assert trait["value"] == 1
    assert trait["label_th"] in profile["work_style"]["summary_th"]
    assert "edited_preferences" not in profile


async def test_a_level_for_a_skill_not_listed_adds_it(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(
        user, groq, {"target": "skill", "op": "set", "skill": "Figma", "level": 2}
    )
    assert edit["changes"][0]["op"] == "add"


@pytest.mark.parametrize(
    ("typed", "skill_id"),
    [
        ("statistic", "statistics"),
        ("statitic", "statistics"),
        ("สภิติ", "statistics"),
        ("Macine Learnig", "machine-learning"),
        ("Javva", "java"),
        ("Dockr", "docker"),
    ],
)
def test_a_mistyped_skill_gets_a_suggestion(typed: str, skill_id: str) -> None:
    assert load_taxonomy("../data").suggest(typed) == skill_id


@pytest.mark.parametrize("typed", ["ทำอาหาร", "ขับรถ", "hello", "asdfgh", "x"])
def test_an_unrelated_word_gets_no_suggestion(typed: str) -> None:
    assert load_taxonomy("../data").suggest(typed) is None


async def test_chat_asks_about_a_mistyped_skill_and_proposes_the_real_one(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(
        user, groq, {"target": "skill", "op": "add", "skill": "statistic", "level": 1}
    )
    assert "คุณอาจหมายถึง “สถิติ” หรือไม่" in body["answer"]
    change = body["edit_proposal"]["changes"][0]
    assert change["skill_id"] == "statistics"
    assert change["new_value"] == {"name_th": "สถิติ", "level": 1}
    assert _skill(await _profile(user), "statistics") is None  # waits for the button

    await _confirm(user, body["edit_proposal"]["edit_id"])
    saved = _skill(await _profile(user), "statistics")
    assert saved is not None and saved["level"] == 1


async def test_a_mistyped_name_of_a_listed_skill_changes_that_skill(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = await _ask(user, groq, {"target": "skill", "op": "set", "skill": "Pyton", "level": 4})
    assert "คุณอาจหมายถึง" in body["answer"]
    change = body["edit_proposal"]["changes"][0]
    assert (change["op"], change["skill_id"], change["new_value"]) == ("set", "python", 4)


async def test_chat_does_not_propose_a_skill_outside_the_taxonomy(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = await _profile(user)
    body = await _ask(user, groq, {"target": "skill", "op": "add", "skill": "ทำอาหาร", "level": 1})
    assert body["edit_proposal"] is None
    assert "ไม่พบทักษะ “ทำอาหาร” ในระบบ" in body["answer"]
    assert await _profile(user) == before


async def test_a_custom_skill_already_listed_can_still_be_removed(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    async with container.sessions() as db:
        row = await db.scalar(select(Profile))
        assert row is not None
        sections = json.loads(json.dumps(row.sections))
        sections["hard_skills"].append(
            {
                "skill_id": "custom-abc",
                "name_th": "Macine Learnig",
                "name_en": "Macine Learnig",
                "kind": "hard",
                "level": 1,
                "evidence_ids": [],
                "edited_by_user": True,
            }
        )
        row.sections = sections
        await db.commit()
    edit = await _propose(
        user, groq, {"target": "skill", "op": "remove", "skill": "Macine Learnig"}
    )
    assert edit["changes"][0]["skill_id"] == "custom-abc"


async def test_removing_a_skill_wins_over_changing_it_in_the_same_message(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(
        user,
        groq,
        {"target": "skill", "op": "remove", "skill": "Python"},
        SET_LEVEL,
    )
    assert [c["op"] for c in edit["changes"]] == ["remove"]
    assert _skill((await _confirm(user, edit["edit_id"]))["profile"], "python") is None


async def test_an_unknown_edit_is_not_found(user: httpx.AsyncClient, with_profile: None) -> None:
    assert_problem(await user.post("/api/profile/edits/nope/confirm"), 404, "EDIT_NOT_FOUND")
    assert_problem(await user.post("/api/profile/edits/nope/reject"), 404, "EDIT_NOT_FOUND")


async def test_a_confirmed_edit_cannot_be_used_again(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, SET_LEVEL)
    await _confirm(user, edit["edit_id"])
    url = f"/api/profile/edits/{edit['edit_id']}/confirm"
    assert_problem(await user.post(url), 404, "EDIT_NOT_FOUND")


async def test_an_old_proposal_expires(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, SET_LEVEL)
    async with container.sessions() as db:
        await db.execute(update(EditProposal).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == []
    url = f"/api/profile/edits/{edit['edit_id']}/confirm"
    assert_problem(await user.post(url), 409, "EDIT_EXPIRED")
    assert_problem(await user.post(url), 409, "EDIT_EXPIRED")
    python = _skill(await _profile(user), "python")
    assert python is not None
    assert python["level"] == 3


async def test_a_proposal_lasts_fifteen_minutes(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, SET_LEVEL)
    assert edit["expires_at"].endswith("+07:00")
    left = datetime.fromisoformat(edit["expires_at"]) - utcnow()
    assert timedelta(minutes=14) < left <= timedelta(minutes=15)


async def test_a_field_changed_since_the_proposal_is_a_conflict(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    first = await _propose(user, groq, SET_LEVEL)
    second = await _propose(user, groq, {**SET_LEVEL, "level": 2})
    # A new proposal closes the old one, so only two requests racing can leave both open.
    async with container.sessions() as db:
        await db.execute(
            update(EditProposal).where(EditProposal.id == first["edit_id"]).values(status="pending")
        )
        await db.commit()
    await _confirm(user, first["edit_id"])
    url = f"/api/profile/edits/{second['edit_id']}/confirm"
    assert_problem(await user.post(url), 409, "EDIT_CONFLICT")
    python = _skill(await _profile(user), "python")
    assert python is not None
    assert python["level"] == 4


async def test_someone_elses_edit_is_not_found(
    client: httpx.AsyncClient, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, SET_LEVEL)
    await register(client, "other@example.com")
    url = f"/api/profile/edits/{edit['edit_id']}"
    assert_problem(await client.post(f"{url}/confirm"), 404, "EDIT_NOT_FOUND")
    assert_problem(await client.post(f"{url}/reject"), 404, "EDIT_NOT_FOUND")
    assert (await user.get("/api/profile/edits/pending")).json()["edits"] == [edit]


# --- rejecting


async def test_reject_changes_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = await _profile(user)
    edit = await _propose(user, groq, SET_LEVEL)
    response = await user.post(f"/api/profile/edits/{edit['edit_id']}/reject")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert await _profile(user) == before
    url = f"/api/profile/edits/{edit['edit_id']}/confirm"
    assert_problem(await user.post(url), 404, "EDIT_NOT_FOUND")


# --- remove and restore


async def test_remove_needs_no_llm_and_no_quota(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    async with container.sessions() as db:
        await db.execute(update(QuotaUsage).values(requests=20, tokens=5000))
        await db.commit()
    before = await _profile(user)
    response = await user.delete("/api/profile/skills/docker")
    assert response.status_code == 200
    body = response.json()
    assert _skill(body["profile"], "docker") is None
    assert body["profile"]["profile_version"] == before["profile_version"] + 1
    assert groq.requests == []
    [removed] = (await user.get("/api/profile/removed-skills")).json()["skills"]
    assert removed["skill_id"] == "docker"
    assert removed["name_th"]
    assert removed["removed_at"].endswith("+07:00")


async def test_a_removed_skill_leaves_matching(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await user.delete("/api/profile/skills/python")
    matches = (await user.get("/api/roles/matches")).json()
    for role in matches["roles"]:
        assert "python" not in [skill["skill_id"] for skill in role["matched"]]


async def test_removing_what_is_not_there_is_not_found(
    user: httpx.AsyncClient, with_profile: None
) -> None:
    assert_problem(await user.delete("/api/profile/skills/nope"), 404, "SKILL_NOT_FOUND")
    assert_problem(await user.post("/api/profile/skills/nope/restore"), 404, "SKILL_NOT_FOUND")


async def test_restore_brings_back_the_skill_with_its_evidence(
    user: httpx.AsyncClient, with_profile: None
) -> None:
    before = _skill(await _profile(user), "docker")
    await user.delete("/api/profile/skills/docker")
    response = await user.post("/api/profile/skills/docker/restore")
    assert response.status_code == 200
    assert _skill(response.json()["profile"], "docker") == before
    assert (await user.get("/api/profile/removed-skills")).json()["skills"] == []


async def test_generating_again_keeps_a_removed_skill_out(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await user.delete("/api/profile/skills/docker")
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200
    assert _skill(response.json()["profile"], "docker") is None
    sent = groq.requests[0]["messages"][1]["content"]
    assert "Docker" not in sent


async def test_asking_for_a_removed_skill_back_is_flagged(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    before = _skill(await _profile(user), "docker")
    assert before is not None
    await user.delete("/api/profile/skills/docker")
    edit = await _propose(user, groq, {"target": "skill", "op": "add", "skill": "Docker"})
    assert edit["changes"][0]["restores_removed_skill"] is True
    assert edit["changes"][0]["new_value"]["level"] == before["level"]
    assert "เคยลบ" in edit["summary_th"]
    profile = (await _confirm(user, edit["edit_id"]))["profile"]
    docker = _skill(profile, "docker")
    assert docker is not None
    assert docker["edited_by_user"] is True
    assert len(docker["evidence_ids"]) >= 2
    assert (await user.get("/api/profile/removed-skills")).json()["skills"] == []


async def test_a_chat_remove_lands_on_the_removed_list(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(user, groq, {"target": "skill", "op": "remove", "skill": "Docker"})
    await _confirm(user, edit["edit_id"])
    skills = (await user.get("/api/profile/removed-skills")).json()["skills"]
    assert [s["skill_id"] for s in skills] == ["docker"]


# --- generating again


async def test_generating_again_keeps_what_the_user_edited(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    edit = await _propose(
        user,
        groq,
        SET_LEVEL,
        {"target": "skill", "op": "add", "skill": "Figma", "level": 2},
        {"target": "desired_salary", "value": 45000},
        {"target": "work_style", "trait": "teamwork", "score": 5},
    )
    await _confirm(user, edit["edit_id"])
    groq.reply(LLM_SECTIONS)
    profile = (await user.post("/api/profile/generate")).json()["profile"]
    python = _skill(profile, "python")
    assert python is not None
    assert python["level"] == 4
    assert python["edited_by_user"] is True
    assert any("Figma" in s["name_en"] for s in profile["hard_skills"])
    assert profile["preferences"]["desired_salary_thb"] == 45000
    assert profile["preferences"]["work_style"]["teamwork"] == 1
    assert f"ua-{edit['edit_id']}" in profile["evidence"]
    assert all(i in profile["evidence"] for i in python["evidence_ids"])


def test_a_kept_skill_still_cites_a_source_that_is_gone(container: Container) -> None:
    source = {"id": "cv-4", "kind": "cv_line", "label_th": "CV บรรทัด 4", "excerpt": "Docker"}
    other = {"id": "cv-9", "kind": "cv_line", "label_th": "CV บรรทัด 9", "excerpt": "SQL"}
    edited = {"skill_id": "docker", "kind": "hard", "level": 3, "evidence_ids": ["cv-4"]}
    removed = {"skill_id": "sql", "kind": "hard", "level": 2, "evidence_ids": ["cv-9"]}
    previous = {
        "evidence": {"cv-4": source, "cv-9": other},
        "hard_skills": [{**edited, "edited_by_user": True}],
        "soft_skills": [],
    }
    sections: dict[str, Any] = {"evidence": {}, "hard_skills": [], "soft_skills": []}
    questionnaire = questionnaire_for(container.settings)
    kept = keep_user_edits(sections, previous, questionnaire, [removed])
    assert kept["evidence"] == {"cv-4": source, "cv-9": other}
    assert [s["skill_id"] for s in kept["hard_skills"]] == ["docker"]


async def test_restoring_after_generating_again_cites_what_exists(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await user.delete("/api/profile/skills/docker")
    groq.reply(LLM_SECTIONS)
    await user.post("/api/profile/generate")
    profile = (await user.post("/api/profile/skills/docker/restore")).json()["profile"]
    docker = _skill(profile, "docker")
    assert docker is not None
    assert all(i in profile["evidence"] for i in docker["evidence_ids"])


# --- matches after an edit


async def test_an_edit_makes_changed_wording_stale(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    matches = (await user.get("/api/roles/matches")).json()
    groq.reply({"roles": []})
    await user.post("/api/roles/matches/explain")
    response = await user.delete("/api/profile/skills/python")
    after = response.json()["matches"]
    async with container.sessions() as db:
        written = {row.role_id for row in await db.scalars(select(MatchExplanation))}
    assert written >= {m["role_id"] for m in matches["roles"]}
    stale = [m for m in after["roles"] if m["explanations_stale"]]
    assert stale
    assert all(m["next_steps"] == [] for m in stale)


# --- the form


async def test_the_form_changes_preferences_with_no_llm(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    body = {
        "interested_roles": ["qa-engineer"],
        "desired_salary_thb": 50000,
        "locations": ["กรุงเทพมหานคร"],
        "work_style": {"teamwork": 0.25},
    }
    response = await user.patch("/api/profile/preferences", json=body)
    assert response.status_code == 200, response.text
    preferences = response.json()["profile"]["preferences"]
    assert preferences["interested_roles"] == ["qa-engineer"]
    assert preferences["desired_salary_thb"] == 50000
    assert preferences["locations"] == ["กรุงเทพมหานคร"]
    assert preferences["work_style"]["teamwork"] == 0.25
    assert groq.requests == []
    groq.reply(LLM_SECTIONS)
    again = (await user.post("/api/profile/generate")).json()["profile"]
    assert again["preferences"]["desired_salary_thb"] == 50000


@pytest.mark.parametrize(
    "body",
    [{"email": "a@b.c"}, {"profile_version": 9}, {"work_style": {"made-up": 0.5}}],
)
async def test_the_form_refuses_what_is_off_the_allow_list(
    user: httpx.AsyncClient, with_profile: None, body: dict[str, Any]
) -> None:
    response = await user.patch("/api/profile/preferences", json=body)
    assert_problem(response, 422, "EDIT_FIELD_NOT_ALLOWED")


@pytest.mark.parametrize(
    "body",
    [
        {"interested_roles": ["no-such-role"]},
        {"interested_roles": [{"id": "qa-engineer"}]},
        {"desired_salary_thb": 5},
        {"locations": [""]},
        {"work_style": {"teamwork": 2}},
    ],
)
async def test_the_form_refuses_bad_values(
    user: httpx.AsyncClient, with_profile: None, body: dict[str, Any]
) -> None:
    response = await user.patch("/api/profile/preferences", json=body)
    assert_problem(response, 422, "VALIDATION_ERROR")


# --- no profile, login, account


async def test_before_a_profile(user: httpx.AsyncClient) -> None:
    assert (await user.get("/api/profile/edits/pending")).json() == {"edits": []}
    assert (await user.get("/api/profile/removed-skills")).json() == {"skills": []}
    assert_problem(await user.delete("/api/profile/skills/python"), 404, "PROFILE_NOT_FOUND")
    assert_problem(await user.post("/api/profile/skills/python/restore"), 404, "PROFILE_NOT_FOUND")
    response = await user.patch("/api/profile/preferences", json={"locations": []})
    assert_problem(response, 404, "PROFILE_NOT_FOUND")


async def test_everything_needs_a_login(client: httpx.AsyncClient) -> None:
    for response in (
        await client.get("/api/profile/edits/pending"),
        await client.post("/api/profile/edits/x/confirm"),
        await client.post("/api/profile/edits/x/reject"),
        await client.delete("/api/profile/skills/x"),
        await client.post("/api/profile/skills/x/restore"),
        await client.get("/api/profile/removed-skills"),
        await client.patch("/api/profile/preferences", json={}),
    ):
        assert_problem(response, 401, "UNAUTHENTICATED")


async def test_deleting_the_account_deletes_the_edits(
    container: Container, user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await _propose(user, groq, SET_LEVEL)
    await user.delete("/api/profile/skills/docker")
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200
    async with container.sessions() as db:
        assert list(await db.scalars(select(EditProposal))) == []
        assert list(await db.scalars(select(RemovedSkill))) == []


# --- found by testing the running system


async def test_add_and_remove_on_one_list_keeps_both(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await user.patch("/api/profile/preferences", json={"locations": ["Bangkok"]})
    edit = await _propose(
        user,
        groq,
        {"target": "locations", "op": "add", "values": ["เชียงใหม่"]},
        {"target": "locations", "op": "remove", "values": ["Bangkok"]},
    )
    assert edit["changes"][0]["new_value"] == ["เชียงใหม่"]
    assert edit["changes"][0]["old_value"] == ["Bangkok"]


async def test_add_and_remove_that_cancel_out_propose_nothing(
    user: httpx.AsyncClient, groq: Groq, with_profile: None
) -> None:
    await user.patch("/api/profile/preferences", json={"locations": ["Bangkok"]})
    reply = await _ask(
        user,
        groq,
        {"target": "locations", "op": "add", "values": ["เชียงใหม่"]},
        {"target": "locations", "op": "remove", "values": ["เชียงใหม่"]},
    )
    assert reply["edit_proposal"] is None


async def test_removing_a_skill_already_marked_removed_is_not_an_error(
    container: Container, user: httpx.AsyncClient, with_profile: None
) -> None:
    """Left by a remove during generating, on data saved before that was fixed."""
    async with container.sessions() as db:
        profile = await db.scalar(select(Profile).limit(1))
        assert profile is not None
        db.add(
            RemovedSkill(
                user_id=profile.user_id,
                skill_id="python",
                skill={"skill_id": "python", "name_th": "เก่า", "evidence_ids": []},
                removed_at=utcnow(),
            )
        )
        await db.commit()
    response = await user.delete("/api/profile/skills/python")
    assert response.status_code == 200, response.text
    assert (await user.get("/api/profile/removed-skills")).status_code == 200


async def test_restoring_a_skill_whose_source_is_gone_still_cites_something(
    container: Container, user: httpx.AsyncClient, with_profile: None
) -> None:
    async with container.sessions() as db:
        profile = await db.scalar(select(Profile).limit(1))
        assert profile is not None
        db.add(
            RemovedSkill(
                user_id=profile.user_id,
                skill_id="rust",
                skill={
                    "skill_id": "rust",
                    "name_th": "Rust",
                    "name_en": "Rust",
                    "kind": "hard",
                    "level": 2,
                    "evidence_ids": ["ua-gone"],
                    "edited_by_user": True,
                },
                removed_at=utcnow(),
            )
        )
        await db.commit()
    response = await user.post("/api/profile/skills/rust/restore")
    assert response.status_code == 200, response.text
    restored = response.json()["profile"]
    skill = _skill(restored, "rust")
    assert skill is not None
    assert skill["evidence_ids"]
    assert all(i in restored["evidence"] for i in skill["evidence_ids"])
