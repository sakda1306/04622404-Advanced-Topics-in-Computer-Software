"""Mock Travel AI Agent for development and tests.

Implements the contract in docs/02_api_spec.md section 9 with canned scenarios, so the
backend can be built and tested before Module 03 is ready. It does not import the
backend package; it only speaks the HTTP contract.

Choose a scenario with the MOCK_SCENARIO environment variable, or at runtime with
`PUT /_mock/scenario {"name": "high_risk"}`.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

SCENARIO_DIR = Path(__file__).parent / "scenarios"
NDJSON = "application/x-ndjson"
PROGRESS_STAGES = (
    ("fetching_data", 20, "Checking weather, transport and disaster alerts"),
    ("assessing_risk", 60, "Assessing route risk"),
    ("generating_advice", 90, "Writing the recommendation"),
)


def load_scenarios() -> dict[str, dict[str, Any]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCENARIO_DIR.glob("*.json"))
    }


SCENARIOS = load_scenarios()


class ScenarioChoice(BaseModel):
    name: str


class MockState:
    def __init__(self) -> None:
        self.scenario = os.environ.get("MOCK_SCENARIO", "low_risk")
        self.required_token = os.environ.get("MOCK_REQUIRE_TOKEN") or None
        self.step_delay = float(os.environ.get("MOCK_STEP_DELAY_SECONDS", "0.05"))
        self.cancelled: set[str] = set()
        self.runs: list[dict[str, Any]] = []


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_result(scenario: dict[str, Any], run_id: str, now: datetime) -> dict[str, Any]:
    """Fill a scenario template with the run id and timestamps relative to now."""
    result: dict[str, Any] = json.loads(json.dumps(scenario["response"]))
    result["run_id"] = run_id
    if "valid_for_seconds" in scenario:
        result["valid_until"] = _iso(now + timedelta(seconds=scenario["valid_for_seconds"]))
    result["data_freshness"] = {
        "items": [
            {"category": category, "updated_at": _iso(now - timedelta(seconds=age))}
            if age is not None
            else {"category": category, "updated_at": None}
            for category, age in scenario.get("freshness_age_seconds", {}).items()
        ]
    }
    for source in result.get("sources", []):
        source["retrieved_at"] = _iso(now - timedelta(seconds=60))
    return result


def create_app(state: MockState | None = None) -> FastAPI:
    state = state or MockState()
    app = FastAPI(title="Mock Travel AI Agent", docs_url=None, redoc_url=None)
    app.state.mock = state

    def check_auth(authorization: str | None) -> None:
        if state.required_token and authorization != f"Bearer {state.required_token}":
            raise HTTPException(status_code=401, detail="invalid service token")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "scenario": state.scenario}

    @app.get("/_mock/scenario")
    async def get_scenario() -> dict[str, Any]:
        return {
            "name": state.scenario,
            "available": sorted(SCENARIOS),
            "runs": len(state.runs),
            "cancelled": len(state.cancelled),
        }

    @app.put("/_mock/scenario")
    async def set_scenario(choice: ScenarioChoice) -> dict[str, str]:
        if choice.name not in SCENARIOS:
            raise HTTPException(status_code=404, detail="unknown scenario")
        state.scenario = choice.name
        return {"name": state.scenario}

    @app.post("/v1/agent/runs")
    async def create_run(
        request: Request,
        accept: str = Header(default="application/json"),
        x_deadline: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ) -> Response:
        check_auth(authorization)
        if x_deadline is None:
            raise HTTPException(status_code=400, detail="X-Deadline header is required")
        body = await request.json()
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or "request" not in body or "limits" not in body:
            raise HTTPException(status_code=422, detail="invalid run request")
        state.runs.append({"run_id": run_id, "headers": dict(request.headers), "body": body})

        scenario = SCENARIOS[state.scenario]
        http = scenario.get("http", {})
        if "status" in http:
            return JSONResponse(
                {"error": http.get("error", "mock failure")},
                status_code=http["status"],
                headers=http.get("headers"),
            )
        delay = float(scenario.get("delay_seconds", 0))

        if accept.startswith(NDJSON):
            return StreamingResponse(stream_run(state, scenario, run_id, delay), media_type=NDJSON)
        if delay:
            await asyncio.sleep(delay)
        if scenario.get("raw_body") is not None:
            return Response(scenario["raw_body"], media_type="application/json")
        return JSONResponse(build_result(scenario, run_id, datetime.now(UTC)))

    @app.delete("/v1/agent/runs/{run_id}", status_code=202)
    async def cancel_run(run_id: str, authorization: str | None = Header(default=None)) -> None:
        check_auth(authorization)
        if not any(run["run_id"] == run_id for run in state.runs):
            raise HTTPException(status_code=404, detail="unknown run")
        state.cancelled.add(run_id)

    return app


async def stream_run(
    state: MockState, scenario: dict[str, Any], run_id: str, delay: float
) -> AsyncIterator[bytes]:
    step = max(state.step_delay, delay / len(PROGRESS_STAGES))
    for stage, progress, message in PROGRESS_STAGES:
        if run_id in state.cancelled:
            yield _line({"type": "error", "code": "CANCELLED", "message": "run cancelled"})
            return
        yield _line({"type": "progress", "stage": stage, "progress": progress, "message": message})
        await asyncio.sleep(step)
    if scenario.get("stream_error"):
        yield _line({"type": "error", **scenario["stream_error"]})
        return
    if scenario.get("raw_body") is not None:
        yield (scenario["raw_body"] + "\n").encode()
        return
    yield _line({"type": "result", **build_result(scenario, run_id, datetime.now(UTC))})


def _line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode()


app = create_app()
