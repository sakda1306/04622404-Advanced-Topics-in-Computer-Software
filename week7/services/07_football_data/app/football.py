"""football-data.org adapter and contract-shaped payloads."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings

BANGKOK = ZoneInfo("Asia/Bangkok")
BASE = "https://football-assistant.local/match/"
STATUS = {
    "TIMED": "SCHEDULED",
    "SCHEDULED": "SCHEDULED",
    "IN_PLAY": "LIVE",
    "PAUSED": "LIVE",
    "LIVE": "LIVE",
    "FINISHED": "FINISHED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED",
    "SUSPENDED": "POSTPONED",
}
ALIASES = json.loads((Path(__file__).parent / "team_aliases.json").read_text(encoding="utf-8"))


def normalize_team_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).casefold()
    name = re.sub(r"\b(fc|afc|football club)\b", "", name)
    return re.sub(r"[^a-z0-9]+", "", name)


NORMALIZED_ALIASES = {normalize_team_name(name): aliases for name, aliases in ALIASES.items()}


def now_iso() -> str:
    return datetime.now(BANGKOK).isoformat(timespec="seconds")


def bangkok_iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(BANGKOK).isoformat(timespec="seconds")


def current_season() -> str:
    now = datetime.now(BANGKOK)
    return str(now.year if now.month >= 7 else now.year - 1)


def team_payload(raw: dict) -> dict:
    name = raw["name"]
    local_aliases = NORMALIZED_ALIASES.get(normalize_team_name(name), [])
    aliases = list(dict.fromkeys([raw.get("shortName") or name, name, *local_aliases]))
    return {
        "team_id": raw["id"],
        "name": name,
        "short_name": raw.get("shortName") or name,
        "tla": raw.get("tla") or "",
        "aliases": aliases,
        "crest_url": raw.get("crest"),
    }


def squad_payload(raw_team: dict, fetched_at: str) -> dict | None:
    squad = raw_team.get("squad")
    players = [
        {
            "id": item.get("id"),
            "name": item["name"],
            "position": item.get("position"),
            "date_of_birth": item.get("dateOfBirth"),
            "nationality": item.get("nationality"),
        }
        for item in (squad if isinstance(squad, list) else [])
        if isinstance(item, dict) and item.get("name")
    ]
    if not players:
        return None
    coach = raw_team.get("coach")
    coach = coach if isinstance(coach, dict) else {}
    return {
        "team_id": raw_team["id"],
        "team_name": raw_team["name"],
        "coach": (
            {"id": coach.get("id"), "name": coach["name"], "nationality": coach.get("nationality")}
            if coach.get("name")
            else None
        ),
        "players": players,
        "fetched_at": fetched_at,
    }


def season_stats_line(stat: dict, season: str, as_of: str) -> str:
    def reported(value) -> str:
        return "not reported" if value is None else str(value)

    games = (
        f" in {stat['played_matches']} matches" if stat.get("played_matches") is not None else ""
    )
    return (
        f"Premier League {season} season so far (as of {as_of}): "
        f"{stat['goals']} goals{games}. Assists: {reported(stat.get('assists'))}. "
        f"Penalty goals: {reported(stat.get('penalties'))}."
    )


# The provider says "Offence"/"Defence"; fans ask for forwards and defenders.
POSITION_GROUPS = {
    "Goalkeeper": "Goalkeepers",
    "Defence": "Defenders",
    "Defender": "Defenders",
    "Midfield": "Midfielders",
    "Midfielder": "Midfielders",
    "Offence": "Forwards",
    "Forward": "Forwards",
}
POSITION_ORDER = ("Goalkeepers", "Defenders", "Midfielders", "Forwards")


NOT_LISTED = "Position not listed"


def squad_groups(players: list[dict]) -> list[tuple[str, list[str]]]:
    """Player names by position group, in the usual order; unknown labels keep their name."""
    groups: dict[str, list[str]] = {}
    for player in players:
        label = POSITION_GROUPS.get(player["position"], player["position"] or NOT_LISTED)
        groups.setdefault(label, []).append(player["name"])
    order = [g for g in POSITION_ORDER if g in groups]
    order += [g for g in groups if g not in POSITION_ORDER and g != NOT_LISTED]
    order += [NOT_LISTED] if NOT_LISTED in groups else []
    return [(g, groups[g]) for g in order]


def squad_list(team: str, players: list[dict]) -> str:
    """The whole squad by position, so one chunk answers "who is in the squad"."""
    lines = [f"{team} squad list ({len(players)} players):"]
    lines += [f"{g} ({len(names)}): {', '.join(names)}." for g, names in squad_groups(players)]
    return "\n".join(lines)


def position_sections(team: str, players: list[dict]) -> list[str]:
    """One short chunk per position: the long squad list lost to one-player chunks."""
    return [
        f"## {team} {g.lower()}\n{team} {g.lower()} ({len(names)}): {', '.join(names)}."
        for g, names in squad_groups(players)
        if g != NOT_LISTED
    ]


def squad_document(squad: dict, season: str, stats: dict[int, dict] | None = None) -> dict:
    team = squad["team_name"]
    as_of = squad["fetched_at"][:10]
    stats = stats or {}
    intro = f"Premier League {season} squad: {team}."
    if squad["coach"]:
        intro += f" Coach: {squad['coach']['name']}."
    # Each player below is a chunk of its own; only five chunks reach generation.
    intro += "\n" + squad_list(team, squad["players"])
    sections = position_sections(team, squad["players"])
    for player in squad["players"]:
        section = (
            f"## {player['name']}\n"
            f"Team: {team}. Position: {player['position'] or 'unknown'}. "
            f"Date of birth: {player['date_of_birth'] or 'unknown'}. "
            f"Nationality: {player['nationality'] or 'unknown'}."
        )
        stat = stats.get(player["id"]) if player["id"] is not None else None
        if stat:
            section += "\n" + season_stats_line(stat, season, as_of)
        sections.append(section)
    return {
        "doc_id": f"players-{season}-team-{squad['team_id']}",
        "title": f"{team} squad {season}",
        "text": intro + "\n\n" + "\n\n".join(sections),
        "category": "player",
        "origin": "football-data.org",
        "season": season,
        "matchweek": None,
        "team_ids": [squad["team_id"]],
        "date": as_of,
        "fetched_at": squad["fetched_at"],
        "url": None,
    }


def match_payload(raw: dict, fetched_at: str) -> dict:
    home, away = raw["homeTeam"], raw["awayTeam"]
    score = raw.get("score") or {}
    full = score.get("fullTime") or {}
    half = score.get("halfTime") or {}
    season = str(raw["season"]["startDate"][:4])
    external_id = raw["id"]
    return {
        "match_id": str(uuid5(NAMESPACE_URL, BASE + str(external_id))),
        "external_ids": {"football_data": external_id, "api_football": None},
        "season": season,
        "matchweek": raw.get("matchday"),
        "kickoff": bangkok_iso(raw["utcDate"]),
        "status": STATUS.get(raw["status"], "SCHEDULED"),
        "home": {"team_id": home["id"], "name": home["name"]},
        "away": {"team_id": away["id"], "name": away["name"]},
        "score": {
            "home": full.get("home"),
            "away": full.get("away"),
            "half_time": {"home": half.get("home"), "away": half.get("away")},
        },
        "events": [],
        "lineups": None,
        "statistics": None,
        "fetched_at": fetched_at,
        "detail_source": "none",
    }


def standing_payload(raw: dict, season: str, fetched_at: str) -> dict:
    standings = raw.get("standings") or []
    total = next((part for part in standings if part.get("type") == "TOTAL"), {})
    rows = [
        {
            "position": row["position"],
            "team_id": row["team"]["id"],
            "name": row["team"]["name"],
            "played": row["playedGames"],
            "won": row["won"],
            "draw": row["draw"],
            "lost": row["lost"],
            "goals_for": row["goalsFor"],
            "goals_against": row["goalsAgainst"],
            "goal_difference": row["goalDifference"],
            "points": row["points"],
            "form": row.get("form") or "",
        }
        for row in total.get("table", [])
    ]
    return {
        "season": season,
        "matchweek": raw.get("season", {}).get("currentMatchday"),
        "fetched_at": fetched_at,
        "rows": rows,
    }


def scorer_payload(raw: dict) -> list[dict]:
    return [
        {
            "player": row["player"]["name"],
            "player_id": row["player"].get("id"),
            "team_id": row["team"]["id"],
            "played_matches": row.get("playedMatches"),
            "goals": row.get("goals") or 0,
            "assists": row.get("assists"),
            "penalties": row.get("penalties"),
        }
        for row in raw.get("scorers", [])
    ]


def completed_matchweeks(matches: list[dict]) -> list[int]:
    weeks = sorted({m["matchweek"] for m in matches if m["matchweek"] is not None})
    return [
        week
        for week in weeks
        if all(
            m["status"] in ("FINISHED", "POSTPONED", "CANCELLED")
            for m in matches
            if m["matchweek"] == week
        )
    ]


def derive_standings(
    matches: list[dict],
    teams: list[dict],
    season: str,
    matchweek: int,
    fetched_at: str,
    reference_rows: list[dict] | None = None,
) -> dict:
    """Build a provisional snapshot, retaining known official point adjustments."""
    adjustments = {
        row["team_id"]: row["points"] - 3 * row["won"] - row["draw"]
        for row in reference_rows or []
        if all(key in row for key in ("team_id", "points", "won", "draw"))
    }
    rank_hints = {
        row["team_id"]: row["position"]
        for row in reference_rows or []
        if "team_id" in row and "position" in row
    }
    rows = {
        team["team_id"]: {
            "position": 0,
            "team_id": team["team_id"],
            "name": team["name"],
            "played": 0,
            "won": 0,
            "draw": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
            "form": "",
        }
        for team in teams
    }
    ordered = sorted(
        (m for m in matches if m["matchweek"] is not None and m["matchweek"] <= matchweek),
        key=lambda m: m["kickoff"],
    )
    for match in ordered:
        if match["status"] != "FINISHED":
            continue
        home_id, away_id = match["home"]["team_id"], match["away"]["team_id"]
        home_score, away_score = match["score"]["home"], match["score"]["away"]
        if home_score is None or away_score is None:
            raise ValueError("finished match has no score")
        for team_id, goals_for, goals_against in (
            (home_id, home_score, away_score),
            (away_id, away_score, home_score),
        ):
            row = rows[team_id]
            row["played"] += 1
            row["goals_for"] += goals_for
            row["goals_against"] += goals_against
            row["goal_difference"] += goals_for - goals_against
            result = (
                "W" if goals_for > goals_against else "D" if goals_for == goals_against else "L"
            )
            row[{"W": "won", "D": "draw", "L": "lost"}[result]] += 1
            row["points"] += {"W": 3, "D": 1, "L": 0}[result]
            row["form"] = (row["form"] + result)[-5:]
    for team_id, row in rows.items():
        row["point_adjustment"] = adjustments.get(team_id, 0)
        row["points"] += row["point_adjustment"]
    ranked = sorted(
        rows.values(),
        key=lambda row: (
            -row["points"],
            -row["goal_difference"],
            -row["goals_for"],
            rank_hints.get(row["team_id"], len(rows) + 1),
            row["name"],
        ),
    )
    for position, row in enumerate(ranked, start=1):
        row["position"] = position
    return {
        "season": season,
        "matchweek": matchweek,
        "fetched_at": fetched_at,
        "rows": ranked,
        "provisional": True,
    }


class UpstreamError(Exception):
    pass


class PrimaryThrottle:
    """Pause before the next call once football-data.org reports the minute quota spent."""

    WINDOW_SECONDS = 60

    def __init__(self, sleep=asyncio.sleep):
        self._sleep = sleep
        self._remaining: int | None = None
        self._reset = self.WINDOW_SECONDS

    @staticmethod
    def _header_int(headers: httpx.Headers, name: str) -> int | None:
        try:
            value = int(headers.get(name, ""))
        except ValueError:
            return None
        return value if value >= 0 else None

    def observe(self, headers: httpx.Headers) -> None:
        remaining = self._header_int(headers, "x-requests-available-minute")
        if remaining is None:
            return
        self._remaining = remaining
        reset = self._header_int(headers, "X-RequestCounter-Reset")
        self._reset = reset if reset is not None else self.WINDOW_SECONDS

    def block(self, headers: httpx.Headers) -> None:
        """Treat a 429 as an exhausted minute even when it carries no counters."""
        self.observe(headers)
        self._remaining = 0

    async def wait(self) -> None:
        if self._remaining == 0:
            self._remaining = None
            await self._sleep(self._reset)


async def fetch_primary(
    http: httpx.AsyncClient,
    settings: Settings,
    path: str,
    season: str,
    request_id: str,
    throttle: PrimaryThrottle | None = None,
    params: dict | None = None,
) -> dict:
    if not settings.football_data_api_key:
        raise UpstreamError("FOOTBALL_DATA_API_KEY is not configured")
    url = f"{settings.football_data_base_url.rstrip('/')}/{path.lstrip('/')}"
    for attempt in range(3):
        if throttle:
            await throttle.wait()
        try:
            response = await http.get(
                url,
                params={"season": season, **(params or {})},
                headers={
                    "X-Auth-Token": settings.football_data_api_key,
                    "X-Request-ID": request_id,
                },
                timeout=10,
            )
            if throttle:
                throttle.observe(response.headers)
            if response.status_code == 429 and throttle and attempt < 2:
                throttle.block(response.headers)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep((1, 3)[attempt])
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == 2:
                raise UpstreamError(str(exc)) from exc
            await asyncio.sleep((1, 3)[attempt])
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise UpstreamError(str(exc)) from exc
    raise UpstreamError("football-data.org unavailable")
