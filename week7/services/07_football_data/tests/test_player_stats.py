import httpx

from app.config import Settings
from app.football import fetch_primary, scorer_payload, squad_document
from app.service import FootballService

FETCHED_AT = "2026-09-30T10:00:00+07:00"


def standings_text(scorers: list[dict]) -> str:
    standing = {
        "matchweek": 6,
        "snapshot_type": "live",
        "rows": [
            {
                "position": 1,
                "team_id": 57,
                "name": "Arsenal FC",
                "points": 13,
                "played": 6,
                "goal_difference": 9,
            }
        ],
    }
    documents = FootballService._documents([], standing, "2026", FETCHED_AT, scorers)
    return next(d for d in documents if d["category"] == "standings")["text"]


def test_unreported_assists_stay_none():
    rows = scorer_payload(
        {"scorers": [{"player": {"name": "A"}, "team": {"id": 57}, "goals": 3, "assists": None}]}
    )
    assert rows[0]["assists"] is None


def test_standings_document_says_not_reported_instead_of_zero():
    text = standings_text(
        [
            {"player": "Erling Haaland", "team_id": 65, "goals": 5, "assists": None},
            {"player": "Bukayo Saka", "team_id": 57, "goals": 3, "assists": 2},
        ]
    )
    assert "1. Erling Haaland (65): 5 goals, assists not reported." in text
    assert "2. Bukayo Saka (Arsenal FC): 3 goals, 2 assists." in text
    assert "0 assists" not in text
    assert "None" not in text


def test_scorer_payload_keeps_id_matches_and_penalties():
    rows = scorer_payload(
        {
            "scorers": [
                {
                    "player": {"id": 38101, "name": "Erling Haaland"},
                    "team": {"id": 65},
                    "playedMatches": 5,
                    "goals": 5,
                    "assists": None,
                    "penalties": 1,
                },
                {"player": {"name": "No Id"}, "team": {"id": 57}, "goals": None},
            ]
        }
    )
    assert rows[0] == {
        "player": "Erling Haaland",
        "player_id": 38101,
        "team_id": 65,
        "played_matches": 5,
        "goals": 5,
        "assists": None,
        "penalties": 1,
    }
    assert rows[1]["player_id"] is None
    assert rows[1]["played_matches"] is None
    assert rows[1]["goals"] == 0


async def test_fetch_primary_sends_extra_params_only_when_given():
    seen = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={})

    settings = Settings(football_data_api_key="k", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        await fetch_primary(http, settings, "competitions/PL/teams", "2026", "r")
        await fetch_primary(
            http, settings, "competitions/PL/scorers", "2026", "r", params={"limit": 100}
        )
    assert seen == [{"season": "2026"}, {"season": "2026", "limit": "100"}]


def test_standings_document_shows_only_the_top_ten():
    scorers = [
        {"player": f"Player {n}", "team_id": 57, "goals": 20 - n, "assists": None}
        for n in range(1, 13)
    ]
    text = standings_text(scorers)
    assert "10. Player 10 " in text
    assert "Player 11" not in text


SQUAD = {
    "team_id": 57,
    "team_name": "Arsenal FC",
    "coach": None,
    "fetched_at": FETCHED_AT,
    "players": [
        {
            "id": 7,
            "name": "Bukayo Saka",
            "position": "Winger",
            "date_of_birth": "2001-09-05",
            "nationality": "England",
        },
        {
            "id": 8,
            "name": "Martin Ødegaard",
            "position": "Midfielder",
            "date_of_birth": "1998-12-17",
            "nationality": "Norway",
        },
    ],
}


def section(text: str, name: str) -> str:
    return text.split(f"## {name}\n", 1)[1].split("\n\n## ", 1)[0]


def test_player_with_stats_gets_a_season_line_under_their_own_heading():
    stats = {7: {"player_id": 7, "played_matches": 6, "goals": 3, "assists": 2, "penalties": None}}
    text = squad_document(SQUAD, "2026", stats)["text"]
    assert section(text, "Bukayo Saka").endswith(
        "Premier League 2026 season so far (as of 2026-09-30): 3 goals in 6 matches. "
        "Assists: 2. Penalty goals: not reported."
    )
    assert "season so far" not in section(text, "Martin Ødegaard")


def test_missing_played_matches_drops_the_match_count():
    stats = {
        8: {"player_id": 8, "played_matches": None, "goals": 1, "assists": None, "penalties": 0}
    }
    line = section(squad_document(SQUAD, "2026", stats)["text"], "Martin Ødegaard")
    assert "(as of 2026-09-30): 1 goals. Assists: not reported. Penalty goals: 0." in line
    assert "None" not in line


def test_no_stats_keeps_the_layer_one_document_unchanged():
    assert squad_document(SQUAD, "2026") == squad_document(SQUAD, "2026", {})
    assert "season so far" not in squad_document(SQUAD, "2026")["text"]
