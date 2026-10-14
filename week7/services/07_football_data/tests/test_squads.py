import contextlib
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import Squad
from app.football import current_season, squad_document, squad_payload
from app.main import create_app
from app.service import ServiceError

FETCHED_AT = "2026-09-30T10:00:00+07:00"


def raw_team(**overrides) -> dict:
    team = {
        "id": 57,
        "name": "Arsenal FC",
        "coach": {"id": 11, "name": "Mikel Arteta", "nationality": "Spain"},
        "squad": [
            {
                "id": 3189,
                "name": "Kepa Arrizabalaga",
                "position": "Goalkeeper",
                "dateOfBirth": "1994-10-03",
                "nationality": "Spain",
            },
            {
                "id": 4001,
                "name": "Martin Ødegaard",
                "position": "Midfielder",
                "dateOfBirth": "1998-12-17",
                "nationality": "Norway",
            },
        ],
    }
    team.update(overrides)
    return team


def test_squad_payload_maps_players_and_coach():
    squad = squad_payload(raw_team(), FETCHED_AT)
    assert squad["team_id"] == 57
    assert squad["team_name"] == "Arsenal FC"
    assert squad["coach"] == {"id": 11, "name": "Mikel Arteta", "nationality": "Spain"}
    assert squad["fetched_at"] == FETCHED_AT
    assert squad["players"][0] == {
        "id": 3189,
        "name": "Kepa Arrizabalaga",
        "position": "Goalkeeper",
        "date_of_birth": "1994-10-03",
        "nationality": "Spain",
    }


@pytest.mark.parametrize("squad", [[], None])
def test_squad_payload_is_none_when_squad_is_empty_or_null(squad):
    assert squad_payload(raw_team(squad=squad), FETCHED_AT) is None


def test_squad_payload_is_none_when_squad_key_is_missing():
    team = raw_team()
    del team["squad"]
    assert squad_payload(team, FETCHED_AT) is None


def test_squad_payload_skips_players_without_a_name():
    team = raw_team(squad=[{"id": 1, "name": ""}, {"id": 2, "name": "Bukayo Saka"}])
    squad = squad_payload(team, FETCHED_AT)
    assert [p["name"] for p in squad["players"]] == ["Bukayo Saka"]


@pytest.mark.parametrize("coach", [None, {}, {"id": 5, "name": ""}])
def test_squad_payload_coach_is_none_when_missing_or_nameless(coach):
    assert squad_payload(raw_team(coach=coach), FETCHED_AT)["coach"] is None


def test_squad_document_follows_the_contract_shape():
    document = squad_document(squad_payload(raw_team(), FETCHED_AT), "2026")
    assert document["doc_id"] == "players-2026-team-57"
    assert document["category"] == "player"
    assert document["origin"] == "football-data.org"
    assert document["season"] == "2026"
    assert document["matchweek"] is None
    assert document["team_ids"] == [57]
    assert document["date"] == "2026-09-30"
    assert document["fetched_at"] == FETCHED_AT
    assert document["url"] is None
    assert document["title"] == "Arsenal FC squad 2026"


def test_squad_document_has_one_heading_per_player_and_keeps_special_characters():
    text = squad_document(squad_payload(raw_team(), FETCHED_AT), "2026")["text"]
    assert text.startswith("Premier League 2026 squad: Arsenal FC. Coach: Mikel Arteta.")
    assert text.count("\n## ") == 4  # two players and two position lists
    assert "## Martin Ødegaard" in text
    assert (
        "Team: Arsenal FC. Position: Midfielder. Date of birth: 1998-12-17. Nationality: Norway."
    ) in text


def test_squad_document_never_prints_none_for_missing_fields():
    team = raw_team(coach=None, squad=[{"id": 9, "name": "Trialist"}])
    text = squad_document(squad_payload(team, FETCHED_AT), "2026")["text"]
    assert "None" not in text
    assert "Coach:" not in text
    assert "Position: unknown. Date of birth: unknown. Nationality: unknown." in text


def squad_text(players):
    return squad_document(squad_payload(raw_team(squad=players), FETCHED_AT), "2026")["text"]


def player(name, position):
    return {"id": abs(hash(name)) % 10_000, "name": name, "position": position}


# Live chat test 2026-10-05: "นักเตะในทีม Arsenal มีใครบ้าง" listed 4 of 24 players, because
# each player is its own chunk and only five chunks reach generation; "กองหน้า" found nothing,
# because the provider says "Offence". The first chunk now lists the whole squad by position.
def test_first_chunk_lists_the_whole_squad_by_position():
    text = squad_text(
        [
            player("Kepa Arrizabalaga", "Goalkeeper"),
            player("William Saliba", "Defence"),
            player("Ben White", "Defence"),
            player("Declan Rice", "Midfield"),
            player("Bukayo Saka", "Offence"),
            player("Trialist", None),
        ]
    )
    first_chunk = text.split("\n## ", 1)[0]
    assert first_chunk == (
        "Premier League 2026 squad: Arsenal FC. Coach: Mikel Arteta.\n"
        "Arsenal FC squad list (6 players):\n"
        "Goalkeepers (1): Kepa Arrizabalaga.\n"
        "Defenders (2): William Saliba, Ben White.\n"
        "Midfielders (1): Declan Rice.\n"
        "Forwards (1): Bukayo Saka.\n"
        "Position not listed (1): Trialist.\n"
    )


def test_squad_list_accepts_both_spellings_and_keeps_unknown_labels():
    text = squad_text(
        [
            player("Martin Ødegaard", "Midfielder"),
            player("Gabriel Jesus", "Forward"),
            player("Riccardo Calafiori", "Defender"),
            player("Ethan Nwaneri", "Centre-Forward"),
        ]
    )
    assert "Midfielders (1): Martin Ødegaard.\n" in text
    assert "Forwards (1): Gabriel Jesus.\n" in text
    assert "Defenders (1): Riccardo Calafiori.\n" in text
    assert "Centre-Forward (1): Ethan Nwaneri.\n" in text
    assert "Goalkeepers" not in text


# Live chat test 2026-10-05: "Everton มีกองหน้าคนไหนบ้าง" still found nothing; the long squad
# list lost to the short one-player chunks. Each position also gets a short chunk of its own.
def test_each_position_has_a_short_chunk_of_its_own():
    text = squad_text(
        [
            player("Kepa Arrizabalaga", "Goalkeeper"),
            player("William Saliba", "Defence"),
            player("Declan Rice", "Midfield"),
            player("Bukayo Saka", "Offence"),
            player("Kai Havertz", "Offence"),
            player("Trialist", None),
        ]
    )
    assert "## Arsenal FC forwards\nArsenal FC forwards (2): Bukayo Saka, Kai Havertz.\n" in text
    assert "## Arsenal FC goalkeepers\nArsenal FC goalkeepers (1): Kepa Arrizabalaga.\n" in text
    assert "## Arsenal FC defenders\n" in text and "## Arsenal FC midfielders\n" in text
    assert "## Arsenal FC position not listed" not in text
    # Position chunks come before the player chunks, after the squad list.
    assert (
        text.index("squad list")
        < text.index("## Arsenal FC goalkeepers")
        < text.index("## Kepa Arrizabalaga")
    )


def upstream_factory(indexed: dict, teams: list[dict]):
    async def upstream(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/teams"):
            return httpx.Response(200, json={"teams": teams})
        if path.endswith("/matches"):
            return httpx.Response(200, json={"matches": []})
        if path.endswith("/standings"):
            return httpx.Response(
                200,
                json={
                    "season": {"currentMatchday": 1},
                    "standings": [{"type": "TOTAL", "table": []}],
                },
            )
        if path.endswith("/scorers"):
            return httpx.Response(200, json={"scorers": []})
        if path == "/index/upsert":
            for document in json.loads(request.content)["documents"]:
                indexed[document["doc_id"]] = document
            return httpx.Response(200, json={"upserted": 1})
        if request.method == "DELETE" and path.startswith("/index/"):
            indexed.pop(path.removeprefix("/index/"), None)
            return httpx.Response(200, json={"deleted": True})
        raise AssertionError(f"unexpected request: {request.url}")

    return upstream


async def run_ingest(tmp_path, teams, *, player_index_enabled):
    indexed: dict = {}
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
        football_data_api_key="test-key",
        player_index_enabled=player_index_enabled,
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_factory(indexed, teams)))
    app = create_app(settings, http=client)
    async with app.router.lifespan_context(app):
        service = app.state.service
        await service._ingest_primary(str(uuid4()))
        await service.reconcile_index()
        async with service.sessions() as db:
            rows = {row.team_id: row.payload for row in await db.scalars(select(Squad))}
    await client.aclose()
    return indexed, rows


async def test_ingest_stores_squads_and_indexes_player_documents_when_enabled(tmp_path):
    season = current_season()
    teams = [raw_team(), raw_team(id=61, name="Chelsea FC", squad=[], coach=None)]
    indexed, rows = await run_ingest(tmp_path, teams, player_index_enabled=True)

    assert set(rows) == {57}  # Chelsea has no squad, so it is skipped without failing
    assert rows[57]["players"][1]["name"] == "Martin Ødegaard"
    document = indexed[f"players-{season}-team-57"]
    assert document["category"] == "player"
    assert "## Martin Ødegaard" in document["text"]
    assert f"players-{season}-team-61" not in indexed


async def test_ingest_stores_squads_but_indexes_nothing_when_flag_is_off(tmp_path):
    season = current_season()
    indexed, rows = await run_ingest(tmp_path, [raw_team()], player_index_enabled=False)

    assert set(rows) == {57}
    assert f"players-{season}-team-57" not in indexed
    assert not any(doc["category"] == "player" for doc in indexed.values())


async def test_second_ingest_replaces_rows_and_keeps_one_document_per_team(tmp_path):
    season = current_season()
    await run_ingest(tmp_path, [raw_team()], player_index_enabled=True)
    changed = raw_team(squad=[{"id": 7, "name": "Only Player", "position": "Defender"}])
    indexed, rows = await run_ingest(tmp_path, [changed], player_index_enabled=True)

    assert [p["name"] for p in rows[57]["players"]] == ["Only Player"]
    assert list(indexed).count(f"players-{season}-team-57") == 1


async def test_squad_endpoint_returns_stored_payload_and_404_when_missing(tmp_path):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
        football_data_api_key="test-key",
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_factory({}, [raw_team()])))
    app = create_app(settings, http=client)
    async with app.router.lifespan_context(app):
        await app.state.service._ingest_primary(str(uuid4()))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            found = await api.get("/football/teams/57/squad")
            assert found.status_code == 200
            assert found.json()["team_name"] == "Arsenal FC"
            assert len(found.json()["players"]) == 2

            missing = await api.get("/football/teams/999/squad")
            assert missing.status_code == 404
    await client.aclose()


@pytest.mark.parametrize("coach", ["N/A", 42, ["x"]])
def test_squad_payload_ignores_malformed_coach(coach):
    assert squad_payload(raw_team(coach=coach), FETCHED_AT)["coach"] is None


def test_squad_payload_skips_malformed_player_entries():
    team = raw_team(squad=[None, "x", 3, {"id": 2, "name": "Bukayo Saka"}])
    squad = squad_payload(team, FETCHED_AT)
    assert [p["name"] for p in squad["players"]] == ["Bukayo Saka"]


async def test_ingest_survives_malformed_squad_shapes(tmp_path):
    teams = [raw_team(coach="N/A", squad=[None, {"id": 2, "name": "Bukayo Saka"}])]
    _indexed, rows = await run_ingest(tmp_path, teams, player_index_enabled=False)
    assert [p["name"] for p in rows[57]["players"]] == ["Bukayo Saka"]


async def test_rejected_player_batch_does_not_block_other_documents(tmp_path):
    season = current_season()
    indexed: dict = {}
    finished = {
        "id": 12345,
        "season": {"startDate": f"{season}-08-01"},
        "matchday": 5,
        "utcDate": f"{season}-09-20T11:30:00Z",
        "status": "FINISHED",
        "homeTeam": {"id": 57, "name": "Arsenal FC"},
        "awayTeam": {"id": 61, "name": "Chelsea FC"},
        "score": {"fullTime": {"home": 2, "away": 1}, "halfTime": {"home": 1, "away": 0}},
    }
    teams = [raw_team(), raw_team(id=61, name="Chelsea FC", squad=[], coach=None)]
    healthy = upstream_factory(indexed, teams)

    async def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json={"matches": [finished]})
        if request.url.path == "/index/upsert":
            documents = json.loads(request.content)["documents"]
            if any(doc["category"] == "player" for doc in documents):
                return httpx.Response(422)  # 05 does not know category "player" yet
        return await healthy(request)

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
        football_data_api_key="test-key",
        player_index_enabled=True,
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    app = create_app(settings, http=client)
    async with app.router.lifespan_context(app):
        service = app.state.service
        await service._ingest_primary(str(uuid4()))
        with contextlib.suppress(ServiceError):
            await service.reconcile_index()
    await client.aclose()

    assert f"match-{season}-mw05-57-61" in indexed
    assert f"standings-{season}" in indexed
    assert f"players-{season}-team-57" not in indexed


async def test_ingest_puts_scorer_stats_into_the_player_document(tmp_path, monkeypatch):
    import app.service as service_module

    season = current_season()
    original = service_module.fetch_primary

    async def fake_fetch(http, settings, path, season_, request_id, throttle=None, params=None):
        if path.endswith("/scorers"):
            return {
                "scorers": [
                    {
                        "player": {"id": 4001, "name": "Martin Ødegaard"},
                        "team": {"id": 57},
                        "playedMatches": 6,
                        "goals": 2,
                        "assists": None,
                        "penalties": None,
                    }
                ]
            }
        return await original(http, settings, path, season_, request_id, throttle, params)

    monkeypatch.setattr(service_module, "fetch_primary", fake_fetch)
    indexed, _rows = await run_ingest(tmp_path, [raw_team()], player_index_enabled=True)
    text = indexed[f"players-{season}-team-57"]["text"]
    assert "2 goals in 6 matches. Assists: not reported." in text
    assert text.count("season so far") == 1
