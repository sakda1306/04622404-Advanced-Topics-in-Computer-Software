"""RAG inside the app: loading, and what each route draws from it (Design.md §4.3, §4.6, §6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.api.deps import Container
from app.rag.index import RagIndex
from app.rag.knowledge import Knowledge
from tests.rag.test_rag import REAL_DATA, FakeEmbedder
from tests.test_profile import LLM_SECTIONS, Groq, _ready


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {
        "groq_api_key": "k",
        "groq_model": "main-model",
        "groq_router_model": "router-model",
        "groq_fallback_model": "router-model",
        "quota_daily_requests": 20,
        "quota_daily_tokens": 50000,
        "data_dir": "../data",
    }


@pytest.fixture
def groq(container: Container) -> Groq:
    return Groq(container)


@pytest.fixture
def knowledge(container: Container, tmp_path: Path) -> Knowledge:
    index = RagIndex(
        data_dir=str(REAL_DATA), db_path=str(tmp_path / "rag.db"), embedder=FakeEmbedder()
    )
    index.build()
    container.knowledge = Knowledge(index)
    return container.knowledge


async def _profile(container: Container, user: httpx.AsyncClient, groq: Groq) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    response = await user.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    groq.requests.clear()


def _facts(groq: Groq) -> dict[str, Any]:
    return json.loads(groq.requests[-1]["messages"][1]["content"])


# --- loading and failing


async def test_a_search_before_the_index_is_ready_finds_nothing() -> None:
    assert await Knowledge().search("อะไรก็ได้") == []


def test_no_model_set_leaves_it_off(container: Container) -> None:
    knowledge = Knowledge()
    knowledge.load(container.settings)
    assert knowledge.ready is False


def test_a_model_that_fails_to_load_leaves_it_off(
    container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_name: str) -> None:
        raise OSError("no network")

    monkeypatch.setattr("app.rag.embedder.SentenceTransformerEmbedder", fail)
    settings = container.settings.model_copy(update={"embed_model": "some-model"})
    knowledge = Knowledge()
    knowledge.load(settings)
    assert knowledge.ready is False


async def test_a_failed_search_finds_nothing() -> None:
    class Broken:
        def search(self, *_args: Any, **_kwargs: Any) -> list[Any]:
            raise RuntimeError("broken")

    assert await Knowledge(Broken()).search("อะไรก็ได้") == []  # type: ignore[arg-type]


async def test_a_search_uses_the_filters(knowledge: Knowledge) -> None:
    hits = await knowledge.search("ทดสอบซอฟต์แวร์", category="learning_path", role_id="qa-engineer")
    assert [hit.chunk.chunk_id for hit in hits] == ["role-qa-engineer#learning_path"]
    assert hits[0].chunk.status == "reviewed"


# --- work style


async def test_work_style_cites_the_notes_it_found_without_an_llm_call(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _profile(container, user, groq)
    body = (await user.post("/api/chat", json={"message": "สไตล์การทำงานของผมเป็นยังไง"})).json()
    assert body["route"] == "work_style"
    assert "ความหมายในการทำงาน:" in body["answer"]
    assert "[1]" in body["answer"]
    assert "ไม่ใช่การวินิจฉัยบุคลิกภาพ" in body["answer"]
    source = body["sources"][0]
    assert source["evidence_id"].startswith("rag-work_style#")
    assert "ยังไม่ได้ตรวจทาน" in source["label_th"]
    assert source["url"].startswith("https://")
    assert body["tokens_used"] == 0
    assert groq.requests == []


async def test_work_style_without_the_index_still_answers(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _profile(container, user, groq)
    body = (await user.post("/api/chat", json={"message": "สไตล์การทำงานของผมเป็นยังไง"})).json()
    assert "ความหมายในการทำงาน" not in body["answer"]
    assert body["sources"] == []


# --- routes the LLM words


async def test_job_matching_can_cite_the_learning_path_of_the_top_role(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _profile(container, user, groq)
    top = (await user.get("/api/roles/matches")).json()["roles"][0]["role_id"]
    chunk = f"rag-role-{top}#learning_path"
    groq.reply({"claims": [{"text_th": "ลองทำโปรเจกต์ฝึกหัด", "evidence_ids": [chunk]}]})
    body = (await user.post("/api/chat", json={"message": "ผมควรเรียนอะไรต่อ"})).json()
    assert body["route"] == "job_matching"
    [note] = _facts(groq)["facts"]["notes"]
    assert note["evidence_ids"] == [chunk]
    assert len(note["text"]) <= 600
    assert "ลองทำโปรเจกต์ฝึกหัด" in body["answer"]
    source = next(s for s in body["sources"] if s["evidence_id"] == chunk)
    assert source["url"].startswith("http")


async def test_blind_spots_get_notes_on_missing_soft_skills(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _profile(container, user, groq)
    groq.reply({"claims": []})
    body = (await user.post("/api/chat", json={"message": "จุดอ่อนของผมคืออะไร"})).json()
    assert body["route"] == "blind_spots"
    notes = _facts(groq)["facts"]["notes"]
    assert notes
    assert all(n["evidence_ids"][0].startswith("rag-soft_skills#") for n in notes)


async def test_a_note_id_the_route_did_not_retrieve_cannot_be_cited(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _profile(container, user, groq)
    claim = {"text_th": "ลองทำโปรเจกต์ฝึกหัด", "evidence_ids": ["rag-role-other#learning_path"]}
    groq.reply({"claims": [claim]})
    body = (await user.post("/api/chat", json={"message": "ผมควรเรียนอะไรต่อ"})).json()
    assert "ลองทำโปรเจกต์ฝึกหัด" not in body["answer"]


async def test_skill_assessment_uses_no_notes(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _profile(container, user, groq)
    groq.reply({"claims": []})
    await user.post("/api/chat", json={"message": "ทักษะของผมเป็นยังไง"})
    assert "notes" not in _facts(groq)["facts"]


async def test_routes_without_the_index_send_no_notes(
    container: Container, user: httpx.AsyncClient, groq: Groq
) -> None:
    await _profile(container, user, groq)
    groq.reply({"claims": []})
    await user.post("/api/chat", json={"message": "ผมควรเรียนอะไรต่อ"})
    assert "notes" not in _facts(groq)["facts"]


# --- next steps


async def test_next_steps_get_the_learning_path_and_soft_skill_notes(
    container: Container, user: httpx.AsyncClient, groq: Groq, knowledge: Knowledge
) -> None:
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    groq.reply({"roles": []})
    assert (await user.post("/api/profile/generate")).status_code == 200
    facts = _facts(groq)["roles"]
    for role in facts:
        assert "Learning path" in role["learning_path"]  # the heading only the chunk starts with
        soft = [gap for gap in role["gaps"] if gap["kind"] == "soft_skill"]
        assert bool(role.get("soft_skill_notes")) == bool(soft)


def test_the_note_chunks_carry_their_status() -> None:
    from app.rag.chunking import load_chunks

    notes = [c for c in load_chunks(str(REAL_DATA)) if c.category == "work_style"]
    assert {c.status for c in notes} == {"draft"}
