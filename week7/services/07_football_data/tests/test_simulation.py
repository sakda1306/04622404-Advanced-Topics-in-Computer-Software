import json

import httpx
import pytest

from app.config import Settings
from app.db import HistoricalMatch, Match, ServiceState, Standing, Team
from app.football import current_season
from app.main import create_app
from app.service import ServiceError
from app.simulation import inputs_hash


def engine_handler(state):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state["calls"].append((request.url.path, body))
        state.setdefault("timeouts", []).append(request.extensions.get("timeout", {}).get("read"))
        if state.get("fail"):
            return httpx.Response(503, json={"code": "LLM_UNAVAILABLE"})
        if request.url.path == "/local/predict":
            return httpx.Response(
                200,
                json={
                    "engine": "local_ai",
                    "content": "Arsenal ชนะ 50%",
                    "data": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
                    "sources": [],
                    "model": "poisson-v1",
                    "latency_ms": 1,
                    "token_usage": {"input": 0, "output": 0},
                },
            )
        if request.url.path == "/local/simulate":
            teams = [
                {
                    "team_id": r["team_id"],
                    "points": r["points"],
                    "expected_points": float(r["points"]),
                    "p_title": 0.5,
                    "p_top4": 1.0,
                    "p_relegation": 0.0,
                    "position_probs": [0.5, 0.5],
                }
                for r in body["inputs"]["table"]
            ]
            return httpx.Response(
                200,
                json={
                    "engine": "local_ai",
                    "content": "จำลอง",
                    "data": {
                        "season": body["inputs"]["season"],
                        "as_of": body["inputs"]["as_of"],
                        "n_sims": body["n_sims"],
                        "remaining_matches": len(body["inputs"]["remaining"]),
                        "teams": teams,
                    },
                    "sources": [],
                    "model": "poisson-mc-v1",
                    "latency_ms": 1,
                    "token_usage": {"input": 0, "output": 0},
                },
            )
        raise AssertionError(request.url.path)

    return handler


def standing_row(team_id, name, points, gd, gf, played):
    return {
        "position": 1,
        "team_id": team_id,
        "name": name,
        "played": played,
        "won": 0,
        "draw": 0,
        "lost": 0,
        "goals_for": gf,
        "goals_against": gf - gd,
        "goal_difference": gd,
        "points": points,
    }


async def seed(app, *, history=True):
    season = current_season()
    previous = str(int(season) - 1)
    async with app.state.service.sessions() as db:
        db.add(
            Standing(
                season=season,
                matchweek=1,
                payload={
                    "season": season,
                    "matchweek": 1,
                    "rows": [
                        standing_row(57, "Arsenal FC", 3, 1, 2, 1),
                        standing_row(61, "Chelsea FC", 0, -1, 1, 1),
                    ],
                },
            )
        )
        db.add(
            Team(team_id=57, payload={"team_id": 57, "name": "Arsenal FC", "short_name": "Arsenal"})
        )
        db.add(
            Team(team_id=61, payload={"team_id": 61, "name": "Chelsea FC", "short_name": "Chelsea"})
        )
        db.add(
            Match(
                match_id="m1",
                external_id=1,
                season=season,
                matchweek=1,
                home_team_id=57,
                away_team_id=61,
                status="FINISHED",
                payload={"kickoff": "2026-08-20T20:00:00+07:00", "score": {"home": 2, "away": 1}},
            )
        )
        db.add(
            Match(
                match_id="m2",
                external_id=2,
                season=season,
                matchweek=2,
                home_team_id=61,
                away_team_id=57,
                status="SCHEDULED",
                payload={
                    "kickoff": "2026-12-20T20:00:00+07:00",
                    "score": {"home": None, "away": None},
                },
            )
        )
        if history:
            db.add(
                HistoricalMatch(
                    match_id="h1",
                    season=previous,
                    home_slug="arsenal",
                    away_slug="chelsea",
                    payload={
                        "home": "arsenal",
                        "away": "chelsea",
                        "home_goals": 3,
                        "away_goals": 0,
                    },
                )
            )
        await db.commit()


async def finish_second_match(app):
    async with app.state.service.sessions() as db:
        row = await db.get(Match, "m2")
        row.status = "FINISHED"
        row.payload = {**row.payload, "score": {"home": 1, "away": 1}}
        await db.commit()


def make(tmp_path, state):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}", _env_file=None
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(engine_handler(state)))
    return create_app(settings, http=http), http


@pytest.mark.parametrize("history", [True, False])
async def test_predict_sends_strengths_and_names(tmp_path, history):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app, history=history)
        result = await app.state.simulation.predict(61, 57, "req-1")
    await http.aclose()
    path, body = state["calls"][0]
    assert path == "/local/predict"
    assert (body["home_name"], body["away_name"]) == ("Chelsea", "Arsenal")
    assert body["away_strength"]["attack"] > body["home_strength"]["attack"]
    assert body["league_avg_goals"] > 0
    assert "as_of" in result["data"]


async def test_predict_rejects_same_team_and_unknown_team(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        with pytest.raises(ServiceError) as same:
            await app.state.simulation.predict(57, 57, "req-1")
        with pytest.raises(ServiceError) as unknown:
            await app.state.simulation.predict(57, 999, "req-1")
    await http.aclose()
    assert (same.value.status, unknown.value.status) == (422, 404)
    assert state["calls"] == []


async def test_snapshot_is_computed_once_per_input(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        first = await app.state.simulation.snapshot(None, "req-1")
        second = await app.state.simulation.snapshot(None, "req-2")
    await http.aclose()
    assert [c[0] for c in state["calls"]] == ["/local/simulate"]
    body = state["calls"][0][1]
    assert (body["n_sims"], body["seed"]) == (10000, 42)
    assert [m["match_id"] for m in body["inputs"]["remaining"]] == ["m2"]
    assert first["stale"] is False and second["stale"] is False
    assert {t["short_name"] for t in first["teams"]} == {"Arsenal", "Chelsea"}
    assert first["model"] == "poisson-mc-v1"


def test_inputs_hash_ignores_as_of():
    base = {"season": "2026", "table": [], "as_of": "a"}
    assert inputs_hash(base) == inputs_hash({**base, "as_of": "b"})
    assert inputs_hash(base) != inputs_hash({**base, "season": "2027"})


async def api_get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_predict_endpoint_and_errors(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        ok = await api_get(app, "/football/predict?home_team_id=57&away_team_id=61")
        same = await api_get(app, "/football/predict?home_team_id=57&away_team_id=57")
        missing = await api_get(app, "/football/predict?home_team_id=57&away_team_id=999")
        state["fail"] = True
        down = await api_get(app, "/football/predict?home_team_id=57&away_team_id=61")
    await http.aclose()
    assert ok.status_code == 200 and ok.json()["data"]["home_win"] == 0.5
    assert (same.status_code, same.json()["code"]) == (422, "VALIDATION_ERROR")
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    assert (down.status_code, down.json()["code"]) == (503, "SIMULATION_UNAVAILABLE")


async def test_simulation_endpoint(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        ok = await api_get(app, "/football/simulation")
        other = await api_get(app, "/football/simulation?season=1999")
    await http.aclose()
    assert ok.status_code == 200 and ok.json()["n_sims"] == 10000
    assert other.status_code == 404


async def test_simulation_is_stale_when_engines_fail_after_a_snapshot(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        await api_get(app, "/football/simulation")
        state["fail"] = True
        await finish_second_match(app)  # inputs change → new hash → must call 04 again
        stale = await api_get(app, "/football/simulation")
    await http.aclose()
    assert stale.status_code == 200
    assert stale.json()["stale"] is True


async def test_simulation_503_without_any_snapshot(tmp_path):
    state = {"calls": [], "fail": True}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        down = await api_get(app, "/football/simulation")
    await http.aclose()
    assert (down.status_code, down.json()["code"]) == (503, "SIMULATION_UNAVAILABLE")


async def test_ingest_refreshes_the_simulation(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        await app.state.service._reconcile_after_ingest()
    await http.aclose()
    assert "/local/simulate" in [path for path, _ in state["calls"]]


async def test_club_without_team_id_in_reference_uses_its_own_history(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    season = current_season()
    async with app.router.lifespan_context(app):
        await seed(app, history=False)
        async with app.state.service.sessions() as db:
            row = await db.get(Standing, (season, 1))
            row.payload = {
                **row.payload,
                "rows": [
                    *row.payload["rows"],
                    standing_row(76, "Wolverhampton Wanderers FC", 0, 0, 0, 0),
                ],
            }
            db.add(
                Team(
                    team_id=76,
                    payload={
                        "team_id": 76,
                        "name": "Wolverhampton Wanderers FC",
                        "short_name": "Wolverhampton",
                    },
                )
            )
            db.add(
                HistoricalMatch(
                    match_id="h2",
                    season=str(int(season) - 1),
                    home_slug="wolves",
                    away_slug="arsenal",
                    payload={"home": "wolves", "away": "arsenal", "home_goals": 4, "away_goals": 0},
                )
            )
            await db.commit()
        await app.state.simulation.predict(76, 57, "req-1")
    await http.aclose()
    body = state["calls"][0][1]
    # wolves has no team_id in historical_clubs.json; its own 4-0 must still count
    assert body["home_strength"]["matches_used"] == 1
    assert body["home_strength"]["attack"] > 3


async def test_engines_failure_is_remembered_so_stale_is_served_fast(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        await api_get(app, "/football/simulation")
        state["fail"] = True
        await finish_second_match(app)
        first = await api_get(app, "/football/simulation")
        second = await api_get(app, "/football/simulation")
    await http.aclose()
    assert first.json()["stale"] is True and second.json()["stale"] is True
    # the second request must not wait on 04 again right after a failure
    assert [path for path, _ in state["calls"]] == ["/local/simulate", "/local/simulate"]
    # 07 must give up on 04 well before 02 (10 s) gives up on 07
    assert max(state["timeouts"]) <= 5


async def test_predict_uses_the_home_side_of_the_next_fixture(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)  # m2: Chelsea (61) at home to Arsenal (57), not played yet
        await app.state.simulation.predict(57, 61, "req-1")
    await http.aclose()
    body = state["calls"][0][1]
    assert (body["home_team_id"], body["away_team_id"]) == (61, 57)
    assert body["home_name"] == "Chelsea"


async def test_cached_snapshot_reports_the_latest_data_time(tmp_path):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        await app.state.simulation.snapshot(None, "req-1")
        async with app.state.service.sessions() as db:
            await db.merge(ServiceState(key="last_ingest_at", value="2026-10-02T09:00:00+07:00"))
            await db.commit()
        again = await app.state.simulation.snapshot(None, "req-2")
    await http.aclose()
    assert [path for path, _ in state["calls"]] == ["/local/simulate"]
    assert again["as_of"] == "2026-10-02T09:00:00+07:00"


async def set_m2_live(app, *, counted_in_table):
    season = current_season()
    async with app.state.service.sessions() as db:
        match = await db.get(Match, "m2")
        match.status = "LIVE"
        if counted_in_table:
            standing = await db.get(Standing, (season, 1))
            standing.payload = {
                **standing.payload,
                "rows": [{**row, "played": row["played"] + 1} for row in standing.payload["rows"]],
            }
        await db.commit()


@pytest.mark.parametrize("counted_in_table, simulated", [(True, False), (False, True)])
async def test_live_match_is_simulated_only_if_the_table_has_not_counted_it(
    tmp_path, counted_in_table, simulated
):
    state = {"calls": []}
    app, http = make(tmp_path, state)
    async with app.router.lifespan_context(app):
        await seed(app)
        await set_m2_live(app, counted_in_table=counted_in_table)
        await app.state.simulation.snapshot(None, "req-1")
    await http.aclose()
    remaining = [m["match_id"] for m in state["calls"][0][1]["inputs"]["remaining"]]
    assert ("m2" in remaining) is simulated
