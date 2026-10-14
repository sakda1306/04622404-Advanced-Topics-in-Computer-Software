"""Index management endpoints (CONTRACT §6): upsert, delete, stats, rebuild and its jobs."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import Container
from tests.conftest import assert_problem
from tests.samples import SAMPLE_CHUNK_COUNT

NEW_MATCH: dict[str, Any] = {
    "doc_id": "match-2026-mw06-64-65",
    "title": "Liverpool 3–0 Manchester City · PL 2026/27 นัดที่ 6",
    "text": "Premier League 2026/27, matchweek 6. Liverpool 3-0 Manchester City at Anfield.",
    "category": "match_report",
    "origin": "api-football",
    "season": "2026",
    "matchweek": 6,
    "team_ids": [64, 65],
    "date": "2026-09-27",
    "fetched_at": "2026-09-28T09:00:00+07:00",
    "url": None,
}


def doc(**changes: Any) -> dict[str, Any]:
    return {**NEW_MATCH, **changes}


async def upsert(client: httpx.AsyncClient, *documents: dict[str, Any]) -> httpx.Response:
    return await client.post(
        "/index/upsert", json={"request_id": "req-1", "documents": list(documents)}
    )


async def doc_ids_found(client: httpx.AsyncClient, query: str) -> list[str]:
    response = await client.post("/search", json={"query": query, "top_k": 20})
    return [c["source"]["doc_id"] for c in response.json()["chunks"]]


async def test_upsert_matches_contract_and_is_searchable(client: httpx.AsyncClient) -> None:
    response = await upsert(client, NEW_MATCH)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "upserted", "chunks", "index_version"}
    assert (body["request_id"], body["upserted"], body["chunks"]) == ("req-1", 1, 1)
    assert NEW_MATCH["doc_id"] in await doc_ids_found(client, "Liverpool Manchester City Anfield")

    search = await client.post("/search", json={"query": "Anfield"})
    assert search.json()["index_version"] == body["index_version"]


async def test_upserting_the_same_doc_id_keeps_only_the_latest(
    client: httpx.AsyncClient, container: Container
) -> None:
    await upsert(client, NEW_MATCH)
    response = await upsert(client, doc(text="Liverpool 4-0 Manchester City after extra goals."))
    assert response.json()["upserted"] == 1
    snapshot = container.index.snapshot
    assert snapshot is not None
    texts = [r.document.text for r in snapshot.records if r.chunk.doc_id == NEW_MATCH["doc_id"]]
    assert texts == ["Liverpool 4-0 Manchester City after extra goals."]
    stored = [s for s in container.store.load_all() if s.chunk.doc_id == NEW_MATCH["doc_id"]]
    assert [s.document.text for s in stored] == texts


async def test_unchanged_upsert_keeps_the_version(client: httpx.AsyncClient) -> None:
    first = (await upsert(client, NEW_MATCH)).json()
    again = (await upsert(client, NEW_MATCH)).json()
    assert again["index_version"] == first["index_version"]


async def test_request_id_defaults_to_the_header(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/index/upsert", json={"documents": [NEW_MATCH]}, headers={"X-Request-ID": "hdr-9"}
    )
    assert response.json()["request_id"] == "hdr-9"


@pytest.mark.parametrize(
    "document",
    [
        doc(doc_id="match-2026-mw6-64-65"),
        doc(doc_id="standings-2026-mw06"),
        doc(category="player"),  # a match doc_id is not a player doc_id
        doc(category="player", doc_id="players-2026-team-57-extra"),
        doc(category="news"),
        doc(origin="twitter"),
        doc(text=""),
        doc(text="   "),
        doc(title=""),
        doc(text="Liverpool\u0000"),
        doc(season="26"),
        doc(matchweek=39),
        doc(date="yesterday"),
        doc(colour="red"),
        {k: v for k, v in NEW_MATCH.items() if k != "text"},
    ],
)
async def test_invalid_documents_are_422(
    client: httpx.AsyncClient, container: Container, document: dict[str, Any]
) -> None:
    before = container.index.snapshot
    response = await upsert(client, NEW_MATCH | {"doc_id": "match-2026-mw06-1-2"}, document)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert container.index.snapshot is before


@pytest.mark.parametrize(
    "body",
    [
        {"documents": []},
        {"documents": [doc(doc_id=f"match-2026-mw06-{i}-1") for i in range(101)]},
        {"documents": [NEW_MATCH], "extra": 1},
        {},
    ],
)
async def test_invalid_upsert_bodies_are_422(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    assert_problem(await client.post("/index/upsert", json=body), 422, "VALIDATION_ERROR")


async def test_delete_removes_the_document_from_search(client: httpx.AsyncClient) -> None:
    await upsert(client, NEW_MATCH)
    response = await client.delete(f"/index/{NEW_MATCH['doc_id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert NEW_MATCH["doc_id"] not in await doc_ids_found(client, "Liverpool Manchester City")


async def test_deleting_again_is_false(client: httpx.AsyncClient) -> None:
    await upsert(client, NEW_MATCH)
    await client.delete(f"/index/{NEW_MATCH['doc_id']}")
    before = (await client.get("/index/stats")).json()["index_version"]
    response = await client.delete(f"/index/{NEW_MATCH['doc_id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted": False}
    assert (await client.get("/index/stats")).json()["index_version"] == before


async def test_stats_match_the_store_and_the_snapshot(
    client: httpx.AsyncClient, container: Container
) -> None:
    await upsert(client, NEW_MATCH)
    response = await client.get("/index/stats")
    assert response.status_code == 200
    body = response.json()
    stored = container.store.load_all()
    snapshot = container.index.snapshot
    assert snapshot is not None
    assert body == {
        "documents": 7,
        "chunks": SAMPLE_CHUNK_COUNT + 1,
        "by_category": {"trivia": 3, "match_report": 2, "standings": 1, "fixtures": 1},
        "index_version": snapshot.index_version,
    }
    assert body["chunks"] == len(stored) == snapshot.faiss_count == snapshot.bm25_count
    assert body["documents"] == len({s.chunk.doc_id for s in stored})


async def test_stats_before_the_index_loads_are_503(unloaded_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=unloaded_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        assert_problem(await c.get("/index/stats"), 503, "INDEX_NOT_READY")


async def finished_job(client: httpx.AsyncClient, container: Container, job_id: str) -> Any:
    await container.jobs.wait()
    response = await client.get(f"/index/jobs/{job_id}")
    assert response.status_code == 200
    return response.json()


async def test_rebuild_is_accepted_and_the_job_can_be_followed(
    client: httpx.AsyncClient, container: Container
) -> None:
    before = (await client.get("/index/stats")).json()
    response = await client.post("/index/rebuild", json={"request_id": "req-2"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert set(response.json()) == {"job_id"}

    job = await finished_job(client, container, job_id)
    assert set(job) == {"job_id", "status", "started_at", "finished_at", "detail"}
    assert (job["job_id"], job["status"]) == (job_id, "done")
    after = (await client.get("/index/stats")).json()
    assert after["index_version"] != before["index_version"]
    assert {k: after[k] for k in ("documents", "chunks", "by_category")} == {
        k: before[k] for k in ("documents", "chunks", "by_category")
    }
    assert "match-2026-mw05-57-61" in await doc_ids_found(client, "Arsenal Chelsea Saka")


async def test_rebuild_of_one_category(client: httpx.AsyncClient, container: Container) -> None:
    response = await client.post("/index/rebuild", json={"category": "standings"})
    job = await finished_job(client, container, response.json()["job_id"])
    assert (job["status"], job["detail"]) == ("done", "1 documents, 2 chunks")


async def test_rebuild_while_one_runs_is_409(
    client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()

    async def slow_rebuild(_category: str | None) -> Any:
        started.set()
        await finish.wait()
        raise RuntimeError("stopped by the test")

    monkeypatch.setattr(container.index, "rebuild", slow_rebuild)
    first = await client.post("/index/rebuild", json={})
    await started.wait()
    running = (await client.get(f"/index/jobs/{first.json()['job_id']}")).json()
    assert running["status"] == "running"
    assert running["finished_at"] is None
    assert_problem(await client.post("/index/rebuild", json={}), 409, "JOB_ALREADY_RUNNING")
    finish.set()
    job = await finished_job(client, container, first.json()["job_id"])
    assert (job["status"], job["detail"]) == ("failed", "RuntimeError")


@pytest.mark.parametrize(
    "body", [{"category": "news"}, {"category": ["trivia"]}, {"categories": "trivia"}]
)
async def test_invalid_rebuild_bodies_are_422(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    assert_problem(await client.post("/index/rebuild", json=body), 422, "VALIDATION_ERROR")


async def test_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/index/jobs/no-such-job"), 404, "NOT_FOUND")


async def test_rebuild_before_the_index_loads_is_503(unloaded_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=unloaded_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        assert_problem(await c.post("/index/rebuild", json={}), 503, "INDEX_NOT_READY")


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/index/upsert", {"documents": [NEW_MATCH]}),
        ("DELETE", "/index/match-2026-mw06-64-65", None),
    ],
)
async def test_writes_before_the_index_loads_are_503(
    unloaded_app: FastAPI, method: str, path: str, body: dict[str, Any] | None
) -> None:
    # 07 treats a failed index write as a failed job and retries it (CONTRACT §6).
    transport = httpx.ASGITransport(app=unloaded_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        response = await c.request(method, path, json=body)
        assert_problem(response, 503, "INDEX_NOT_READY")


def football_data_payload() -> list[dict[str, Any]]:
    """Documents in the shape 07 (#6) builds them: `_documents()` and `report_doc()`."""
    common = {"season": "2026", "fetched_at": "2026-09-28T09:00:00+07:00", "url": None}
    return [
        {
            **common,
            "doc_id": "match-2026-mw06-58-57",
            "title": "Aston Villa FC 0-2 Arsenal FC",
            "text": "Premier League 2026, matchweek 6. Aston Villa FC 0-2 Arsenal FC. "
            "Kickoff: 2026-09-27T21:00:00+07:00.",
            "category": "match_report",
            "origin": "football-data.org",
            "matchweek": 6,
            "team_ids": [58, 57],
            "date": "2026-09-27",
        },
        {
            **common,
            "doc_id": "standings-2026-mw06",
            "title": "Premier League 2026 standings after matchweek 6",
            "text": "## Standings\n1. Arsenal FC: 16 points, played 6, goal difference 9\n"
            "2. Liverpool FC: 15 points, played 6, goal difference 8",
            "category": "standings",
            "origin": "football-data.org",
            "matchweek": 6,
            "team_ids": [57, 64],
            "date": "2026-09-28",
        },
        {
            # A team with no scheduled match left: 07 sends only the heading.
            **common,
            "doc_id": "fixtures-2026-team-58",
            "title": "Premier League 2026 fixtures for team 58",
            "text": "## Upcoming fixtures\n",
            "category": "fixtures",
            "origin": "football-data.org",
            "matchweek": None,
            "team_ids": [58],
            "date": "2026-09-28",
        },
        {
            **common,
            "doc_id": "weekly-2026-mw06",
            "title": "Premier League weekly report · matchweek 6",
            "text": "## Summary\nArsenal won 2-0 at Aston Villa.",
            "category": "weekly_report",
            "origin": "generated",
            "matchweek": 6,
            "team_ids": [],
            "date": "2026-09-28",
        },
    ]


async def test_documents_from_football_data_round_trip(client: httpx.AsyncClient) -> None:
    before = (await client.get("/index/stats")).json()
    response = await upsert(client, *football_data_payload())
    assert response.status_code == 200, response.text
    assert response.json()["upserted"] == 4
    assert (await client.get("/index/stats")).json()["documents"] == before["documents"] + 4
    found = await client.post(
        "/search",
        json={
            "query": "Aston Villa vs Arsenal result",
            "query_original": "วิลล่าเจอปืนใหญ่ผลเป็นไง",
            "filters": {"category": ["match_report"], "matchweek": 6},
        },
    )
    assert found.json()["chunks"][0]["source"]["doc_id"] == "match-2026-mw06-58-57"
    # Re-ingesting the same documents changes nothing.
    again = await upsert(client, *football_data_payload())
    assert again.json()["index_version"] == response.json()["index_version"]
    # Unpublishing the weekly report removes it.
    assert (await client.delete("/index/weekly-2026-mw06")).json() == {"deleted": True}
    assert (await client.get("/index/stats")).json()["documents"] == before["documents"] + 3


PLAYER_DOC: dict[str, Any] = {
    "doc_id": "players-2026-team-57",
    "title": "Arsenal FC squad 2026",
    "text": (
        "Premier League 2026 squad: Arsenal FC. Coach: Mikel Arteta.\n\n"
        "## Martin Ødegaard\n"
        "Team: Arsenal FC. Position: Midfielder. Date of birth: 1998-12-17. "
        "Nationality: Norway.\n\n"
        "## Bukayo Saka\n"
        "Team: Arsenal FC. Position: Winger. Date of birth: 2001-09-05. "
        "Nationality: England."
    ),
    "category": "player",
    "origin": "football-data.org",
    "season": "2026",
    "matchweek": None,
    "team_ids": [57],
    "date": "2026-09-30",
    "fetched_at": "2026-09-30T10:00:00+07:00",
    "url": None,
}


async def test_player_documents_are_indexed_one_chunk_per_player_and_filterable(
    client: httpx.AsyncClient,
) -> None:
    response = await upsert(client, PLAYER_DOC)
    assert response.status_code == 200, response.text
    assert response.json()["upserted"] == 1
    assert response.json()["chunks"] == 3  # the coach preamble plus one chunk per player

    stats = (await client.get("/index/stats")).json()
    assert stats["by_category"]["player"] == 1

    found = await client.post(
        "/search",
        json={
            "query": "Saka position",
            "filters": {"category": ["player"], "team_ids": [57]},
        },
    )
    chunks = found.json()["chunks"]
    assert chunks
    assert {c["source"]["doc_id"] for c in chunks} == {"players-2026-team-57"}
    assert chunks[0]["source"]["category"] == "player"
    assert "Saka" in chunks[0]["text"]

    excluded = await client.post(
        "/search",
        json={"query": "Saka position", "filters": {"category": ["match_report"]}},
    )
    assert "players-2026-team-57" not in {c["source"]["doc_id"] for c in excluded.json()["chunks"]}


async def test_player_document_can_be_replaced_and_deleted(client: httpx.AsyncClient) -> None:
    await upsert(client, PLAYER_DOC)
    smaller = {**PLAYER_DOC, "text": PLAYER_DOC["text"].split("\n\n## Bukayo Saka")[0]}
    replaced = await upsert(client, smaller)
    assert replaced.json()["chunks"] == 2  # preamble + Martin only: no stale Saka chunk
    assert (await client.delete("/index/players-2026-team-57")).json() == {"deleted": True}


HISTORICAL_DOC: dict[str, Any] = {
    "doc_id": "hist-team-2015-leicester-city",
    "title": "Leicester City FC — Premier League 2015/16",
    "text": (
        "Final position: 1. P38 W23 D12 L3 GF68 GA36 GD+32 Pts81.\n"
        "## Sources and license\nSources: openfootball/england (CC0 1.0)."
    ),
    "category": "historical",
    "origin": "openfootball",
    "topic": "team_season",
    "season": "2015",
    "matchweek": None,
    "team_ids": [],
    "date": None,
    "fetched_at": None,
    "url": "https://github.com/openfootball/england",
}


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"doc_id": "hist-season-2004", "topic": "season_table", "origin": "fjelstul"},
        {
            "doc_id": "hist-h2h-manchester-united-nottm-forest",
            "topic": "head_to_head",
            "season": None,
        },
        {"doc_id": "hist-club-leicester-city", "topic": "club_record", "season": None},
        {"doc_id": "hist-records", "topic": "league_records", "season": None},
    ],
)
async def test_historical_documents_are_accepted_and_filterable(
    client: httpx.AsyncClient, changes: dict[str, Any]
) -> None:
    document = {**HISTORICAL_DOC, **changes}
    response = await upsert(client, document)
    assert response.status_code == 200, response.text
    assert (await client.get("/index/stats")).json()["by_category"]["historical"] == 1
    found = await client.post(
        "/search",
        json={"query": "Leicester 2015/16 points", "filters": {"category": ["historical"]}},
    )
    assert {c["source"]["doc_id"] for c in found.json()["chunks"]} == {document["doc_id"]}


@pytest.mark.parametrize(
    "doc_id",
    [
        "hist-season-04",
        "hist-team-2004-Arsenal",
        "hist-team-2004",
        "hist-h2h-arsenal_chelsea",
        "hist-club-",
        "hist-records-2025",
        "hist-club-Leicester",
        "trivia-0001",
    ],
)
async def test_historical_doc_ids_keep_their_locked_format(
    client: httpx.AsyncClient, doc_id: str
) -> None:
    response = await upsert(client, {**HISTORICAL_DOC, "doc_id": doc_id})
    assert response.status_code == 422


async def test_wikidata_documents_are_accepted(client: httpx.AsyncClient) -> None:
    coach = doc(
        doc_id="coach-2026-team-66",
        category="player",
        origin="wikidata",
        matchweek=None,
        team_ids=[66],
        text="Who is the head coach of Manchester United FC? Michael Carrick.",
    )
    response = await upsert(client, coach)
    assert response.status_code == 200
    found = await doc_ids_found(client, "Manchester United head coach Carrick")
    assert "coach-2026-team-66" in found
