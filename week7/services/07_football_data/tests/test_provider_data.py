"""Validate cached real provider responses without consuming another API request."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.db import ApiQuota, Match
from app.service import ServiceError
from scripts.demo_details import build_demo
from tests.test_outbox import local_service

RAW = Path(__file__).resolve().parents[1] / "data/raw/provider-smoke"


@pytest.mark.asyncio
async def test_plan_error_does_not_retry_or_treat_empty_response_as_success(tmp_path):
    calls = []

    async def transport(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "errors": {"plan": "Free plans do not have access to this season"},
                "response": [],
            },
        )

    async with local_service(tmp_path, transport) as service:
        service.settings.api_football_key = "test-only"
        with pytest.raises(ServiceError, match="API-Football"):
            await service._api_football_get("fixtures", {"season": 2026}, str(uuid4()))
        assert len(calls) == 1
        async with service.sessions() as db:
            assert await db.scalar(select(ApiQuota.used)) == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (RAW / "football-data-matches.json").exists(), reason="Run local provider smoke first"
)
async def test_ingest_cached_real_primary_data(tmp_path):
    indexed = {}

    async def transport(request):
        if request.method == "DELETE":
            return httpx.Response(200)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if request.url.path == "/index/upsert":
            indexed.update({d["doc_id"]: d for d in json.loads(request.content)["documents"]})
            return httpx.Response(200)
        return httpx.Response(
            200,
            json=json.loads((RAW / f"football-data-{endpoint}.json").read_text(encoding="utf-8")),
        )

    async with local_service(tmp_path, transport) as service:
        service.settings.football_data_api_key = "test-only"
        await service._ingest_primary(str(uuid4()))
        async with service.sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Match)) == 380
        assert (await service.status())["index_sync"]["pending"] == 0
        assert any("Current top scorers" in d["text"] for d in indexed.values())


@pytest.mark.skipif(
    not (RAW / "api-football-2024-fixture.json").exists(),
    reason="Run local provider smoke first",
)
def test_real_2024_details_can_be_normalized():
    result = build_demo()
    assert result["season"] == "2024"
    assert result["home"]["team_id"] == 351
    assert result["away"]["team_id"] == 61
    assert result["events"]
    assert result["detail_source"] == "api-football"
    assert result["lineups"]
    assert result["statistics"]
