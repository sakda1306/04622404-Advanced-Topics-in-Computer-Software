"""FastAPI entry point for the Football Data service (CONTRACT.md §7)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import Base, make_database, schema_for
from app.history import verified_season_top_scorer
from app.service import FootballService, ServiceError
from app.simulation import SimulationService

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class UTF8JSONResponse(JSONResponse):
    def render(self, content):
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class ProblemResponse(UTF8JSONResponse):
    media_type = "application/problem+json"


def problem(code: str, status: int, detail: str) -> ProblemResponse:
    return ProblemResponse(
        status_code=status,
        content={
            "type": f"https://errors.football-assistant.local/{code.lower().replace('_', '-')}",
            "title": code.replace("_", " ").title(),
            "status": status,
            "code": code,
            "detail": detail,
            "service": "football-data",
            "request_id": request_id_var.get(),
        },
    )


class IngestRequest(BaseModel):
    scope: Literal["fixtures", "details", "all"]
    triggered_by: str = Field(pattern=r"^(beat|admin:[0-9a-fA-F-]{36})$")


class GenerateReportRequest(BaseModel):
    season: str | None = Field(default=None, pattern=r"^\d{4}$")
    matchweek: int | None = Field(default=None, ge=1, le=38)
    triggered_by: str = Field(pattern=r"^(beat|admin:[0-9a-fA-F-]{36})$")


class EditReportRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    markdown: str | None = Field(default=None, min_length=1)
    edited_by: str = Field(pattern=r"^(beat|admin:[0-9a-fA-F-]{36})$")

    @model_validator(mode="after")
    def has_change(self):
        if self.title is None and self.markdown is None:
            raise ValueError("title or markdown is required")
        return self


class ActorRequest(BaseModel):
    published_by: str | None = Field(default=None, pattern=r"^(beat|admin:[0-9a-fA-F-]{36})$")
    unpublished_by: str | None = Field(default=None, pattern=r"^(beat|admin:[0-9a-fA-F-]{36})$")


def create_app(
    settings: Settings | None = None, *, http: httpx.AsyncClient | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine, sessions = make_database(settings.database_url)
    owns_http = http is None
    http = http or httpx.AsyncClient()
    service = FootballService(settings, sessions, http)
    simulation = SimulationService(settings, sessions, http)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with engine.begin() as conn:
            if schema_for(settings.database_url):
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS football"))
            await conn.run_sync(Base.metadata.create_all)

        await service.recover_interrupted_jobs()
        repair_task = asyncio.create_task(service.run_index_worker())
        try:
            yield
        finally:
            repair_task.cancel()
            try:
                await repair_task
            except asyncio.CancelledError:
                pass
            if owns_http:
                await http.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Football Assistant — Football Data",
        version=settings.version,
        lifespan=lifespan,
        default_response_class=UTF8JSONResponse,
    )
    app.state.service = service
    app.state.simulation = simulation
    service.after_ingest = simulation.refresh

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        candidate = request.headers.get("X-Request-ID", "")
        try:
            request_id = str(UUID(candidate)) if candidate else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        token = request_id_var.set(request_id)
        try:
            try:
                response = await call_next(request)
            except Exception:
                response = problem("INTERNAL_ERROR", 500, "เกิดข้อผิดพลาดภายในระบบ")
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        return problem(exc.code, exc.status, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return problem("VALIDATION_ERROR", 422, str(exc.errors()))

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return problem(code, exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        return problem("INTERNAL_ERROR", 500, "เกิดข้อผิดพลาดภายในระบบ")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "football-data", "version": settings.version}

    @app.get("/ready")
    async def ready():
        async with sessions() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/football/status")
    async def football_status():
        return await service.status()

    @app.get("/football/teams")
    async def teams():
        return await service.teams()

    @app.get("/football/teams/{team_id}/squad")
    async def team_squad(
        team_id: int, season: str | None = Query(default=None, pattern=r"^\d{4}$")
    ):
        return await service.squad(team_id, season)

    @app.get("/football/standings")
    async def standings(season: str | None = Query(default=None, pattern=r"^\d{4}$")):
        return await service.standings(season)

    @app.get("/football/history/top-scorer/{season}")
    async def historical_top_scorer(season: str):
        if not season.isdigit() or len(season) != 4:
            raise ServiceError("VALIDATION_ERROR", 422, "season must be a four-digit start year")
        result = verified_season_top_scorer(season)
        if result is None:
            raise ServiceError(
                "HISTORICAL_SCORER_UNAVAILABLE",
                404,
                "No verified top-scorer reference for this season",
            )
        return result

    @app.get("/football/predict")
    async def predict(home_team_id: int = Query(ge=1), away_team_id: int = Query(ge=1)):
        return await simulation.predict(home_team_id, away_team_id, request_id_var.get())

    @app.get("/football/simulation")
    async def season_simulation(season: str | None = Query(default=None, pattern=r"^\d{4}$")):
        return await simulation.snapshot(season, request_id_var.get())

    @app.get("/football/fixtures")
    async def fixtures(
        season: str | None = Query(default=None, pattern=r"^\d{4}$"),
        matchweek: int | None = Query(default=None, ge=1, le=38),
        team_id: int | None = None,
        status: Literal["SCHEDULED", "LIVE", "FINISHED", "POSTPONED", "CANCELLED"] | None = None,
    ):
        return await service.fixtures(season, matchweek, team_id, status)

    @app.get("/football/matches/{match_id}")
    async def match(match_id: UUID):
        return await service.match(str(match_id))

    @app.get("/football/reports/weekly")
    async def public_report(
        season: str | None = Query(default=None, pattern=r"^\d{4}$"),
        matchweek: int | None = Query(default=None, ge=1, le=38),
    ):
        return await service.report(season, matchweek, published=True)

    @app.post("/ingest/run", status_code=202)
    async def ingest(body: IngestRequest, background: BackgroundTasks):
        if body.scope in ("details", "all"):
            if not settings.api_football_key:
                raise ServiceError("UPSTREAM_UNAVAILABLE", 502, "ยังไม่ได้ตั้ง API_FOOTBALL_KEY")
            quota = (await service.status())["quota"]
            if quota["api_football_used_today"] >= quota["api_football_limit"]:
                raise ServiceError("QUOTA_EXHAUSTED", 429, "ครบโควตา API-Football วันนี้แล้ว")
        request_id = request_id_var.get()
        job_id = await service.start_job("ingest", body.scope, body.triggered_by, request_id)
        background.add_task(service.run_ingest, job_id, body.scope, request_id)
        return {"job_id": job_id, "scope": body.scope}

    @app.post("/index/reconcile", status_code=202)
    async def reconcile_index(background: BackgroundTasks):
        background.add_task(service.reconcile_index)
        return {"queued": True}

    @app.post("/reports/weekly/run", status_code=202)
    async def generate_report(body: GenerateReportRequest, background: BackgroundTasks):
        request_id = request_id_var.get()
        job_id = await service.start_job("weekly_report", None, body.triggered_by, request_id)
        background.add_task(service.run_report, job_id, body.season, body.matchweek, request_id)
        return {"job_id": job_id}

    @app.get("/jobs")
    async def jobs(
        kind: Literal["ingest", "weekly_report"] | None = None,
        status: Literal["queued", "running", "done", "failed"] | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ):
        return await service.list_jobs(kind, status, limit)

    @app.get("/jobs/{job_id}")
    async def job(job_id: UUID):
        return await service.get_job(str(job_id))

    @app.get("/reports/weekly/list")
    async def reports(
        status: Literal["draft", "published", "unpublished"] | None = None,
        season: str | None = Query(default=None, pattern=r"^\d{4}$"),
    ):
        return await service.list_reports(status, season)

    @app.get("/reports/weekly/{season}/{matchweek}")
    async def report(season: str, matchweek: int):
        return await service.report(season, matchweek, published=False)

    @app.patch("/reports/weekly/{season}/{matchweek}")
    async def edit_report(season: str, matchweek: int, body: EditReportRequest):
        return await service.edit_report(
            season, matchweek, body.title, body.markdown, body.edited_by
        )

    @app.post("/reports/weekly/{season}/{matchweek}/publish")
    async def publish(season: str, matchweek: int, body: ActorRequest):
        if not body.published_by:
            raise ServiceError("VALIDATION_ERROR", 422, "published_by is required")
        return await service.publish(season, matchweek, body.published_by, request_id_var.get())

    @app.post("/reports/weekly/{season}/{matchweek}/unpublish")
    async def unpublish(season: str, matchweek: int, body: ActorRequest):
        if not body.unpublished_by:
            raise ServiceError("VALIDATION_ERROR", 422, "unpublished_by is required")
        return await service.unpublish(season, matchweek, body.unpublished_by, request_id_var.get())

    return app


def __getattr__(name: str):
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
