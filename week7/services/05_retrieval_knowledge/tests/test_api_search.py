"""POST /search and GET /ready against the sample knowledge base (CONTRACT §4)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from tests.conftest import assert_problem
from tests.fakes import FakeEmbedder

CHUNK_KEYS = {"chunk_id", "text", "score", "bm25_score", "vector_score", "rerank_score", "source"}
SOURCE_KEYS = {
    "ref",
    "doc_id",
    "title",
    "category",
    "origin",
    "season",
    "matchweek",
    "team_ids",
    "fetched_at",
    "url",
    "topic",
}


async def search(client: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await client.post("/search", json=body)


async def test_ready_reports_the_loaded_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunks"] == 9
    assert body["index_version"].endswith("+07:00")


async def test_not_ready_until_the_index_is_loaded(unloaded_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=unloaded_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        assert (await c.get("/ready")).status_code == 503
        assert (await c.get("/health")).status_code == 200
        assert_problem(await c.post("/search", json={"query": "Arsenal"}), 503, "INDEX_NOT_READY")


async def test_response_matches_the_contract(client: httpx.AsyncClient) -> None:
    response = await search(client, request_id="req-1", query="Arsenal Chelsea result", top_k=3)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "chunks", "latency_ms", "index_version"}
    assert body["request_id"] == "req-1"
    assert len(body["chunks"]) == 3
    first = body["chunks"][0]
    assert set(first) == CHUNK_KEYS
    assert set(first["source"]) == SOURCE_KEYS
    assert first["source"]["doc_id"] == "match-2026-mw05-57-61"
    assert first["source"]["title"] == "Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5"
    assert first["rerank_score"] is None
    assert [c["source"]["ref"] for c in body["chunks"]] == [1, 2, 3]
    scores = [c["score"] for c in body["chunks"]]
    assert scores == sorted(scores, reverse=True)


async def test_request_id_falls_back_to_the_header(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/search", json={"query": "Arsenal"}, headers={"X-Request-ID": "hdr-7"}
    )
    assert response.json()["request_id"] == "hdr-7"


async def test_trivia_source_has_null_live_fields(client: httpx.AsyncClient) -> None:
    body = (await search(client, query="Ballon d'Or 2008 winner", mode="bm25")).json()
    source = body["chunks"][0]["source"]
    assert source["doc_id"] == "trivia-0001"
    assert source["category"] == "trivia"
    assert (source["season"], source["fetched_at"], source["team_ids"]) == (None, None, [])
    assert source["topic"] == "Ballon d'Or"


async def test_filters_apply(client: httpx.AsyncClient) -> None:
    body = (await search(client, query="Arsenal", filters={"category": ["standings"]})).json()
    assert body["chunks"]
    assert {c["source"]["category"] for c in body["chunks"]} == {"standings"}


async def test_topic_filter_applies(client: httpx.AsyncClient) -> None:
    body = (await search(client, query="World Cup Spain", filters={"topic": ["World Cup"]})).json()
    assert body["chunks"]
    assert {c["source"]["topic"] for c in body["chunks"]} == {"World Cup"}


async def test_nothing_found_is_200_with_no_chunks(client: httpx.AsyncClient) -> None:
    response = await search(client, query="Arsenal", filters={"season": "1999"})
    assert response.status_code == 200
    assert response.json()["chunks"] == []


async def test_thai_only_query_is_answered(client: httpx.AsyncClient) -> None:
    response = await search(client, query="ปืนใหญ่ชนะไหม")
    assert response.status_code == 200
    assert 57 in response.json()["chunks"][0]["source"]["team_ids"]


@pytest.mark.parametrize("mode", ["hybrid", "bm25", "vector"])
async def test_every_mode_answers(client: httpx.AsyncClient, mode: str) -> None:
    response = await search(client, query="World Cup Spain", mode=mode)
    assert response.status_code == 200
    assert response.json()["chunks"]


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "Arsenal\u0000"},
        {"query": "Arsenal", "query_original": "ปืน\u0000"},
        {"query": "Arsenal", "top_k": 0},
        {"query": "Arsenal", "top_k": 21},
        {"query": "Arsenal", "mode": "semantic"},
        {"query": "Arsenal", "filters": {"category": []}},
        {"query": "Arsenal", "filters": {"category": ["news"]}},
        {"query": "Arsenal", "filters": {"colour": "red"}},
        {"query": "Arsenal", "filters": {"season": "26"}},
        {"query": "Arsenal", "filters": {"matchweek": 39}},
        {"query": "Arsenal", "filters": {"date_from": "2026-09-22", "date_to": "2026-09-20"}},
        {"query": "Arsenal", "filters": {"date_from": "yesterday"}},
        {"query": "Arsenal", "filters": {"topic": []}},
        {"query": "Arsenal", "filters": {"topic": [""]}},
    ],
)
async def test_invalid_requests_are_422(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    assert_problem(await client.post("/search", json=body), 422, "VALIDATION_ERROR")


async def test_null_filters_mean_no_filter(client: httpx.AsyncClient) -> None:
    # A caller that dumps an optional model without dropping None sends "filters": null.
    response = await search(client, query="Arsenal Chelsea", filters=None)
    assert response.status_code == 200
    assert response.json()["chunks"]


async def test_unknown_top_level_key_is_422(client: httpx.AsyncClient) -> None:
    # "filter" instead of "filters" must not return unfiltered results.
    response = await search(client, query="Arsenal", filter={"category": ["standings"]})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_vector_side_embeds_the_english_query(
    client: httpx.AsyncClient, embedder: FakeEmbedder
) -> None:
    # CONTRACT §4 v1.2: `query` (the router's English rewrite) goes to the vector side;
    # `query_original` is only searched for team nicknames.
    response = await search(
        client, query="Arsenal latest result", query_original="เมื่อวานปืนใหญ่ชนะไหม", mode="vector"
    )
    assert response.status_code == 200
    assert embedder.calls[-1] == ["Arsenal latest result"]


def test_reranking_is_off_by_default() -> None:
    assert Settings.model_fields["rerank_model"].default == ""
