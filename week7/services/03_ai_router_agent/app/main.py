import json
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .clients import ServiceClients
from .router import Router, UpstreamError
from .teams import TeamDirectory


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RouteUser(BaseModel):
    id: UUID
    favorite_team_id: int | None = None
    language: Literal["th", "en"] = "th"


class RouteContext(BaseModel):
    season: str
    current_matchweek: int | None = None
    now: str
    last_ingest_at: str | None = None


class RouteRequest(BaseModel):
    request_id: str | None = None
    session_id: UUID
    user: RouteUser
    query: str = Field(min_length=1)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)
    context: RouteContext


logger = logging.getLogger("router")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as http:
        app.state.http = http
        app.state.clients = ServiceClients(http)
        path = Path(__file__).resolve().parents[1] / "data" / "team_aliases.json"
        app.state.teams = TeamDirectory.from_file(path)

        async def refresh_teams():
            while True:
                try:
                    payload = await app.state.clients.get_teams()
                    app.state.teams = app.state.teams.merged(TeamDirectory.from_payload(payload))
                except (UpstreamError, KeyError, TypeError):
                    logger.info(json.dumps({"event": "team_cache_fallback", "request_id": None}))
                await asyncio.sleep(300)

        refresh_task = asyncio.create_task(refresh_teams())
        try:
            yield
        finally:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Football Assistant Router", version="0.1.0", lifespan=lifespan)


def problem(status: int, code: str, title: str, detail: str, request_id: str):
    return JSONResponse({"type": f"https://errors.football-assistant.local/{code.lower().replace('_', '-')}",
                         "title": title, "status": status, "code": code, "detail": detail,
                         "service": "router", "request_id": request_id},
                        status_code=status, media_type="application/problem+json",
                        headers={"X-Request-ID": request_id})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    return problem(422, "INVALID_REQUEST", "Invalid router request", "ข้อมูลคำขอไม่ถูกต้อง", request_id)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "router", "version": "0.1.0"}


@app.post("/route")
async def route(body: RouteRequest, request: Request):
    request_id = body.request_id or request.headers.get("X-Request-ID") or str(uuid4())
    payload = body.model_dump(mode="json")
    payload["request_id"] = request_id
    try:
        result = await Router(request.app.state.clients, request.app.state.teams).route(payload)
        logger.info(json.dumps({"event": "route", "request_id": request_id, "route": result["route"],
                                "latency_ms": result["latency_ms"]}, ensure_ascii=False))
        return JSONResponse(result, headers={"X-Request-ID": request_id},
                            media_type="application/json; charset=utf-8")
    except Exception as exc:
        logger.error(json.dumps({"event": "route_error", "request_id": request_id,
                                 "error": type(exc).__name__}))
        return problem(500, "ROUTER_ERROR", "Router error", "ตอนนี้ระบบไม่ว่าง ลองใหม่อีกครั้งในอีกสักครู่", request_id)
