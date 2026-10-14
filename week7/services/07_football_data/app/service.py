"""Database operations and scheduled ingestion/report jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api_football import enriched_match, match_api_fixture
from app.coaches import (
    QID,
    CoachFetchError,
    coach_document,
    current_coach,
    fetch_coaches,
    load_club_qids,
)
from app.config import Settings
from app.db import (
    ApiQuota,
    IndexTask,
    Job,
    Match,
    Scorers,
    ServiceState,
    Squad,
    Standing,
    Team,
    WeeklyReport,
)
from app.football import (
    PrimaryThrottle,
    completed_matchweeks,
    current_season,
    derive_standings,
    fetch_primary,
    match_payload,
    now_iso,
    scorer_payload,
    squad_document,
    squad_payload,
    standing_payload,
    team_payload,
)

BANGKOK = ZoneInfo("Asia/Bangkok")
INDEX_MAX_BYTES = 5_000_000
TOP_SCORERS_SHOWN = 10
logger = logging.getLogger(__name__)


def index_body(documents: list[dict], request_id: str) -> bytes:
    return json.dumps(
        {"request_id": request_id, "documents": documents},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class ServiceError(Exception):
    def __init__(self, code: str, status: int, detail: str):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(detail)


def job_dict(row: Job) -> dict:
    return {
        "job_id": row.job_id,
        "kind": row.kind,
        "scope": row.scope,
        "status": row.status,
        "triggered_by": row.triggered_by,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "detail": row.detail,
    }


def report_doc(report: dict) -> dict:
    season, week = report["season"], report["matchweek"]
    if not report.get("search_text_en"):
        raise ServiceError(
            "INDEX_UPDATE_FAILED", 502, "Report search text requires source-data backfill"
        )
    return {
        "doc_id": f"weekly-{season}-mw{week:02d}",
        "title": f"Premier League {season} matchweek {week} summary",
        "text": report["search_text_en"],
        "category": "weekly_report",
        "origin": "generated",
        "season": season,
        "matchweek": week,
        "team_ids": [],
        "date": report["data_as_of"][:10],
        "fetched_at": report["data_as_of"],
        "url": None,
    }


def report_search_text(
    season: str, matchweek: int, matches: list[dict], standings: list[dict], scorers: list[dict]
) -> str:
    lines = [f"Premier League {season}, matchweek {matchweek}.", "## Match results"]
    for match in sorted(matches, key=lambda item: item["kickoff"]):
        home, away = match["home"]["name"], match["away"]["name"]
        if match["status"] == "FINISHED":
            lines.append(
                f"{home} {match['score']['home']}-{match['score']['away']} {away}; "
                f"kickoff {match['kickoff']}."
            )
        else:
            lines.append(f"{home} vs {away}: {match['status'].lower()}.")
    lines.append("## Standings")
    for row in standings:
        lines.append(f"{row['position']}. {row['name']}: {row['points']} points.")
    if scorers:
        lines.append("## Top scorers")
        for scorer in scorers:
            lines.append(f"{scorer['player']}: {scorer['goals']} goals.")
    return "\n".join(lines)


class FootballService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker, http: httpx.AsyncClient):
        self.settings, self.sessions, self.http = settings, sessions, http
        self._job_lock = asyncio.Lock()
        self._index_lock = asyncio.Lock()
        self._report_lock = asyncio.Lock()
        self._quota_lock = asyncio.Lock()
        self._primary_throttle = PrimaryThrottle()
        self.after_ingest: Callable[[], Awaitable[None]] | None = None

    @staticmethod
    async def _latest_standing(db: AsyncSession, season: str) -> Standing | None:
        rows = list(
            await db.scalars(
                select(Standing)
                .where(Standing.season == season)
                .order_by(Standing.matchweek.desc())
            )
        )
        # The newest official live row is the current table; completed prior weeks
        # remain available by exact matchweek for report generation.
        return rows[0] if rows else None

    async def status(self) -> dict:
        season = current_season()
        async with self.sessions() as db:
            state = await db.get(ServiceState, "last_ingest_at")
            sync_state = await db.get(ServiceState, "last_index_sync_at")
            pending = await db.scalar(select(func.count()).select_from(IndexTask))
            error = await db.scalar(
                select(IndexTask.last_error).where(IndexTask.last_error.is_not(None)).limit(1)
            )
            today = datetime.now(UTC).date()
            quota = await db.get(ApiQuota, today)
            standing = await self._latest_standing(db, season)
            reports = await db.scalars(
                select(WeeklyReport).where(
                    WeeklyReport.season == season, WeeklyReport.status == "published"
                )
            )
            weeks = [r.matchweek for r in reports]
        reset = datetime.combine(today + timedelta(days=1), datetime.min.time(), UTC)
        return {
            "current_season": season,
            "current_matchweek": standing.payload.get("matchweek") if standing else None,
            "last_ingest_at": state.value if state else None,
            "last_report_matchweek": max(weeks) if weeks else None,
            "quota": {
                "api_football_used_today": quota.used if quota else 0,
                "api_football_limit": self.settings.api_football_daily_limit,
                "reset_at": reset.astimezone(BANGKOK).isoformat(timespec="seconds"),
            },
            "index_sync": {
                "pending": pending,
                "last_error": error,
                "last_synced_at": sync_state.value if sync_state else None,
            },
        }

    @staticmethod
    async def _queue_documents(db: AsyncSession, documents: list[dict], request_id: str) -> None:
        for document in documents:
            await db.merge(
                IndexTask(
                    doc_id=document["doc_id"],
                    action="upsert",
                    payload=document,
                    request_id=request_id,
                    updated_at=datetime.now(BANGKOK),
                    last_error=None,
                )
            )

    async def _send_index(self, action: str, document: dict | None, doc_id: str, request_id: str):
        base_url = self.settings.retrieval_url.rstrip("/")
        if action == "upsert":
            await self._send_upserts([document], request_id)
            return
        else:
            response = await self.http.delete(
                f"{base_url}/index/{doc_id}",
                headers={"X-Request-ID": request_id},
                timeout=30,
            )
        response.raise_for_status()

    async def _send_upserts(self, documents: list[dict], request_id: str) -> None:
        if (
            any(doc.get("category") == "historical" for doc in documents)
            and not self.settings.historical_index_enabled
        ):
            raise ServiceError(
                "INDEX_UPDATE_FAILED", 502, "Historical CONTRACT/05 integration is not enabled"
            )
        body = index_body(documents, request_id)
        if not 1 <= len(documents) <= 100 or len(body) > INDEX_MAX_BYTES:
            raise ServiceError("INDEX_UPDATE_FAILED", 502, "Index batch exceeds contract limits")
        response = await self.http.post(
            f"{self.settings.retrieval_url.rstrip('/')}/index/upsert",
            content=body,
            headers={"X-Request-ID": request_id, "Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

    async def run_index_worker(self) -> None:
        """Keep replaying the durable outbox; cancellation leaves pending tasks in DB."""
        delay = self.settings.index_retry_seconds
        while True:
            try:
                await self.reconcile_index()
                delay = self.settings.index_retry_seconds
            except Exception:
                logger.exception("Index replay failed; retrying with backoff")
                delay = min(delay * 2, self.settings.index_retry_max_seconds)
            await asyncio.sleep(delay)

    async def _replay_upsert_batch(self, doc_ids: list[str]) -> None:
        async with self.sessions() as db:
            tasks = list(
                await db.scalars(
                    select(IndexTask)
                    .where(IndexTask.doc_id.in_(doc_ids), IndexTask.action == "upsert")
                    .order_by(IndexTask.updated_at, IndexTask.doc_id)
                )
            )
        if not tasks:
            return
        try:
            await self._send_upserts([task.payload for task in tasks], tasks[0].request_id)
        except (httpx.HTTPError, ValueError, ServiceError) as exc:
            async with self.sessions() as db:
                for task in tasks:
                    await db.execute(
                        update(IndexTask)
                        .where(
                            IndexTask.doc_id == task.doc_id,
                            IndexTask.action == "upsert",
                            IndexTask.updated_at == task.updated_at,
                        )
                        .values(last_error=str(exc))
                    )
                await db.commit()
            raise ServiceError("INDEX_UPDATE_FAILED", 502, str(exc)) from exc
        async with self.sessions() as db:
            for task in tasks:
                removed = await db.execute(
                    delete(IndexTask).where(
                        IndexTask.doc_id == task.doc_id,
                        IndexTask.action == "upsert",
                        IndexTask.updated_at == task.updated_at,
                    )
                )
                if removed.rowcount and task.payload.get("category") == "standings":
                    await db.merge(
                        ServiceState(
                            key=f"standings_indexed_{task.payload['season']}",
                            value=now_iso(),
                        )
                    )
            await db.merge(ServiceState(key="last_index_sync_at", value=now_iso()))
            await db.commit()

    async def reconcile_index(self, doc_id: str | None = None) -> None:
        """Replay persisted writes; report tasks follow the durable DB publication state."""
        async with self._index_lock:
            async with self.sessions() as db:
                query = select(IndexTask)
                if doc_id is not None:
                    query = query.where(IndexTask.doc_id == doc_id)
                tasks = list(
                    await db.scalars(query.order_by(IndexTask.updated_at, IndexTask.doc_id))
                )
            batches, batch, documents = [], [], []
            non_upserts = []
            for task in tasks:
                if task.action != "upsert":
                    non_upserts.append(task)
                    continue
                candidate = [*documents, task.payload]
                # Player documents travel alone so a rejected category cannot strand the rest.
                mixes_player = bool(documents) and (
                    (documents[0].get("category") == "player")
                    != (task.payload.get("category") == "player")
                )
                if batch and (
                    mixes_player
                    or len(candidate)
                    > (50 if any(doc.get("category") == "historical" for doc in candidate) else 100)
                    or len(index_body(candidate, task.request_id)) > INDEX_MAX_BYTES
                ):
                    batches.append(batch)
                    batch, documents = [], []
                batch.append(task.doc_id)
                documents.append(task.payload)
            if batch:
                batches.append(batch)
            first_error = None
            for batch_ids in batches:
                try:
                    await self._replay_upsert_batch(batch_ids)
                except ServiceError as exc:
                    first_error = first_error or exc
            for seen in non_upserts:
                async with self.sessions() as db:
                    task = await db.get(IndexTask, seen.doc_id)
                    if (
                        task is None
                        or task.action != seen.action
                        or task.updated_at != seen.updated_at
                    ):
                        continue
                    action, document = task.action, task.payload
                    if action == "delete" and document and document.get("replacement_doc_id"):
                        replacement = await db.get(IndexTask, document["replacement_doc_id"])
                        if replacement is not None:
                            # Do not remove the last old table until the new stable ID is indexed.
                            continue
                        replacement_id = document["replacement_doc_id"]
                        if replacement_id.startswith("standings-"):
                            indexed = await db.get(
                                ServiceState, f"standings_indexed_{replacement_id[10:]}"
                            )
                            if indexed is None:
                                # No durable evidence that the new document ever reached 05.
                                continue
                    if action == "transition":
                        updated_at = task.updated_at
                        if updated_at.tzinfo is None:
                            updated_at = updated_at.replace(tzinfo=BANGKOK)
                        age = datetime.now(BANGKOK) - updated_at
                        if age < timedelta(seconds=self.settings.index_transition_timeout_seconds):
                            continue
                        action = "reconcile_report"
                    if action == "reconcile_report":
                        report = await db.scalar(
                            select(WeeklyReport).where(
                                WeeklyReport.season == document["season"],
                                WeeklyReport.matchweek == document["matchweek"],
                            )
                        )
                        action = "upsert" if report and report.status == "published" else "delete"
                        if action == "upsert":
                            try:
                                await self._backfill_report_search(db, report)
                                document = report_doc(report.payload)
                            except ServiceError as exc:
                                await db.execute(
                                    update(IndexTask)
                                    .where(
                                        IndexTask.doc_id == seen.doc_id,
                                        IndexTask.action == seen.action,
                                        IndexTask.updated_at == seen.updated_at,
                                    )
                                    .values(last_error=str(exc))
                                )
                                await db.commit()
                                first_error = first_error or exc
                                continue
                        else:
                            document = None
                    request_id = task.request_id
                    await db.commit()
                try:
                    await self._send_index(action, document, seen.doc_id, request_id)
                except (httpx.HTTPError, ValueError, ServiceError) as exc:
                    async with self.sessions() as db:
                        await db.execute(
                            update(IndexTask)
                            .where(
                                IndexTask.doc_id == seen.doc_id,
                                IndexTask.action == seen.action,
                                IndexTask.updated_at == seen.updated_at,
                            )
                            .values(last_error=str(exc))
                        )
                        await db.commit()
                    first_error = first_error or ServiceError("INDEX_UPDATE_FAILED", 502, str(exc))
                    continue
                async with self.sessions() as db:
                    removed = await db.execute(
                        delete(IndexTask).where(
                            IndexTask.doc_id == seen.doc_id,
                            IndexTask.action == seen.action,
                            IndexTask.updated_at == seen.updated_at,
                        )
                    )
                    if removed.rowcount:
                        await db.merge(ServiceState(key="last_index_sync_at", value=now_iso()))
                    await db.commit()

            if first_error:
                raise first_error

    async def _reconcile_after_ingest(self) -> None:
        """Persisted football data succeeds even when retrieval must retry later."""
        try:
            await self.reconcile_index()
        except Exception:
            logger.exception("Index sync deferred; durable outbox will retry")
        if self.after_ingest is not None:
            try:
                await self.after_ingest()
            except Exception:
                logger.exception("after-ingest hook failed")

    async def teams(self) -> dict:
        async with self.sessions() as db:
            rows = (await db.scalars(select(Team).order_by(Team.team_id))).all()
            return {"teams": [row.payload for row in rows]}

    async def squad(self, team_id: int, season: str | None) -> dict:
        async with self.sessions() as db:
            row = await db.get(Squad, (season or current_season(), team_id))
            if row is None:
                raise ServiceError("NOT_FOUND", 404, "ยังไม่มีข้อมูลนักเตะของทีมนี้")
            return row.payload

    async def standings(self, season: str | None) -> dict:
        async with self.sessions() as db:
            row = await self._latest_standing(db, season or current_season())
            if row is None:
                raise ServiceError("NOT_FOUND", 404, "ยังไม่มีตารางคะแนนของฤดูกาลนี้")
            return row.payload

    async def fixtures(
        self, season: str | None, matchweek: int | None, team_id: int | None, status: str | None
    ) -> dict:
        selected = season or current_season()
        query = select(Match).where(Match.season == selected)
        if matchweek is not None:
            query = query.where(Match.matchweek == matchweek)
        if status:
            query = query.where(Match.status == status)
        if team_id is not None:
            query = query.where((Match.home_team_id == team_id) | (Match.away_team_id == team_id))
        async with self.sessions() as db:
            matches = (await db.scalars(query)).all()
            state = await db.get(ServiceState, "last_ingest_at")
        matches.sort(key=lambda row: row.payload["kickoff"])
        return {
            "season": selected,
            "fetched_at": state.value if state else None,
            "matches": [row.payload for row in matches],
        }

    async def match(self, match_id: str) -> dict:
        async with self.sessions() as db:
            row = await db.get(Match, match_id)
            if row is None:
                raise ServiceError("NOT_FOUND", 404, "ไม่พบนัดการแข่งขัน")
            return row.payload

    async def list_jobs(self, kind: str | None, status: str | None, limit: int) -> dict:
        query = select(Job)
        if kind:
            query = query.where(Job.kind == kind)
        if status:
            query = query.where(Job.status == status)
        query = query.order_by(Job.started_at.desc()).limit(limit)
        async with self.sessions() as db:
            rows = (await db.scalars(query)).all()
        return {"jobs": [job_dict(row) for row in rows]}

    async def get_job(self, job_id: str) -> dict:
        async with self.sessions() as db:
            row = await db.get(Job, job_id)
            if row is None:
                raise ServiceError("NOT_FOUND", 404, "ไม่พบงาน")
            return job_dict(row)

    async def start_job(
        self, kind: str, scope: str | None, triggered_by: str, request_id: str
    ) -> str:
        async with self._job_lock:
            async with self.sessions() as db:
                active = await db.scalar(
                    select(Job.job_id).where(
                        Job.kind == kind, Job.status.in_(["queued", "running"])
                    )
                )
                if active:
                    raise ServiceError("JOB_ALREADY_RUNNING", 409, "มีงานชนิดเดียวกันกำลังทำงาน")
                job_id = str(uuid4())
                db.add(
                    Job(
                        job_id=job_id,
                        request_id=request_id,
                        kind=kind,
                        scope=scope,
                        status="queued",
                        triggered_by=triggered_by,
                        started_at=datetime.now(BANGKOK),
                    )
                )
                await db.commit()
                return job_id

    async def recover_interrupted_jobs(self) -> None:
        """A previous process cannot resume its in-memory background jobs."""
        async with self.sessions() as db:
            jobs = list(await db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))))
            for job in jobs:
                job.status = "failed"
                job.detail = "Interrupted by service restart"
                job.finished_at = datetime.now(BANGKOK)
            if jobs:
                await db.commit()

    async def _finish_job(self, job_id: str, detail: str | None) -> None:
        async with self.sessions() as db:
            job = await db.get(Job, job_id)
            job.status = "failed" if detail else "done"
            job.detail = detail
            job.finished_at = datetime.now(BANGKOK)
            await db.commit()

    async def _reserve_quota(self) -> None:
        today = datetime.now(UTC).date()
        async with self._quota_lock:
            for _ in range(2):
                async with self.sessions() as db:
                    row = await db.get(ApiQuota, today, with_for_update=True)
                    if row is None:
                        db.add(ApiQuota(utc_day=today, used=1))
                    else:
                        if row.used >= self.settings.api_football_daily_limit:
                            raise ServiceError(
                                "QUOTA_EXHAUSTED", 429, "ครบโควตา API-Football วันนี้แล้ว"
                            )
                        row.used += 1
                    try:
                        await db.commit()
                        return
                    except IntegrityError:
                        await db.rollback()
            raise ServiceError("QUOTA_EXHAUSTED", 429, "ไม่สามารถจองโควตา API-Football")

    async def _api_football_get(self, path: str, params: dict, request_id: str) -> list[dict]:
        if not self.settings.api_football_key:
            raise ServiceError("UPSTREAM_UNAVAILABLE", 502, "ยังไม่ได้ตั้ง API_FOOTBALL_KEY")
        url = f"{self.settings.api_football_base_url.rstrip('/')}/{path.lstrip('/')}"
        for attempt in range(3):
            await self._reserve_quota()
            try:
                response = await self.http.get(
                    url,
                    params=params,
                    headers={
                        "x-apisports-key": self.settings.api_football_key,
                        "X-Request-ID": request_id,
                    },
                    timeout=10,
                )
                if response.status_code == 429:
                    raise ServiceError("QUOTA_EXHAUSTED", 429, "API-Football ปฏิเสธโควตา")
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep((1, 3)[attempt])
                    continue
                response.raise_for_status()
                data = response.json()
                if data.get("errors"):
                    raise ServiceError("UPSTREAM_UNAVAILABLE", 502, "API-Football คืนข้อผิดพลาด")
                return data.get("response", [])
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 2:
                    raise ServiceError(
                        "UPSTREAM_UNAVAILABLE", 502, "ติดต่อ API-Football ไม่ได้"
                    ) from exc
                await asyncio.sleep((1, 3)[attempt])
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise ServiceError("UPSTREAM_UNAVAILABLE", 502, str(exc)) from exc
        raise ServiceError("UPSTREAM_UNAVAILABLE", 502, "ติดต่อ API-Football ไม่ได้")

    async def run_ingest(self, job_id: str, scope: str, request_id: str) -> None:
        async with self.sessions() as db:
            job = await db.get(Job, job_id)
            job.status = "running"
            await db.commit()
        try:
            if scope in ("fixtures", "all"):
                await self._ingest_primary(request_id)
            if scope in ("details", "all"):
                await self._ingest_details(request_id)
            await self._finish_job(job_id, None)
        except asyncio.CancelledError:
            await self._finish_job(job_id, "CancelledError: task cancelled")
            raise
        except Exception as exc:
            await self._finish_job(job_id, f"{type(exc).__name__}: {exc}")

    async def _coach_documents(
        self, teams: list[dict], season: str, fetched_at: str, request_id: str
    ) -> list[dict]:
        """One head coach document per team (CONTRACT v1.16); none when Wikidata fails."""
        if not self.settings.coach_index_enabled:
            return []
        try:
            qids = load_club_qids()
            # A malformed QID must not turn into a "no coach" document over a good one.
            known = [team for team in teams if QID.match(qids.get(team["team_id"], ""))]
            if not known:
                return []
            coaches = await fetch_coaches(
                self.http, [qids[team["team_id"]] for team in known], self.settings.version
            )
            return [
                coach_document(
                    team["team_id"],
                    team["name"],
                    qids[team["team_id"]],
                    current_coach(coaches.get(qids[team["team_id"]], [])),
                    season,
                    fetched_at,
                )
                for team in known
            ]
        except (CoachFetchError, Exception) as exc:  # noqa: BLE001 - coaches must never stop the ingest
            # The previous coach documents stay in the index until Wikidata answers again.
            logger.warning("coach_fetch_failed request_id=%s error=%s", request_id, exc)
            return []

    async def _ingest_primary(self, request_id: str) -> None:
        season = current_season()
        # Fetch all responses before changing any database rows.
        teams_raw = await fetch_primary(
            self.http,
            self.settings,
            "competitions/PL/teams",
            season,
            request_id,
            self._primary_throttle,
        )
        matches_raw = await fetch_primary(
            self.http,
            self.settings,
            "competitions/PL/matches",
            season,
            request_id,
            self._primary_throttle,
        )
        standings_raw = await fetch_primary(
            self.http,
            self.settings,
            "competitions/PL/standings",
            season,
            request_id,
            self._primary_throttle,
        )
        scorers_raw = await fetch_primary(
            self.http,
            self.settings,
            "competitions/PL/scorers",
            season,
            request_id,
            self._primary_throttle,
            params={"limit": 100},
        )
        fetched_at = now_iso()
        teams = [team_payload(item) for item in teams_raw.get("teams", [])]
        matches = [match_payload(item, fetched_at) for item in matches_raw.get("matches", [])]
        standing = standing_payload(standings_raw, season, fetched_at)
        scorers = scorer_payload(scorers_raw)
        squads = [
            squad
            for item in teams_raw.get("teams", [])
            if (squad := squad_payload(item, fetched_at))
        ]
        completed_weeks = completed_matchweeks(matches)
        standing["snapshot_type"] = (
            "completed" if standing["matchweek"] in completed_weeks else "live"
        )
        derived_weeks = [week for week in completed_weeks if week != standing["matchweek"]]
        coach_documents = await self._coach_documents(teams, season, fetched_at, request_id)
        async with self.sessions() as db:
            for item in teams:
                await db.merge(Team(team_id=item["team_id"], payload=item))
            for item in matches:
                existing = await db.get(Match, item["match_id"])
                if existing and existing.payload.get("detail_source") == "api-football":
                    for field in ("events", "lineups", "statistics", "detail_source"):
                        item[field] = existing.payload[field]
                    item["external_ids"]["api_football"] = existing.payload["external_ids"].get(
                        "api_football"
                    )
                await db.merge(
                    Match(
                        match_id=item["match_id"],
                        external_id=item["external_ids"]["football_data"],
                        season=season,
                        matchweek=item["matchweek"],
                        home_team_id=item["home"]["team_id"],
                        away_team_id=item["away"]["team_id"],
                        status=item["status"],
                        payload=item,
                    )
                )
            await db.merge(
                Standing(season=season, matchweek=standing["matchweek"] or 0, payload=standing)
            )
            for week in derived_weeks:
                key = (season, week)
                existing_snapshot = await db.get(Standing, key)
                if (
                    existing_snapshot is not None
                    and existing_snapshot.payload.get("snapshot_type") == "completed"
                ):
                    continue
                # A previous official live row preserves deductions already in force
                # at that week; otherwise the current official table is the best
                # available reference. The derived result stays marked provisional.
                reference_rows = (
                    existing_snapshot.payload.get("rows")
                    if existing_snapshot and existing_snapshot.payload.get("rows")
                    else standing["rows"]
                )
                snapshot = derive_standings(
                    matches, teams, season, week, fetched_at, reference_rows
                )
                snapshot["snapshot_type"] = "completed"
                await db.merge(Standing(season=season, matchweek=week, payload=snapshot))
            await db.merge(
                Scorers(season=season, payload={"items": scorers, "fetched_at": fetched_at})
            )
            for squad in squads:
                await db.merge(Squad(season=season, team_id=squad["team_id"], payload=squad))
            await db.merge(ServiceState(key="last_ingest_at", value=fetched_at))
            documents = self._documents(matches, standing, season, fetched_at, scorers)
            if self.settings.player_index_enabled:
                stats = {s["player_id"]: s for s in scorers if s["player_id"] is not None}
                documents += [squad_document(squad, season, stats) for squad in squads]
            documents += coach_documents
            await self._queue_documents(db, documents, request_id)
            cleanup_key = f"standings_legacy_cleanup_queued_{season}"
            if (
                any(doc["doc_id"] == f"standings-{season}" for doc in documents)
                and await db.get(ServiceState, cleanup_key) is None
            ):
                # Durable one-time migration; failed deletes remain retryable in the outbox.
                for week in range(1, 39):
                    await db.merge(
                        IndexTask(
                            doc_id=f"standings-{season}-mw{week:02d}",
                            action="delete",
                            payload={"replacement_doc_id": f"standings-{season}"},
                            request_id=request_id,
                            updated_at=datetime.now(BANGKOK),
                        )
                    )
                await db.merge(ServiceState(key=cleanup_key, value=now_iso()))
            await db.commit()
        # The outbox remains in DB if retrieval is unavailable and is safe to replay.
        await self._reconcile_after_ingest()

    async def _ingest_details(self, request_id: str) -> None:
        if not self.settings.api_football_key:
            raise ServiceError("UPSTREAM_UNAVAILABLE", 502, "ยังไม่ได้ตั้ง API_FOOTBALL_KEY")
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(Match)
                    .where(Match.season == current_season(), Match.status == "FINISHED")
                    .order_by(Match.matchweek.desc())
                )
            ).all()
            candidates = [
                row.payload for row in rows if row.payload.get("detail_source") != "api-football"
            ]
        by_date: dict[str, list[dict]] = {}
        for match in candidates:
            # API-Football's date filter uses UTC dates.
            utc_date = datetime.fromisoformat(match["kickoff"]).astimezone(UTC).date()
            by_date.setdefault(utc_date.isoformat(), []).append(match)
        for date, matches in by_date.items():
            fixtures = await self._api_football_get(
                "fixtures",
                {
                    "league": self.settings.api_football_league_id,
                    "season": current_season(),
                    "date": date,
                },
                request_id,
            )
            for match in matches:
                fixture = match_api_fixture(match, fixtures)
                if fixture is None:
                    logger.warning(
                        "Skipping unmatched API-Football fixture: match_id=%s date=%s",
                        match["match_id"],
                        date,
                    )
                    continue
                api_id = fixture["fixture"]["id"]
                events = await self._api_football_get(
                    "fixtures/events", {"fixture": api_id}, request_id
                )
                lineups = await self._api_football_get(
                    "fixtures/lineups", {"fixture": api_id}, request_id
                )
                statistics = await self._api_football_get(
                    "fixtures/statistics", {"fixture": api_id}, request_id
                )
                fetched_at = now_iso()
                enriched = enriched_match(match, fixture, events, lineups, statistics, fetched_at)
                documents = [
                    doc
                    for doc in self._documents(
                        [enriched], {"matchweek": None}, match["season"], fetched_at
                    )
                    if doc["category"] == "match_report"
                ]
                async with self.sessions() as db:
                    row = await db.get(Match, match["match_id"])
                    row.payload = enriched
                    await self._queue_documents(db, documents, request_id)
                    await db.commit()
                await self._reconcile_after_ingest()

    @staticmethod
    def _documents(
        matches: list[dict],
        standing: dict,
        season: str,
        fetched_at: str,
        scorers: list[dict] | None = None,
    ) -> list[dict]:
        documents = []
        for match in matches:
            if match["status"] != "FINISHED" or match["matchweek"] is None:
                continue
            home, away = match["home"], match["away"]
            week = match["matchweek"]
            title = (
                f"{home['name']} {match['score']['home']}-{match['score']['away']} {away['name']}"
            )
            goal_lines = [
                f"{event['player']} ({event['minute']}') for team {event['team_id']}"
                for event in match.get("events", [])
                if event["type"] in ("goal", "own_goal", "penalty")
            ]
            documents.append(
                {
                    "doc_id": f"match-{season}-mw{week:02d}-{home['team_id']}-{away['team_id']}",
                    "title": title,
                    "text": (
                        f"Premier League {season}, matchweek {week}. {title}. "
                        f"Kickoff: {match['kickoff']}. "
                        + ("Goals: " + "; ".join(goal_lines) if goal_lines else "")
                    ),
                    "category": "match_report",
                    "origin": (
                        "api-football"
                        if match.get("detail_source") == "api-football"
                        else "football-data.org"
                    ),
                    "season": season,
                    "matchweek": week,
                    "team_ids": [home["team_id"], away["team_id"]],
                    "date": match["kickoff"][:10],
                    "fetched_at": fetched_at,
                    "url": None,
                }
            )
        week = standing.get("matchweek")
        if week is not None:
            rows = standing["rows"]
            label = (
                f"Live standings during matchweek {week}"
                if standing.get("snapshot_type") == "live"
                else f"Standings after matchweek {week}"
            )
            text = f"## {label}\n" + "\n".join(
                f"{r['position']}. {r['name']}: {r['points']} points, "
                f"played {r['played']}, goal difference {r['goal_difference']}"
                for r in rows
            )
            if scorers:
                names = {row["team_id"]: row["name"] for row in rows}
                text += f"\n## Current top scorers / Golden Boot as of {fetched_at}\n"
                text += "\n".join(
                    f"{rank}. {scorer['player']} "
                    f"({names.get(scorer['team_id'], scorer['team_id'])}): "
                    + (
                        f"{scorer['goals']} goals, "
                        + (
                            f"{scorer['assists']} assists."
                            if scorer["assists"] is not None
                            else "assists not reported."
                        )
                    )
                    for rank, scorer in enumerate(scorers[:TOP_SCORERS_SHOWN], start=1)
                )
            documents.append(
                {
                    "doc_id": f"standings-{season}",
                    "title": f"Premier League {season} {label}",
                    "text": text,
                    "category": "standings",
                    "origin": "football-data.org",
                    "season": season,
                    "matchweek": week,
                    "team_ids": [r["team_id"] for r in rows],
                    "date": fetched_at[:10],
                    "fetched_at": fetched_at,
                    "url": None,
                }
            )
        for team_id in {m["home"]["team_id"] for m in matches} | {
            m["away"]["team_id"] for m in matches
        }:
            upcoming = [
                m
                for m in matches
                if m["status"] == "SCHEDULED"
                and team_id in (m["home"]["team_id"], m["away"]["team_id"])
            ]
            documents.append(
                {
                    "doc_id": f"fixtures-{season}-team-{team_id}",
                    "title": f"Premier League {season} fixtures for team {team_id}",
                    "text": "## Upcoming fixtures\n"
                    + "\n".join(
                        f"{m['kickoff']}: {m['home']['name']} vs {m['away']['name']}"
                        for m in upcoming
                    ),
                    "category": "fixtures",
                    "origin": "football-data.org",
                    "season": season,
                    "matchweek": None,
                    "team_ids": [team_id],
                    "date": fetched_at[:10],
                    "fetched_at": fetched_at,
                    "url": None,
                }
            )
        return documents

    async def list_reports(self, status: str | None, season: str | None) -> dict:
        query = select(WeeklyReport)
        if status:
            query = query.where(WeeklyReport.status == status)
        if season:
            query = query.where(WeeklyReport.season == season)
        query = query.order_by(WeeklyReport.season.desc(), WeeklyReport.matchweek.desc())
        async with self.sessions() as db:
            rows = (await db.scalars(query)).all()
        return {"items": [row.payload for row in rows]}

    async def report(self, season: str | None, matchweek: int | None, *, published: bool) -> dict:
        async with self.sessions() as db:
            if season is not None and matchweek is not None:
                row = await db.get(WeeklyReport, (season, matchweek))
            else:
                query = select(WeeklyReport)
                if season:
                    query = query.where(WeeklyReport.season == season)
                if matchweek is not None:
                    query = query.where(WeeklyReport.matchweek == matchweek)
                if published:
                    query = query.where(WeeklyReport.status == "published")
                row = await db.scalar(
                    query.order_by(WeeklyReport.season.desc(), WeeklyReport.matchweek.desc()).limit(
                        1
                    )
                )
            if row is None or (published and row.status != "published"):
                raise ServiceError("NOT_FOUND", 404, "ไม่พบรายงานที่เผยแพร่แล้ว")
            return row.payload

    async def edit_report(
        self, season: str, matchweek: int, title: str | None, markdown: str | None, actor: str
    ) -> dict:
        async with self.sessions() as db:
            row = await db.get(WeeklyReport, (season, matchweek))
            if row is None:
                raise ServiceError("NOT_FOUND", 404, "ไม่พบรายงาน")
            if row.status == "published":
                raise ServiceError("REPORT_NOT_EDITABLE", 409, "ต้องยกเลิกเผยแพร่ก่อนแก้ไข")
            payload = dict(row.payload)
            if title is not None:
                payload["title"] = title
            if markdown is not None:
                payload["markdown"] = markdown
            payload["edited_at"] = now_iso()
            payload["edited_by"] = actor
            row.payload = payload
            await db.commit()
            return payload

    async def _backfill_report_search(self, db: AsyncSession, row: WeeklyReport) -> None:
        if row.payload.get("search_text_en"):
            return
        standing = await db.get(Standing, (row.season, row.matchweek))
        matches = list(
            await db.scalars(
                select(Match).where(Match.season == row.season, Match.matchweek == row.matchweek)
            )
        )
        if not standing or not matches:
            raise ServiceError(
                "NOT_FOUND", 409, "Cannot backfill report search without source match/standing data"
            )
        payload = dict(row.payload)
        payload["search_text_en"] = report_search_text(
            row.season,
            row.matchweek,
            [match.payload for match in matches],
            standing.payload["rows"],
            [],
        )
        payload["search_text_policy"] = "source_facts"
        row.payload = payload

    async def _transition_report(
        self, season: str, matchweek: int, actor: str, request_id: str, publish: bool
    ) -> dict:
        doc_id = f"weekly-{season}-mw{matchweek:02d}"
        async with self._report_lock:
            # Repair a previous interrupted transition before starting another one.
            await self.reconcile_index(doc_id)
            async with self.sessions() as db:
                row = await db.get(WeeklyReport, (season, matchweek), with_for_update=True)
                if row is None:
                    raise ServiceError("NOT_FOUND", 404, "ไม่พบรายงาน")
                if row.status == ("published" if publish else "unpublished"):
                    return row.payload
                if not publish and row.status != "published":
                    return row.payload
                if await db.get(IndexTask, doc_id):
                    raise ServiceError("JOB_ALREADY_RUNNING", 409, "รายงานนี้กำลังเปลี่ยนสถานะ")
                if publish:
                    await self._backfill_report_search(db, row)
                db.add(
                    IndexTask(
                        doc_id=doc_id,
                        action="transition",
                        payload={"season": season, "matchweek": matchweek},
                        request_id=request_id,
                        updated_at=datetime.now(BANGKOK),
                    )
                )
                try:
                    await db.commit()
                except IntegrityError as exc:
                    await db.rollback()
                    raise ServiceError("JOB_ALREADY_RUNNING", 409, "รายงานนี้กำลังเปลี่ยนสถานะ") from exc
            try:
                if publish:
                    await self._send_index("upsert", report_doc(row.payload), doc_id, request_id)
                else:
                    await self._send_index("delete", None, doc_id, request_id)
                async with self.sessions() as db:
                    row = await db.get(WeeklyReport, (season, matchweek), with_for_update=True)
                    payload = dict(row.payload)
                    if publish:
                        payload.update(
                            status="published", published_at=now_iso(), published_by=actor
                        )
                    else:
                        payload.update(status="unpublished", published_at=None, published_by=None)
                    row.status, row.payload = payload["status"], payload
                    task = await db.get(IndexTask, doc_id)
                    await db.delete(task)
                    await db.commit()
                return payload
            except Exception as exc:
                # The durable task lets a later retry restore the index to DB state.
                try:
                    async with self.sessions() as db:
                        task = await db.get(IndexTask, doc_id)
                        if task is not None:
                            task.action = "reconcile_report"
                            task.updated_at = datetime.now(BANGKOK)
                            await db.commit()
                    await self.reconcile_index()
                except Exception:
                    pass
                raise ServiceError("INDEX_UPDATE_FAILED", 502, str(exc)) from exc

    async def publish(self, season: str, matchweek: int, actor: str, request_id: str) -> dict:
        return await self._transition_report(season, matchweek, actor, request_id, True)

    async def unpublish(self, season: str, matchweek: int, actor: str, request_id: str) -> dict:
        return await self._transition_report(season, matchweek, actor, request_id, False)

    async def run_report(
        self, job_id: str, season: str | None, matchweek: int | None, request_id: str
    ) -> None:
        async with self.sessions() as db:
            job = await db.get(Job, job_id)
            job.status = "running"
            await db.commit()
        try:
            await self._create_report(season, matchweek, request_id)
            await self._finish_job(job_id, None)
        except asyncio.CancelledError:
            await self._finish_job(job_id, "CancelledError: task cancelled")
            raise
        except Exception as exc:
            await self._finish_job(job_id, f"{type(exc).__name__}: {exc}")

    async def _create_report(
        self, season: str | None, matchweek: int | None, request_id: str
    ) -> None:
        season = season or current_season()
        async with self.sessions() as db:
            if matchweek is None:
                weeks = (
                    await db.scalars(
                        select(Match.matchweek)
                        .where(Match.season == season, Match.matchweek.is_not(None))
                        .distinct()
                    )
                ).all()
                for week in sorted(weeks, reverse=True):
                    candidates = (
                        await db.scalars(
                            select(Match).where(Match.season == season, Match.matchweek == week)
                        )
                    ).all()
                    if candidates and all(
                        row.status in ("FINISHED", "POSTPONED", "CANCELLED") for row in candidates
                    ):
                        matchweek = week
                        break
            if matchweek is None:
                raise ServiceError("MATCHWEEK_NOT_COMPLETE", 409, "ยังไม่มีแมตช์วีคที่แข่งครบ")
            standings = await db.get(Standing, (season, matchweek))
            if standings is None:
                raise ServiceError("NOT_FOUND", 404, "ยังไม่มีตารางคะแนนหลังแมตช์วีคนี้")
            matches = (
                await db.scalars(
                    select(Match).where(Match.season == season, Match.matchweek == matchweek)
                )
            ).all()
            if not matches or any(
                row.status not in ("FINISHED", "POSTPONED", "CANCELLED") for row in matches
            ):
                raise ServiceError("MATCHWEEK_NOT_COMPLETE", 409, "แมตช์วีคนี้ยังแข่งไม่ครบ")
            existing = await db.get(WeeklyReport, (season, matchweek))
            if existing and existing.status == "published":
                raise ServiceError("REPORT_ALREADY_PUBLISHED", 409, "รายงานนี้เผยแพร่แล้ว")
            scorers_row = await db.get(Scorers, season)
            match_data = [row.payload for row in matches]
            standings_data = standings.payload["rows"]
            scorers_data = scorers_row.payload["items"][:TOP_SCORERS_SHOWN] if scorers_row else []
        try:
            response = await self.http.post(
                f"{self.settings.generation_url.rstrip('/')}/report/weekly",
                json={
                    "request_id": request_id,
                    "season": season,
                    "matchweek": matchweek,
                    "language": "th",
                    "matches": match_data,
                    "standings": standings_data,
                    "top_scorers": scorers_data,
                },
                headers={"X-Request-ID": request_id},
                timeout=60,
            )
            response.raise_for_status()
            generated = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError("UPSTREAM_UNAVAILABLE", 502, str(exc)) from exc
        payload = {
            "season": season,
            "matchweek": matchweek,
            "title": generated["title"],
            "markdown": generated["markdown"],
            "highlights": generated.get("highlights", []),
            "search_text_en": report_search_text(
                season, matchweek, match_data, standings_data, scorers_data
            ),
            "search_text_policy": "source_facts",
            "status": "draft",
            "generated_at": now_iso(),
            "data_as_of": min(row["fetched_at"] for row in match_data),
            "edited_at": None,
            "edited_by": None,
            "published_at": None,
            "published_by": None,
        }
        async with self.sessions() as db:
            await db.merge(
                WeeklyReport(season=season, matchweek=matchweek, status="draft", payload=payload)
            )
            await db.commit()
        if self.settings.report_auto_publish:
            await self.publish(season, matchweek, "beat", request_id)
