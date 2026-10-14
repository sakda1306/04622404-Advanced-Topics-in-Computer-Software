"""Stub of 07 football-data (CONTRACT §7) and the index admin part of 05 (§6).

    uvicorn stubs.football_data_stub:app --port 8007

Data lives in memory. Jobs finish at once; the weekly report follows the
draft -> published -> unpublished rules of §7 so the admin pages can be built on it.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="football-data stub")

BKK = ZoneInfo("Asia/Bangkok")
FETCHED_AT = "2026-09-21T09:00:00+07:00"


def _now() -> str:
    return datetime.now(BKK).isoformat(timespec="seconds")


def _problem(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"https://errors.football-assistant.local/{code.lower().replace('_', '-')}",
            "title": code,
            "status": status,
            "code": code,
            "detail": detail,
            "service": "football-data",
            "request_id": None,
        },
        status_code=status,
        media_type="application/problem+json",
    )


MATCHES: list[dict[str, Any]] = [
    {
        "match_id": "7d3c1b52-6a8f-4d8e-9c1a-5e2f0b1a9c01",
        "external_ids": {"football_data": 537812, "api_football": 1208123},
        "season": "2026",
        "matchweek": 5,
        "kickoff": "2026-09-20T18:30:00+07:00",
        "status": "FINISHED",
        "home": {"team_id": 57, "name": "Arsenal"},
        "away": {"team_id": 61, "name": "Chelsea"},
        "score": {"home": 2, "away": 1, "half_time": {"home": 1, "away": 0}},
        "events": [
            {
                "minute": 12,
                "type": "goal",
                "team_id": 57,
                "player": "B. Saka",
                "assist": "M. Ødegaard",
            },
        ],
        "lineups": None,
        "statistics": None,
        "fetched_at": FETCHED_AT,
        "detail_source": "api-football",
    },
    {
        "match_id": "7d3c1b52-6a8f-4d8e-9c1a-5e2f0b1a9c02",
        "external_ids": {"football_data": 537820, "api_football": None},
        "season": "2026",
        "matchweek": 6,
        "kickoff": "2026-09-27T21:00:00+07:00",
        "status": "SCHEDULED",
        "home": {"team_id": 64, "name": "Liverpool"},
        "away": {"team_id": 65, "name": "Manchester City"},
        "score": {"home": None, "away": None, "half_time": {"home": None, "away": None}},
        "events": [],
        "lineups": None,
        "statistics": None,
        "fetched_at": FETCHED_AT,
        "detail_source": "none",
    },
]

STANDINGS = [
    {
        "position": 1,
        "team_id": 57,
        "name": "Arsenal",
        "played": 5,
        "won": 4,
        "draw": 1,
        "lost": 0,
        "goals_for": 12,
        "goals_against": 4,
        "goal_difference": 8,
        "points": 13,
        "form": "WWDWW",
    },
    {
        "position": 2,
        "team_id": 65,
        "name": "Manchester City",
        "played": 5,
        "won": 4,
        "draw": 0,
        "lost": 1,
        "goals_for": 11,
        "goals_against": 5,
        "goal_difference": 6,
        "points": 12,
        "form": "WLWWW",
    },
]

TEAMS = [
    {
        "team_id": 57,
        "name": "Arsenal FC",
        "short_name": "Arsenal",
        "tla": "ARS",
        "aliases": ["ปืนใหญ่", "ปืน", "อาร์เซนอล", "the gunners"],
        "crest_url": None,
    },
    {
        "team_id": 66,
        "name": "Manchester United FC",
        "short_name": "Man United",
        "tla": "MUN",
        "aliases": ["ผี", "แมนยู", "ปีศาจแดง"],
        "crest_url": None,
    },
]

REPORTS: dict[tuple[str, int], dict[str, Any]] = {
    ("2026", 5): {
        "season": "2026",
        "matchweek": 5,
        "title": "สรุปพรีเมียร์ลีก 2026/27 นัดที่ 5",
        "markdown": "## ผลการแข่งขัน\n- Arsenal 2–1 Chelsea\n\n## ไฮไลต์\nArsenal ขึ้นจ่าฝูง",
        "highlights": ["Arsenal ชนะ Chelsea 2–1 ขึ้นจ่าฝูง"],
        "status": "draft",
        "generated_at": "2026-09-22T09:02:00+07:00",
        "data_as_of": "2026-09-22T09:00:00+07:00",
        "edited_at": None,
        "edited_by": None,
        "published_at": None,
        "published_by": None,
    }
}

JOBS: list[dict[str, Any]] = []
INDEX_DOCS = {"trivia-0001", "match-2026-mw05-57-61", "standings-2026-mw05"}
_INITIAL = copy.deepcopy((REPORTS, INDEX_DOCS))


def reset_state() -> None:
    """Back to the starting data (used between tests)."""
    reports, docs = copy.deepcopy(_INITIAL)
    REPORTS.clear()
    REPORTS.update(reports)
    INDEX_DOCS.clear()
    INDEX_DOCS.update(docs)
    JOBS.clear()
    PREDICT_CALLS.clear()
    SIMULATION_STATE.update(calls=0, stale=False)


def _job(kind: str, scope: str | None, triggered_by: str) -> dict[str, Any]:
    job = {
        "job_id": str(uuid.uuid4()),
        "kind": kind,
        "scope": scope,
        "status": "done",
        "triggered_by": triggered_by,
        "started_at": _now(),
        "finished_at": _now(),
        "detail": None,
    }
    JOBS.insert(0, job)
    return job


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "football-data", "version": "stub"}


@app.get("/football/status")
async def status() -> dict[str, Any]:
    return {
        "current_season": "2026",
        "current_matchweek": 6,
        "last_ingest_at": FETCHED_AT,
        "last_report_matchweek": 5,
        "quota": {
            "api_football_used_today": 12,
            "api_football_limit": 90,
            "reset_at": "2026-09-25T07:00:00+07:00",
        },
    }


@app.get("/football/standings")
async def standings(season: str = "2026") -> dict[str, Any]:
    return {"season": season, "matchweek": 5, "fetched_at": FETCHED_AT, "rows": STANDINGS}


@app.get("/football/fixtures")
async def fixtures(
    season: str = "2026",
    matchweek: int | None = None,
    team_id: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    matches = [
        m
        for m in MATCHES
        if m["season"] == season
        and (matchweek is None or m["matchweek"] == matchweek)
        and (team_id is None or team_id in (m["home"]["team_id"], m["away"]["team_id"]))
        and (status is None or m["status"] == status)
    ]
    return {"season": season, "fetched_at": FETCHED_AT, "matches": matches}


PREDICT_CALLS: list[tuple[int, int]] = []


@app.get("/football/predict", response_model=None)
async def predict(home_team_id: int, away_team_id: int) -> dict[str, Any] | JSONResponse:
    PREDICT_CALLS.append((home_team_id, away_team_id))
    if home_team_id == 999 or away_team_id == 999:
        return _problem(503, "SIMULATION_UNAVAILABLE", "ระบบทำนายผลไม่พร้อมใช้งานตอนนี้")
    return {
        "engine": "local_ai",
        "content": "Arsenal ชนะ 48%",
        "data": {
            "home_win": 0.48,
            "draw": 0.26,
            "away_win": 0.26,
            "home_xg": 1.6,
            "away_xg": 1.0,
            "most_likely_score": {"home": 1, "away": 0},
            "method": "poisson-v1",
            "matches_used": 43,
            "as_of": FETCHED_AT,
        },
        "sources": [],
        "model": "poisson-v1",
        "latency_ms": 3,
        "token_usage": {"input": 0, "output": 0},
    }


SIMULATION_STATE: dict[str, Any] = {"calls": 0, "stale": False}


@app.get("/football/simulation")
async def simulation(season: str | None = None) -> dict[str, Any]:
    SIMULATION_STATE["calls"] += 1
    return {
        "season": season or "2026",
        "as_of": FETCHED_AT,
        "computed_at": FETCHED_AT,
        "stale": SIMULATION_STATE["stale"],
        "n_sims": 10000,
        "model": "poisson-mc-v1",
        "teams": [
            {
                "team_id": 57,
                "name": "Arsenal FC",
                "short_name": "Arsenal",
                "points": 12,
                "expected_points": 74.3,
                "p_title": 0.31,
                "p_top4": 0.82,
                "p_relegation": 0.0,
                "position_probs": [0.31, 0.69],
            }
        ],
    }


@app.get("/football/matches/{match_id}", response_model=None)
async def match(match_id: str) -> dict[str, Any] | JSONResponse:
    for m in MATCHES:
        if m["match_id"] == match_id:
            return m
    return _problem(404, "NOT_FOUND", "ไม่พบนัดนี้")


@app.get("/football/reports/weekly", response_model=None)
async def published_report(
    season: str | None = None, matchweek: int | None = None
) -> dict[str, Any] | JSONResponse:
    published = [
        r
        for r in REPORTS.values()
        if r["status"] == "published"
        and (season is None or r["season"] == season)
        and (matchweek is None or r["matchweek"] == matchweek)
    ]
    if not published:
        return _problem(404, "NOT_FOUND", "ยังไม่มีรายงานที่เผยแพร่")
    return max(published, key=lambda r: (r["season"], r["matchweek"]))


@app.get("/football/teams")
async def teams() -> dict[str, Any]:
    return {"teams": TEAMS}


@app.post("/ingest/run", status_code=202)
async def ingest(request: Request) -> dict[str, Any]:
    body = await request.json()
    job = _job("ingest", body.get("scope", "all"), body.get("triggered_by", "unknown"))
    return {"job_id": job["job_id"], "scope": job["scope"]}


@app.post("/reports/weekly/run", status_code=202)
async def run_report(request: Request) -> dict[str, Any]:
    body = await request.json()
    job = _job("weekly_report", None, body.get("triggered_by", "unknown"))
    return {"job_id": job["job_id"]}


@app.get("/jobs")
async def jobs(limit: int = 20) -> dict[str, Any]:
    return {"jobs": JOBS[:limit]}


@app.get("/jobs/{job_id}", response_model=None)
async def job(job_id: str) -> dict[str, Any] | JSONResponse:
    for j in JOBS:
        if j["job_id"] == job_id:
            return j
    return _problem(404, "NOT_FOUND", "ไม่พบ job นี้")


@app.get("/reports/weekly/list")
async def reports(status: str | None = None, season: str | None = None) -> dict[str, Any]:
    items = [
        r
        for r in REPORTS.values()
        if (status is None or r["status"] == status) and (season is None or r["season"] == season)
    ]
    return {"items": items}


@app.get("/reports/weekly/{season}/{matchweek}", response_model=None)
async def report(season: str, matchweek: int) -> dict[str, Any] | JSONResponse:
    found = REPORTS.get((season, matchweek))
    return found if found else _problem(404, "NOT_FOUND", "ไม่พบรายงานนี้")


@app.patch("/reports/weekly/{season}/{matchweek}", response_model=None)
async def edit_report(
    season: str, matchweek: int, request: Request
) -> dict[str, Any] | JSONResponse:
    found = REPORTS.get((season, matchweek))
    if not found:
        return _problem(404, "NOT_FOUND", "ไม่พบรายงานนี้")
    if found["status"] == "published":
        return _problem(409, "REPORT_NOT_EDITABLE", "ต้อง unpublish ก่อน")
    body = await request.json()
    for key in ("title", "markdown"):
        if key in body:
            found[key] = body[key]
    found["edited_at"] = _now()
    found["edited_by"] = body.get("edited_by")
    return found


@app.post("/reports/weekly/{season}/{matchweek}/publish", response_model=None)
async def publish(season: str, matchweek: int, request: Request) -> dict[str, Any] | JSONResponse:
    found = REPORTS.get((season, matchweek))
    if not found:
        return _problem(404, "NOT_FOUND", "ไม่พบรายงานนี้")
    body = await request.json()
    found.update(status="published", published_at=_now(), published_by=body.get("published_by"))
    INDEX_DOCS.add(f"weekly-{season}-mw{matchweek:02d}")
    return found


@app.post("/reports/weekly/{season}/{matchweek}/unpublish", response_model=None)
async def unpublish(season: str, matchweek: int) -> dict[str, Any] | JSONResponse:
    found = REPORTS.get((season, matchweek))
    if not found:
        return _problem(404, "NOT_FOUND", "ไม่พบรายงานนี้")
    found["status"] = "unpublished"
    INDEX_DOCS.discard(f"weekly-{season}-mw{matchweek:02d}")
    return found


# ---- 05 retrieval index admin (§6), served here so one stub covers the admin pages ----


@app.get("/index/stats")
async def index_stats() -> dict[str, Any]:
    by_category: dict[str, int] = {}
    for doc_id in INDEX_DOCS:
        category = {"match": "match_report", "weekly": "weekly_report"}.get(
            doc_id.split("-")[0], doc_id.split("-")[0]
        )
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "documents": len(INDEX_DOCS),
        "chunks": len(INDEX_DOCS),
        "by_category": by_category,
        "index_version": _now(),
    }


@app.delete("/index/{doc_id}")
async def delete_doc(doc_id: str) -> dict[str, bool]:
    existed = doc_id in INDEX_DOCS
    INDEX_DOCS.discard(doc_id)
    return {"deleted": existed}


@app.post("/index/rebuild", status_code=202)
async def rebuild() -> dict[str, str]:
    return {"job_id": str(uuid.uuid4())}
