import pytest

from travel_agent.config import Settings
from travel_agent.tools.live import LiveToolSet

from .conftest import run_body


@pytest.mark.asyncio
async def test_live_05_06_pipeline_reaches_real_07(make_client):
    """03 can pass a real 05 context through real 06 and into real 07.

    Weather and routing hit the real Open-Meteo and OSRM demo services (both
    unauthenticated); transport and disasters are stubbed to keep the run fast and
    independent of TomTom/GDACS availability.
    """
    tools = LiveToolSet(
        transport_fetcher=lambda bbox, *, now, api_key: [],
        disaster_fetcher=lambda *, now: [],
    )
    settings = Settings(
        _env_file=None,
        decision_service_url="http://decision",
        use_mock_tools=False,
    )

    async with make_client(settings, tools=tools) as client:
        response = await client.post("/v1/agent/runs", json=run_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"completed", "partial_result"}
    assert payload["versions"]["risk_model"] == "rule-baseline-v0.1.2"
    # Real OSRM route, not a fixed id: only its shape is pinned here.
    assert payload["routes"]["primary"]["route_id"].startswith("osrm-route-")
