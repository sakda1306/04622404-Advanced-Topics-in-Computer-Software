import httpx
import pytest

from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_health_status_and_not_found(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.json() == {
                "status": "ok",
                "service": "football-data",
                "version": "0.1.0",
            }
            response = await client.get("/football/status")
            assert response.status_code == 200
            assert response.json()["quota"]["api_football_limit"] == 90
            missing = await client.get("/football/standings")
            assert missing.status_code == 404
            assert missing.headers["content-type"].startswith("application/problem+json")
            assert missing.json()["code"] == "NOT_FOUND"
            assert missing.json()["request_id"] == missing.headers["X-Request-ID"]
            unsupported = await client.post(
                "/ingest/run", json={"scope": "details", "triggered_by": "beat"}
            )
            assert unsupported.status_code == 502
            assert unsupported.json()["code"] == "UPSTREAM_UNAVAILABLE"
            assert (await client.get("/jobs")).json()["jobs"] == []
