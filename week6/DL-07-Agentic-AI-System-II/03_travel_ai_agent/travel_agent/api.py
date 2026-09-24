"""HTTP API that Module 02 calls (docs/02_api_spec.md section 9)."""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from travel_agent.budget import AgentError
from travel_agent.config import Settings
from travel_agent.contracts import (
    AgentRunRequest,
    AgentRunResponse,
    ErrorLine,
    JobStage,
    ProgressLine,
    ResultLine,
)
from travel_agent.pipeline import Agent
from travel_agent.tools.base import ToolSet
from travel_agent.tools.decision import DecisionClient
from travel_agent.tools.live import LiveToolSet
from travel_agent.tools.mocks import MockToolSet

log = logging.getLogger("travel_agent")

NDJSON = "application/x-ndjson"


def _line(model: BaseModel) -> bytes:
    return model.model_dump_json(by_alias=True).encode() + b"\n"


def _error_body(error: AgentError) -> dict[str, str]:
    return {"code": error.code, "message": error.message}


def create_app(
    settings: Settings | None = None,
    *,
    tools: ToolSet | None = None,
    decision_http: httpx.AsyncClient | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if tools is None:
        tools = (
            MockToolSet()
            if settings.use_mock_tools
            else LiveToolSet(
                transport_provider=settings.transport_provider,
                longdo_api_key=settings.longdo_api_key.get_secret_value() or None,
                tomtom_api_key=settings.tomtom_api_key.get_secret_value() or None,
                osrm_base_url=str(settings.osrm_base_url).rstrip("/"),
            )
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if decision_http is not None:
            yield
            return
        async with httpx.AsyncClient() as http:
            app.state.agent = _agent(http)
            yield

    def _agent(http: httpx.AsyncClient) -> Agent:
        decision = DecisionClient(
            http,
            base_url=str(settings.decision_service_url),
            max_attempts=settings.decision_max_attempts,
        )
        return Agent(settings, tools, decision)

    app = FastAPI(
        title="Team D — Module 03 Travel AI Agent",
        version=settings.agent_version,
        description="Plans the run, calls tools, and hands the evidence to Module 07.",
        lifespan=lifespan,
    )
    if decision_http is not None:
        app.state.agent = _agent(decision_http)
    # run_id -> running task, so DELETE can cancel it.
    runs: dict[UUID, asyncio.Task[AgentRunResponse]] = {}

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Never echo the submitted payload back.
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_INPUT",
                "errors": [{"location": list(e["loc"]), "type": e["type"]} for e in error.errors()],
            },
        )

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        expected = settings.agent_service_token.get_secret_value()
        if not expected:
            return
        supplied = (authorization or "").removeprefix("Bearer ")
        if not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED"})

    @app.get("/health")
    async def health():
        return {"status": "ok", "module": "03"}

    @app.get("/ready")
    async def ready():
        return {
            "status": "ready",
            "tools": "mock" if settings.use_mock_tools else "live-04-05-06-hybrid",
            "decision_service": str(settings.decision_service_url),
        }

    @app.post(
        "/v1/agent/runs",
        response_model=AgentRunResponse,
        dependencies=[Depends(authorize)],
        responses={
            401: {"description": "Missing or wrong service token"},
            409: {"description": "run_id is already running"},
            503: {"description": "Module 07 unavailable or run cancelled"},
            504: {"description": "Deadline or budget exceeded"},
        },
    )
    async def create_run(
        body: AgentRunRequest,
        accept: Annotated[str, Header()] = "application/json",
        x_deadline: Annotated[datetime | None, Header()] = None,
    ):
        if body.run_id in runs:
            raise HTTPException(status_code=409, detail={"code": "RUN_ALREADY_ACTIVE"})

        # Stop at the earliest of: the backend's header, the request limit, our own cap.
        now = datetime.now(UTC)
        deadlines = [body.limits.deadline_at, now + timedelta(seconds=settings.agent_total_timeout)]
        if x_deadline is not None and x_deadline.tzinfo is not None:
            deadlines.append(x_deadline)
        seconds_left = (min(deadlines) - now).total_seconds()
        if seconds_left <= 0:
            error = AgentError("DEADLINE_EXCEEDED", "deadline already passed", 504)
            return JSONResponse(status_code=error.http_status, content=_error_body(error))

        progress: asyncio.Queue[ProgressLine | None] = asyncio.Queue()

        async def emit(stage: JobStage, percent: int, message: str) -> None:
            progress.put_nowait(ProgressLine(stage=stage, progress=percent, message=message))

        async def execute() -> AgentRunResponse:
            try:
                async with asyncio.timeout(seconds_left):
                    return await app.state.agent.run(body, emit)
            except TimeoutError:
                raise AgentError("DEADLINE_EXCEEDED", "run stopped at the deadline", 504) from None

        task = asyncio.create_task(execute())
        runs[body.run_id] = task
        task.add_done_callback(lambda _: runs.pop(body.run_id, None))
        task.add_done_callback(lambda _: progress.put_nowait(None))

        if NDJSON in accept:
            return StreamingResponse(_stream(task, progress), media_type=NDJSON)
        return await _json(task)

    @app.delete("/v1/agent/runs/{run_id}", status_code=202, dependencies=[Depends(authorize)])
    async def cancel_run(run_id: UUID):
        task = runs.get(run_id)
        if task is None:
            # 02 treats 404 as "already finished": success from its side.
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        task.cancel()
        return Response(status_code=202)

    return app


def _outcome(task: asyncio.Task[AgentRunResponse]) -> AgentRunResponse | AgentError:
    if task.cancelled():
        return AgentError("CANCELLED", "run cancelled", 503)
    error = task.exception()
    if error is None:
        return task.result()
    if isinstance(error, AgentError):
        return error
    log.error("agent run failed", exc_info=error)
    return AgentError("INTERNAL_ERROR", "agent failed", 503)


async def _json(task: asyncio.Task[AgentRunResponse]) -> Response:
    try:
        await asyncio.wait({task})
    except asyncio.CancelledError:
        task.cancel()  # the backend closed the connection
        raise
    outcome = _outcome(task)
    if isinstance(outcome, AgentError):
        return JSONResponse(status_code=outcome.http_status, content=_error_body(outcome))
    return Response(content=outcome.model_dump_json(by_alias=True), media_type="application/json")


async def _stream(
    task: asyncio.Task[AgentRunResponse], progress: asyncio.Queue[ProgressLine | None]
) -> AsyncIterator[bytes]:
    try:
        while (line := await progress.get()) is not None:
            yield _line(line)
        outcome = _outcome(task)
        if isinstance(outcome, AgentError):
            yield _line(ErrorLine(code=outcome.code, message=outcome.message))
        else:
            yield _line(ResultLine.model_validate({**outcome.model_dump(), "type": "result"}))
    finally:
        if not task.done():
            task.cancel()  # the backend closed the stream


app = create_app()
