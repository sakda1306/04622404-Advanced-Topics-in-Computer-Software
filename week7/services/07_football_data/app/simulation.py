"""Match prediction and season simulation (CONTRACT v1.7 §7).

07 owns the data: team strengths, simulation inputs and cached snapshots.
04 engines does the maths and keeps no state.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.db import (
    HistoricalMatch,
    HistoricalStanding,
    Match,
    ServiceState,
    SimulationSnapshot,
    Standing,
    Team,
)
from app.football import current_season, now_iso
from app.service import ServiceError
from app.strengths import tally, team_strengths

logger = logging.getLogger(__name__)

CLUBS_PATH = Path(__file__).parents[1] / "data/historical_clubs.json"
N_SIMS = 10000
SEED = 42
RELEGATION_PLACES = 3
UNAVAILABLE = "ระบบทำนายผลไม่พร้อมใช้งานตอนนี้"
# 02 waits 10 s for 07, so 07 must give up on 04 sooner and still answer with a stale snapshot.
SIMULATE_TIMEOUT_SECONDS = 5.0
# After 04 fails, skip it for a while so queued readers get the stale snapshot at once.
ENGINES_RETRY_SECONDS = 30.0


def inputs_hash(inputs: dict) -> str:
    stable = {key: value for key, value in inputs.items() if key != "as_of"}
    return hashlib.sha1(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _club_keys(teams: dict[int, dict]) -> dict[str, int | str]:
    """Historical club slug → current team_id.

    Clubs without a team_id in historical_clubs.json are matched by name / alias against
    the current Team rows, so a club that came back up still uses its own last season.
    """
    names = {}
    for team_id, payload in teams.items():
        for name in (payload.get("name"), payload.get("short_name"), *payload.get("aliases", [])):
            if isinstance(name, str) and name:
                names[name.casefold()] = team_id
    clubs = json.loads(CLUBS_PATH.read_text(encoding="utf-8"))
    keys: dict[str, int | str] = {}
    for slug, club in clubs.items():
        if club.get("team_id") is not None:
            keys[slug] = club["team_id"]
            continue
        candidates = (club.get("name"), *club.get("aliases", []))
        keys[slug] = next(
            (
                names[n.casefold()]
                for n in candidates
                if isinstance(n, str) and n.casefold() in names
            ),
            slug,
        )
    return keys


class SimulationService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker, http: httpx.AsyncClient):
        self.settings, self.sessions, self.http = settings, sessions, http
        self._locks: dict[str, asyncio.Lock] = {}
        self._engines_down_until = 0.0

    async def _data(self, season: str) -> tuple[dict, dict[int, dict]]:
        previous = str(int(season) - 1)
        async with self.sessions() as db:
            standing = (
                await db.scalars(
                    select(Standing)
                    .where(Standing.season == season)
                    .order_by(Standing.matchweek.desc())
                    .limit(1)
                )
            ).first()
            if standing is None:
                raise ServiceError("NOT_FOUND", 404, "ยังไม่มีตารางคะแนนของฤดูกาลนี้")
            teams = {row.team_id: row.payload for row in (await db.scalars(select(Team))).all()}
            matches = (await db.scalars(select(Match).where(Match.season == season))).all()
            history = (
                await db.scalars(select(HistoricalMatch).where(HistoricalMatch.season == previous))
            ).all()
            previous_table = (
                await db.scalars(
                    select(HistoricalStanding).where(HistoricalStanding.season == previous)
                )
            ).all()
            state = await db.get(ServiceState, "last_ingest_at")

        table = sorted(
            (
                {
                    "team_id": row["team_id"],
                    "name": teams.get(row["team_id"], {}).get("short_name") or row["name"],
                    "points": row["points"],
                    "goal_difference": row["goal_difference"],
                    "goals_for": row["goals_for"],
                    "played": row["played"],
                }
                for row in standing.payload["rows"]
            ),
            key=lambda row: row["team_id"],
        )
        team_ids = [row["team_id"] for row in table]
        current_results = []
        unplayed = []
        for match in matches:
            if match.status == "FINISHED":
                score = match.payload.get("score") or {}
                if isinstance(score.get("home"), int) and isinstance(score.get("away"), int):
                    current_results.append(
                        (match.home_team_id, match.away_team_id, score["home"], score["away"])
                    )
            elif (
                match.status != "CANCELLED"
                and match.home_team_id in team_ids
                and match.away_team_id in team_ids
            ):
                unplayed.append(match)
        # A live match may already be in the provider's table. When a team's `played` is
        # ahead of its finished matches, that live match is counted and must not be
        # simulated again; otherwise it is still to play.
        counted_live = {team_id: 0 for team_id in team_ids}
        for row in table:
            counted_live[row["team_id"]] = row["played"]
        for home, away, _home_goals, _away_goals in current_results:
            counted_live[home] = counted_live.get(home, 0) - 1
            counted_live[away] = counted_live.get(away, 0) - 1
        remaining = []
        for match in sorted(unplayed, key=lambda m: m.payload.get("kickoff") or ""):
            home, away = match.home_team_id, match.away_team_id
            if match.status == "LIVE" and counted_live[home] > 0 and counted_live[away] > 0:
                counted_live[home] -= 1
                counted_live[away] -= 1
                continue
            remaining.append(
                {"match_id": match.match_id, "home_team_id": home, "away_team_id": away}
            )
        remaining.sort(key=lambda m: m["match_id"])

        keys = _club_keys(teams)
        previous_results = [
            (
                keys.get(row.payload["home"], row.payload["home"]),
                keys.get(row.payload["away"], row.payload["away"]),
                row.payload["home_goals"],
                row.payload["away_goals"],
            )
            for row in history
        ]
        relegated = [
            keys.get(row.club_slug, row.club_slug)
            for row in sorted(previous_table, key=lambda r: r.payload["position"])[
                -RELEGATION_PLACES:
            ]
        ]
        strengths, league_avg, prior = team_strengths(
            tally(current_results), tally(previous_results), team_ids, relegated
        )
        if prior == "league_average":
            logger.info(json.dumps({"event": "strength_prior_league_average", "season": season}))
        inputs = {
            "season": season,
            "as_of": state.value if state else None,
            "table": table,
            "remaining": remaining,
            "strengths": {str(team_id): value for team_id, value in strengths.items()},
            "league_avg_goals": league_avg,
            "relegation_places": RELEGATION_PLACES,
        }
        return inputs, teams

    async def _engines(self, path: str, body: dict, request_id: str, timeout: float) -> dict:
        if time.monotonic() < self._engines_down_until:
            raise ServiceError("SIMULATION_UNAVAILABLE", 503, UNAVAILABLE)
        try:
            return await self._call_engines(path, body, request_id, timeout)
        except ServiceError:
            self._engines_down_until = time.monotonic() + ENGINES_RETRY_SECONDS
            raise

    async def _call_engines(self, path: str, body: dict, request_id: str, timeout: float) -> dict:
        url = self.settings.engines_url.rstrip("/") + path
        try:
            response = await self.http.post(
                url, json=body, headers={"X-Request-ID": request_id}, timeout=timeout
            )
        except httpx.HTTPError as exc:
            raise ServiceError("SIMULATION_UNAVAILABLE", 503, UNAVAILABLE) from exc
        if response.status_code >= 400:
            logger.warning(
                json.dumps(
                    {
                        "event": "engines_error",
                        "path": path,
                        "status": response.status_code,
                        "request_id": request_id,
                    }
                )
            )
            raise ServiceError("SIMULATION_UNAVAILABLE", 503, UNAVAILABLE)
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceError("SIMULATION_UNAVAILABLE", 503, UNAVAILABLE) from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            raise ServiceError("SIMULATION_UNAVAILABLE", 503, UNAVAILABLE)
        return data

    async def predict(self, home_team_id: int, away_team_id: int, request_id: str) -> dict:
        if home_team_id == away_team_id:
            raise ServiceError(
                "VALIDATION_ERROR", 422, "home_team_id และ away_team_id ต้องเป็นคนละทีม"
            )
        inputs, _teams = await self._data(current_season())
        strengths = inputs["strengths"]
        if str(home_team_id) not in strengths or str(away_team_id) not in strengths:
            raise ServiceError("NOT_FOUND", 404, "ไม่พบทีมนี้ในฤดูกาลปัจจุบัน")
        fixture = await self._next_fixture(inputs["season"], home_team_id, away_team_id)
        if fixture is not None:
            home_team_id, away_team_id = fixture
        names = {row["team_id"]: row["name"] for row in inputs["table"]}
        result = await self._engines(
            "/local/predict",
            {
                "request_id": request_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "season": inputs["season"],
                "home_strength": strengths[str(home_team_id)],
                "away_strength": strengths[str(away_team_id)],
                "league_avg_goals": inputs["league_avg_goals"],
                "home_name": names[home_team_id],
                "away_name": names[away_team_id],
            },
            request_id,
            timeout=5,
        )
        result["data"]["as_of"] = inputs["as_of"]
        return result

    async def _next_fixture(self, season: str, team_a: int, team_b: int) -> tuple[int, int] | None:
        """(home, away) of the next unplayed meeting, so home advantage goes to the real host."""
        pair = ((Match.home_team_id == team_a) & (Match.away_team_id == team_b)) | (
            (Match.home_team_id == team_b) & (Match.away_team_id == team_a)
        )
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(Match).where(
                        Match.season == season,
                        Match.status.not_in(("FINISHED", "CANCELLED")),
                        pair,
                    )
                )
            ).all()
        if not rows:
            return None
        upcoming = min(rows, key=lambda m: m.payload.get("kickoff") or "")
        return upcoming.home_team_id, upcoming.away_team_id

    async def snapshot(self, season: str | None, request_id: str) -> dict:
        selected = season or current_season()
        if selected != current_season():
            raise ServiceError("NOT_FOUND", 404, "จำลองได้เฉพาะฤดูกาลปัจจุบัน")
        inputs, teams = await self._data(selected)
        digest = inputs_hash(inputs)
        async with self._locks.setdefault(selected, asyncio.Lock()):
            async with self.sessions() as db:
                row = await db.get(SimulationSnapshot, (selected, digest))
                if row is not None:
                    # same inputs, but the data may have been re-checked since it was computed
                    return {**row.payload, "as_of": inputs["as_of"], "stale": False}
            try:
                result = await self._engines(
                    "/local/simulate",
                    {"request_id": request_id, "inputs": inputs, "n_sims": N_SIMS, "seed": SEED},
                    request_id,
                    timeout=SIMULATE_TIMEOUT_SECONDS,
                )
            except ServiceError:
                async with self.sessions() as db:
                    latest = (
                        await db.scalars(
                            select(SimulationSnapshot)
                            .where(SimulationSnapshot.season == selected)
                            .order_by(SimulationSnapshot.computed_at.desc())
                            .limit(1)
                        )
                    ).first()
                if latest is None:
                    raise
                return {**latest.payload, "stale": True}
            names = {row["team_id"]: row["name"] for row in inputs["table"]}
            payload = {
                "season": selected,
                "as_of": inputs["as_of"],
                "computed_at": now_iso(),
                "n_sims": result["data"].get("n_sims", N_SIMS),
                "model": result.get("model", "poisson-mc-v1"),
                "teams": [
                    {
                        **team,
                        "name": teams.get(team["team_id"], {}).get("name")
                        or names[team["team_id"]],
                        "short_name": names[team["team_id"]],
                    }
                    for team in result["data"].get("teams", [])
                ],
            }
            async with self.sessions() as db:
                await db.merge(
                    SimulationSnapshot(
                        season=selected,
                        inputs_hash=digest,
                        payload=payload,
                        computed_at=datetime.now(UTC),
                    )
                )
                await db.commit()
            return {**payload, "stale": False}

    async def refresh(self) -> None:
        """Called after a successful ingest so the first reader does not wait for 04."""
        try:
            await self.snapshot(None, str(uuid4()))
        except Exception:
            logger.exception("simulation refresh failed")
