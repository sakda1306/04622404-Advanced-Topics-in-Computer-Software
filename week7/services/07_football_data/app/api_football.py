"""Map API-Football fixtures and detailed events to football-data.org match IDs."""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher

from app.football import normalize_team_name


def _similarity(left: str, right: str) -> float:
    first, second = normalize_team_name(left), normalize_team_name(right)
    return SequenceMatcher(None, first, second).ratio()


def match_api_fixture(match: dict, fixtures: list[dict]) -> dict | None:
    kickoff = datetime.fromisoformat(match["kickoff"])
    candidates = []
    for fixture in fixtures:
        fixture_time = datetime.fromisoformat(fixture["fixture"]["date"].replace("Z", "+00:00"))
        if abs(fixture_time - kickoff) > timedelta(hours=3):
            continue
        home_score = _similarity(match["home"]["name"], fixture["teams"]["home"]["name"])
        away_score = _similarity(match["away"]["name"], fixture["teams"]["away"]["name"])
        score = (home_score + away_score) / 2
        if fixture.get("goals") == {
            "home": match["score"]["home"],
            "away": match["score"]["away"],
        }:
            score += 0.1
        if score >= 0.68:
            candidates.append((score, fixture))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.08):
        return None
    return candidates[0][1]


def event_payload(raw: dict, api_fixture: dict, match: dict) -> dict | None:
    kind = (raw.get("type") or "").casefold()
    detail = (raw.get("detail") or "").casefold()
    if kind == "goal":
        if "missed" in detail:
            return None
        event_type = "own_goal" if "own" in detail else "penalty" if "penalty" in detail else "goal"
    elif kind == "card":
        event_type = (
            "red"
            if "red" in detail or "second yellow" in detail
            else "yellow"
            if "yellow" in detail
            else None
        )
    elif kind == "subst":
        event_type = "sub"
    else:
        event_type = None
    if event_type is None:
        return None
    api_team_id = (raw.get("team") or {}).get("id")
    if api_team_id == api_fixture["teams"]["home"]["id"]:
        team_id = match["home"]["team_id"]
    elif api_team_id == api_fixture["teams"]["away"]["id"]:
        team_id = match["away"]["team_id"]
    else:
        return None
    return {
        "minute": (raw.get("time") or {}).get("elapsed"),
        "type": event_type,
        "team_id": team_id,
        "player": (raw.get("player") or {}).get("name"),
        "assist": (raw.get("assist") or {}).get("name"),
    }


def enriched_match(
    match: dict,
    api_fixture: dict,
    events: list[dict],
    lineups: list[dict],
    statistics: list[dict],
    fetched_at: str,
) -> dict:
    result = dict(match)
    result["external_ids"] = dict(match["external_ids"])
    result["external_ids"]["api_football"] = api_fixture["fixture"]["id"]
    result["events"] = [
        event for raw in events if (event := event_payload(raw, api_fixture, match)) is not None
    ]
    result["lineups"] = lineups
    result["statistics"] = statistics
    result["detail_source"] = "api-football"
    result["fetched_at"] = fetched_at
    return result
