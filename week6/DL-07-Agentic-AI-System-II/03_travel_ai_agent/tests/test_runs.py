"""End-to-end runs against the real Module 07 engine with mock 04/05/06 tools."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from travel_agent.contracts import AgentRunResponse
from travel_agent.tools.mocks import MockToolSet
from travel_agent.tools.schemas import TravelQuery, WeatherResult

from .conftest import run_body

RUNS = "/v1/agent/runs"


async def post(client, body, **headers):
    return await client.post(RUNS, json=body, headers=headers)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (None, "TRAVEL_NORMALLY"),
        ("high_risk", "AVOID_TRAVEL"),
        ("closure", "AVOID_TRAVEL"),
        ("safer_route", "CHANGE_ROUTE"),
        ("safer_time", "DELAY_TRAVEL"),
    ],
)
async def test_scenarios_reach_module_07_decision(client, scenario, expected):
    body = run_body(scenario)
    response = await post(client, body)

    assert response.status_code == 200, response.text
    result = AgentRunResponse.model_validate(response.json())
    assert str(result.run_id) == body["run_id"]
    assert result.status == "completed"
    assert result.recommendation.type == expected
    assert result.sources, "every recommendation must cite evidence"
    assert {s.value for s in result.service_status.values()} == {"ok"}
    # 04 x4 (weather, transport, disasters, route candidates), 05, 06 x3, 07.
    assert result.diagnostics.tool_calls == 9


async def test_service_status_uses_backend_d47_keys(client):
    status = (await post(client, run_body())).json()["service_status"]
    # Module 02 displays these D-47 keys; any others are passed along and ignored.
    assert {"weather", "transport", "disaster", "risk_model", "rag"} <= status.keys()
    assert not {"risk", "knowledge"} & status.keys()
    assert "llm" not in status  # not reported until there is a real LLM planner


async def test_avoid_passes_module_07_emergency_instructions_through(client):
    # 02's gate rule R-01 rejects a HIGH-risk answer without emergency instructions.
    result = (await post(client, run_body("closure"))).json()

    assert result["recommendation"]["type"] == "AVOID_TRAVEL"
    emergency = result["emergency_instructions"]
    assert emergency is not None, "07 sends guidance with AVOID; the agent must forward it"
    assert emergency["what_to_do_now"]
    assert emergency["nearest_support"] == []
    for contact in emergency["contacts"]:
        assert contact.keys() <= {"name", "phone", "url", "available_hours"}


async def test_non_avoid_actions_carry_no_emergency_instructions(client):
    result = (await post(client, run_body())).json()
    assert result["recommendation"]["type"] == "TRAVEL_NORMALLY"
    assert result["emergency_instructions"] is None


async def test_closure_reports_the_hazard(client):
    result = (await post(client, run_body("closure"))).json()
    assert [h["type"] for h in result["hazards"]] == ["FLOOD"]
    assert result["routes"]["primary"]["restrictions"] == ["NOT_USABLE"]


async def test_safer_time_passes_suggested_departure(client):
    result = (await post(client, run_body("safer_time"))).json()
    assert result["recommendation"]["suggested_departure_time"] is not None


async def test_failed_provider_gives_partial_result(client):
    result = (await post(client, run_body("weather_down"))).json()
    assert result["status"] == "partial_result"
    assert result["service_status"]["weather"] == "unavailable"
    # Missing data never reads as safe: 07 escalates to AVOID.
    assert result["recommendation"]["type"] == "AVOID_TRAVEL"


async def test_invalid_tool_data_is_treated_as_unavailable(make_client):
    class BadWeather(MockToolSet):
        async def weather(self, query: TravelQuery) -> WeatherResult:
            good = await super().weather(query)
            record = good.records[0].model_dump()
            record["url"] = "http://insecure.example.org"  # 07 requires HTTPS
            return WeatherResult.model_validate({"summary": "x", "records": [record]})

    client = make_client(tools=BadWeather())
    result = (await post(client, run_body())).json()
    assert result["service_status"]["weather"] == "unavailable"
    assert result["status"] == "partial_result"


async def test_same_origin_and_destination_asks_instead_of_guessing(client):
    body = run_body()
    body["request"]["destination"] = body["request"]["origin"]
    result = (await post(client, body)).json()
    assert result["status"] == "needs_clarification"
    assert result["clarification"]["missing_fields"] == ["destination"]
    assert result["recommendation"] is None
    assert result["diagnostics"]["tool_calls"] == 0


async def test_ndjson_streams_progress_then_result(client):
    response = await client.post(RUNS, json=run_body(), headers={"Accept": "application/x-ndjson"})
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [line["type"] for line in lines] == ["progress", "progress", "progress", "result"]
    assert [line["stage"] for line in lines[:3]] == [
        "fetching_data",
        "assessing_risk",
        "generating_advice",
    ]
    assert lines[-1]["recommendation"]["type"] == "TRAVEL_NORMALLY"


async def test_tool_call_limit_stops_the_run(client):
    body = run_body()
    body["limits"]["max_tool_calls"] = 3
    response = await post(client, body)
    assert response.status_code == 504
    assert response.json()["code"] == "BUDGET_EXCEEDED"


async def test_past_deadline_is_rejected(client):
    response = await post(client, run_body(), **{"X-Deadline": "2000-01-01T00:00:00Z"})
    assert response.status_code == 504
    assert response.json()["code"] == "DEADLINE_EXCEEDED"


async def test_decision_service_down_is_503(make_client):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    down = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://decision")
    response = await post(make_client(decision=down), run_body())
    assert response.status_code == 503
    assert response.json()["code"] == "DECISION_UNAVAILABLE"


async def test_ndjson_error_line_when_decision_is_down(make_client):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    down = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://decision")
    response = await make_client(decision=down).post(
        RUNS, json=run_body(), headers={"Accept": "application/x-ndjson"}
    )
    last = json.loads(response.text.splitlines()[-1])
    assert last == {"type": "error", "code": "DECISION_UNAVAILABLE", "message": last["message"]}


async def test_delete_cancels_a_running_run(make_client):
    started = asyncio.Event()

    class SlowWeather(MockToolSet):
        async def weather(self, query):
            started.set()
            await asyncio.sleep(10)

    client = make_client(tools=SlowWeather())
    body = run_body()
    pending = asyncio.create_task(post(client, body))
    await started.wait()

    assert (await client.delete(f"{RUNS}/{body['run_id']}")).status_code == 202
    response = await pending
    assert response.status_code == 503
    assert response.json()["code"] == "CANCELLED"


async def test_delete_unknown_run_is_404(client):
    assert (await client.delete(f"{RUNS}/{uuid4()}")).status_code == 404


async def test_service_token_is_required_when_configured(make_client, settings):
    client = make_client(settings.model_copy(update={"agent_service_token": SecretStr("s3cret")}))
    assert (await post(client, run_body())).status_code == 401
    ok = await post(client, run_body(), Authorization="Bearer s3cret")
    assert ok.status_code == 200


async def test_invalid_body_does_not_echo_input(client):
    body = run_body()
    body["request"]["question"] = "secret question"
    del body["user_profile"]
    response = await post(client, body)
    assert response.status_code == 422
    assert "secret question" not in response.text
