"""Opt-in 07 -> real 05 HTTP/index/search smoke, with deterministic test embeddings.

RETRIEVAL_TEST_ROOT points at services/05_retrieval_knowledge in a separate checkout.
External football providers and Generation are mocked; no API keys/models are downloaded.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.football import current_season
from app.main import create_app
from tests.test_integration import example_match

BOOTSTRAP = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.api.deps import build_container
from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeEmbedder
import uvicorn
settings = Settings(kb_db_path=sys.argv[2],
    aliases_file=str(Path(sys.argv[1]) / 'data' / 'team_aliases.json'),
    football_data_url='', log_level='WARNING', log_json=False)
container = build_container(settings, embedder=FakeEmbedder())
uvicorn.run(create_app(settings, container), host='127.0.0.1', port=int(sys.argv[3]),
    log_level='warning')
"""


@pytest.mark.asyncio
async def test_real_retrieval_http_ingest_search_publish_and_recovery(tmp_path):
    root = os.getenv("RETRIEVAL_TEST_ROOT")
    if not root:
        pytest.skip("Set RETRIEVAL_TEST_ROOT to run with the real 05 application")
    assert (Path(root) / "app" / "main.py").is_file()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-c", BOOTSTRAP, root, str(tmp_path / "knowledge.db"), str(port)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    season = current_season()
    outage = False
    generation_calls = []
    async with httpx.AsyncClient(base_url=url, timeout=10) as retrieval:
        try:
            async with asyncio.timeout(20):
                while True:
                    if process.poll() is not None:
                        pytest.fail(process.communicate()[0].decode(errors="replace"))
                    try:
                        if (await retrieval.get("/ready")).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.05)

            async def transport(request):
                path = request.url.path
                if request.url.host == "retrieval":
                    if outage:
                        return httpx.Response(503)
                    response = await retrieval.request(
                        request.method, path, content=request.content, headers=request.headers
                    )
                    return httpx.Response(response.status_code, content=response.content)
                if path.endswith("/teams"):
                    return httpx.Response(
                        200,
                        json={
                            "teams": [
                                {"id": 57, "name": "Arsenal FC"},
                                {"id": 61, "name": "Chelsea FC"},
                            ]
                        },
                    )
                if path.endswith("/matches"):
                    return httpx.Response(200, json={"matches": [example_match(season)]})
                if path.endswith("/standings"):
                    return httpx.Response(
                        200,
                        json={
                            "season": {"currentMatchday": 6},
                            "standings": [{"type": "TOTAL", "table": []}],
                        },
                    )
                if path.endswith("/scorers"):
                    return httpx.Response(
                        200,
                        json={
                            "scorers": [
                                {
                                    "player": {"name": "Example Striker"},
                                    "team": {"id": 57},
                                    "goals": 7,
                                    "assists": 2,
                                }
                            ]
                        },
                    )
                if path == "/report/weekly":
                    generation_calls.append(json.loads(request.content))
                    return httpx.Response(
                        200,
                        json={"title": "สรุปผลทดสอบ", "markdown": "รายงานทดสอบ", "highlights": []},
                    )
                raise AssertionError(str(request.url))

            async def search(query, category, week):
                response = await retrieval.post(
                    "/search",
                    json={
                        "request_id": str(uuid4()),
                        "query": query,
                        "mode": "hybrid",
                        "filters": {"season": season, "category": [category], "matchweek": week},
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()["chunks"]

            settings = Settings(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
                football_data_api_key="mock-only",
                index_retry_seconds=0.03,
                index_retry_max_seconds=0.05,
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as upstream:
                app = create_app(settings, http=upstream)
                async with app.router.lifespan_context(app):
                    service = app.state.service
                    legacy = service._documents(
                        [],
                        {"matchweek": 5, "rows": []},
                        season,
                        "2026-09-21T09:00:00+07:00",
                    )[0]
                    legacy["doc_id"] = f"standings-{season}-mw05"
                    assert (
                        await retrieval.post("/index/upsert", json={"documents": [legacy]})
                    ).status_code == 200
                    await service._ingest_primary(str(uuid4()))
                    stats = (await retrieval.get("/index/stats")).json()
                    assert stats["documents"] == 4
                    assert stats["by_category"]["standings"] == 1
                    chunks = await search("Example Striker top scorers 7 goals", "standings", 6)
                    assert any("Example Striker" in chunk["text"] for chunk in chunks)
                    chunks = await search("Arsenal Chelsea 2-1", "match_report", 5)
                    assert any(chunk["source"]["doc_id"].endswith("-57-61") for chunk in chunks)
                    await service._create_report(season, 5, str(uuid4()))
                    assert generation_calls[0]["matchweek"] == 5
                    assert "lineups" in generation_calls[0]["matches"][0]
                    assert "statistics" in generation_calls[0]["matches"][0]
                    await service.edit_report(season, 5, None, "แก้บทความทดสอบ", "beat")
                    await service.publish(season, 5, "beat", str(uuid4()))
                    chunks = await search("Arsenal Chelsea weekly summary", "weekly_report", 5)
                    assert any(
                        chunk["source"]["doc_id"] == f"weekly-{season}-mw05" for chunk in chunks
                    )
                    await service.unpublish(season, 5, "beat", str(uuid4()))
                    assert await search("weekly summary", "weekly_report", 5) == []
                    outage = True
                    await service._ingest_primary(str(uuid4()))
                    assert (await service.status())["index_sync"]["pending"] > 0
                    outage = False
                    async with asyncio.timeout(5):
                        while (await service.status())["index_sync"]["pending"]:
                            await asyncio.sleep(0.01)
                    assert (await retrieval.get("/index/stats")).json()["documents"] == stats[
                        "documents"
                    ]
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
