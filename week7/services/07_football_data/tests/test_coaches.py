import json
from uuid import uuid4

import httpx
import pytest

from app.coaches import (
    CoachFetchError,
    coach_document,
    coach_query,
    current_coach,
    fetch_coaches,
    load_club_qids,
    parse_coaches,
)
from app.config import Settings
from app.football import current_season
from app.main import create_app

CURRENT_TEAMS = {
    57,
    58,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    71,
    73,
    76,
    328,
    341,
    351,
    354,
    397,
    402,
    563,
    1044,
}


def binding(qid, name, rank="Normal", start=None, end=None):
    row = {
        "club": {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"},
        "coachLabel": {"xml:lang": "en", "type": "literal", "value": name},
        "rank": {"type": "uri", "value": f"http://wikiba.se/ontology#{rank}Rank"},
    }
    if start:
        row["start"] = {"type": "literal", "value": f"{start}T00:00:00Z"}
    if end:
        row["end"] = {"type": "literal", "value": f"{end}T00:00:00Z"}
    return row


def payload(*rows):
    return {
        "head": {"vars": ["club", "coachLabel", "rank", "start", "end"]},
        "results": {"bindings": list(rows)},
    }


def test_every_current_team_has_one_distinct_qid():
    qids = load_club_qids()
    assert CURRENT_TEAMS <= set(qids)
    assert all(qid.startswith("Q") and qid[1:].isdigit() for qid in qids.values())
    assert len(set(qids.values())) == len(qids)


def test_query_lists_every_club_and_asks_for_dates_and_rank():
    query = coach_query(["Q18656", "Q9617"])
    assert "wd:Q18656 wd:Q9617" in query
    for part in ("p:P286", "pq:P580", "pq:P582", "wikibase:rank"):
        assert part in query


def test_parse_groups_statements_by_club():
    parsed = parse_coaches(
        payload(
            binding("Q18656", "Michael Carrick", "Preferred", "2026-01-13"),
            binding("Q18656", "Ralf Rangnick", "Normal", "2021-12-03", "2022-05-31"),
        )
    )
    assert parsed == {
        "Q18656": [
            {"name": "Michael Carrick", "rank": "preferred", "start": "2026-01-13", "end": None},
            {"name": "Ralf Rangnick", "rank": "normal", "start": "2021-12-03", "end": "2022-05-31"},
        ]
    }


def test_parse_skips_incomplete_bindings():
    broken = binding("Q18656", "Michael Carrick")
    del broken["coachLabel"]
    no_rank = binding("Q9617", "Mikel Arteta")
    del no_rank["rank"]
    assert parse_coaches(payload(broken, no_rank, binding("Q9616", "Xabi Alonso"))) == {
        "Q9616": [{"name": "Xabi Alonso", "rank": "normal", "start": None, "end": None}]
    }


def test_parse_skips_unlabelled_coaches():
    assert parse_coaches(payload(binding("Q9617", "Q123456"), binding("Q9616", "Xabi Alonso"))) == {
        "Q9616": [{"name": "Xabi Alonso", "rank": "normal", "start": None, "end": None}]
    }


def test_parse_rejects_a_payload_without_bindings():
    with pytest.raises(CoachFetchError):
        parse_coaches({"head": {}})


# Final review 2026-10-05: an answer with nothing usable must not overwrite good documents.
@pytest.mark.parametrize("rows", [[], [binding("Q9617", "Q123456")], None, ["not a row"]])
def test_parse_rejects_an_answer_with_no_usable_statement(rows):
    with pytest.raises(CoachFetchError):
        parse_coaches({"results": {"bindings": rows}})


def test_parse_reads_an_unknown_start_as_no_start():
    row = binding("Q18656", "Michael Carrick", "Preferred")
    row["start"] = {"type": "uri", "value": "http://www.wikidata.org/.well-known/genid/abc"}
    assert parse_coaches(payload(row))["Q18656"][0]["start"] is None


def statement(name, rank="normal", start=None, end=None):
    return {"name": name, "rank": rank, "start": start, "end": end}


def test_current_coach_ignores_ended_and_deprecated_statements():
    assert (
        current_coach(
            [
                statement("Old", start="2020-01-01", end="2022-01-01"),
                statement("Wrong", rank="deprecated", start="2026-01-01"),
                statement("Now", start="2023-01-01"),
            ]
        )["name"]
        == "Now"
    )


def test_preferred_rank_wins_over_a_later_normal_statement():
    assert (
        current_coach(
            [
                statement("Interim", start="2026-05-01"),
                statement("Chosen", rank="preferred", start="2025-01-01"),
            ]
        )["name"]
        == "Chosen"
    )


def test_latest_start_wins_and_a_missing_start_counts_as_oldest():
    assert (
        current_coach(
            [
                statement("Undated"),
                statement("Later", start="2026-06-04"),
                statement("Earlier", start="2024-07-01"),
            ]
        )["name"]
        == "Later"
    )
    assert current_coach([statement("Undated")])["name"] == "Undated"


def test_no_open_statement_means_no_current_coach():
    assert current_coach([statement("Old", start="2020-01-01", end="2022-01-01")]) is None
    assert current_coach([]) is None


def test_coach_document_follows_the_contract():
    document = coach_document(
        66,
        "Manchester United FC",
        "Q18656",
        statement("Michael Carrick", start="2026-01-13"),
        "2026",
        "2026-10-05T09:00:00+07:00",
    )
    assert document == {
        "doc_id": "coach-2026-team-66",
        "title": "Manchester United FC head coach",
        "text": (
            "Who is the head coach of Manchester United FC? Michael Carrick.\n"
            "Manchester United FC head coach (manager): Michael Carrick, since 13 January 2026.\n"
            "Source: Wikidata (Q18656), checked 2026-10-05."
        ),
        "category": "player",
        "origin": "wikidata",
        "topic": "head_coach",
        "season": "2026",
        "matchweek": None,
        "team_ids": [66],
        "date": "2026-10-05",
        "fetched_at": "2026-10-05T09:00:00+07:00",
        "url": "https://www.wikidata.org/wiki/Q18656",
    }


def test_coach_document_without_a_start_or_a_coach():
    undated = coach_document(
        57, "Arsenal FC", "Q9617", statement("Mikel Arteta"), "2026", "2026-10-05T09:00:00+07:00"
    )
    assert "Arsenal FC head coach (manager): Mikel Arteta.\n" in undated["text"]
    missing = coach_document(61, "Chelsea FC", "Q9616", None, "2026", "2026-10-05T09:00:00+07:00")
    assert (
        missing["text"]
        == "Wikidata lists no current head coach for Chelsea FC (checked 2026-10-05)."
    )


async def test_fetch_sends_the_query_with_a_user_agent():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            url=str(request.url),
            agent=request.headers["user-agent"],
            accept=request.headers["accept"],
        )
        return httpx.Response(200, json=payload(binding("Q18656", "Michael Carrick")))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await fetch_coaches(http, ["Q18656"], "0.1.0")
    assert result == {"Q18656": [statement("Michael Carrick")]}
    assert seen["url"].startswith("https://query.wikidata.org/sparql?")
    assert seen["agent"].startswith("football-assistant-course-project/0.1.0 (")
    assert seen["accept"] == "application/sparql-results+json"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"head": {}}),
    ],
)
async def test_fetch_failures_raise_one_error(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as http:
        with pytest.raises(CoachFetchError):
            await fetch_coaches(http, ["Q18656"], "0.1.0")


async def test_fetch_timeout_raises_one_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(CoachFetchError):
            await fetch_coaches(http, ["Q18656"], "0.1.0")


WIKIDATA = payload(
    binding("Q9617", "Mikel Arteta", "Preferred", "2019-12-20"),
    binding("Q9617", "Unai Emery", "Normal", "2018-05-23", "2019-11-29"),
)


def team(team_id, name):
    return {
        "id": team_id,
        "name": name,
        "coach": None,
        "squad": [{"id": team_id * 100, "name": f"{name} Player", "position": "Defender"}],
    }


def upstream(indexed, *, wikidata, teams):
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "query.wikidata.org":
            return wikidata(request) if callable(wikidata) else wikidata
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

    return handler


async def ingest(tmp_path, *, enabled=True, wikidata=None, teams=None, indexed=None):
    indexed = {} if indexed is None else indexed
    calls = []

    def wrap(request):
        calls.append(request)
        answer = wikidata if wikidata is not None else httpx.Response(200, json=WIKIDATA)
        return answer(request) if callable(answer) else answer

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'football.db'}",
        football_data_api_key="test-key",
        coach_index_enabled=enabled,
        _env_file=None,
    )
    teams = teams or [team(57, "Arsenal FC"), team(61, "Chelsea FC")]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(upstream(indexed, wikidata=wrap, teams=teams))
    )
    app = create_app(settings, http=client)
    async with app.router.lifespan_context(app):
        await app.state.service._ingest_primary(str(uuid4()))
        await app.state.service.reconcile_index()
    await client.aclose()
    return indexed, calls


async def test_ingest_indexes_one_coach_document_per_team(tmp_path):
    season = current_season()
    indexed, calls = await ingest(tmp_path)
    assert len(calls) == 1
    assert "Mikel Arteta, since 20 December 2019" in indexed[f"coach-{season}-team-57"]["text"]
    assert indexed[f"coach-{season}-team-61"]["text"].startswith(
        "Wikidata lists no current head coach for Chelsea FC"
    )


async def test_ingest_skips_teams_without_a_qid(tmp_path):
    season = current_season()
    indexed, _ = await ingest(tmp_path, teams=[team(57, "Arsenal FC"), team(9999, "Unknown FC")])
    assert f"coach-{season}-team-57" in indexed
    assert f"coach-{season}-team-9999" not in indexed


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(503), httpx.Response(200, text="<html>"), httpx.Response(200, json=payload())],
)
async def test_a_failed_fetch_keeps_the_previous_coach_documents(tmp_path, failure):
    season = current_season()
    indexed, _ = await ingest(tmp_path)
    before = dict(indexed[f"coach-{season}-team-57"])
    indexed, _ = await ingest(tmp_path, wikidata=failure, indexed=indexed)
    assert indexed[f"coach-{season}-team-57"] == before
    assert any(
        doc_id.startswith("standings-") for doc_id in indexed
    )  # the rest of the ingest still ran


async def test_the_flag_off_means_no_wikidata_call(tmp_path):
    indexed, calls = await ingest(tmp_path, enabled=False)
    assert calls == []
    assert not any(doc_id.startswith("coach-") for doc_id in indexed)


async def test_any_coach_error_leaves_the_rest_of_the_ingest_running(tmp_path, monkeypatch):
    season = current_season()

    def broken():
        raise ValueError("wikidata_clubs.json is not valid JSON")

    monkeypatch.setattr("app.service.load_club_qids", broken)
    indexed, _ = await ingest(tmp_path)
    assert f"standings-{season}" in indexed
    assert not any(doc_id.startswith("coach-") for doc_id in indexed)


# Review minors 2026-10-05: only well-formed QIDs reach SPARQL.
def test_query_keeps_only_well_formed_qids():
    query = coach_query(["Q1 } . ?x ?y ?z", "Q18656"])
    assert "?x" not in query
    assert "wd:Q18656" in query


async def test_fetch_without_a_valid_qid_makes_no_call():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(binding("Q18656", "Michael Carrick")))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await fetch_coaches(http, ["bad", ""], "0.1.0") == {}
    assert calls == []


# Final review 2026-10-05: a malformed QID keeps the previous coach documents (no "no coach" one).
async def test_ingest_skips_teams_whose_qid_is_malformed(tmp_path, monkeypatch):
    season = current_season()
    monkeypatch.setattr("app.service.load_club_qids", lambda: {57: "Q9617", 61: "not-a-qid"})
    indexed, _ = await ingest(tmp_path)
    assert f"coach-{season}-team-57" in indexed
    assert f"coach-{season}-team-61" not in indexed


async def test_ingest_with_no_valid_qid_writes_no_coach_documents(tmp_path, monkeypatch):
    monkeypatch.setattr("app.service.load_club_qids", lambda: {57: "bad", 61: ""})
    indexed, calls = await ingest(tmp_path)
    assert calls == []
    assert not any(doc_id.startswith("coach-") for doc_id in indexed)
