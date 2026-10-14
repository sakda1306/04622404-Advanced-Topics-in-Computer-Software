"""Team attack / defence strengths for the prediction model (CONTRACT v1.7 §7).

Pure functions: this season's results are blended with last season's per-match rates,
weighted as if last season were K extra matches.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass

K = 10
DEFAULT_GOALS = 1.35  # league goals per team per match when no history exists


@dataclass
class Tally:
    played: int = 0
    goals_for: int = 0
    goals_against: int = 0


def tally(results: Iterable[tuple[Hashable, Hashable, int, int]]) -> dict[Hashable, Tally]:
    """results = (home, away, home_goals, away_goals)."""
    rows: dict[Hashable, Tally] = {}
    for home, away, home_goals, away_goals in results:
        for team, scored, conceded in (
            (home, home_goals, away_goals),
            (away, away_goals, home_goals),
        ):
            row = rows.setdefault(team, Tally())
            row.played += 1
            row.goals_for += scored
            row.goals_against += conceded
    return rows


def _rate(rows: Iterable[Tally]) -> tuple[float, float] | None:
    rows = [r for r in rows if r.played]
    played = sum(r.played for r in rows)
    if not played:
        return None
    return sum(r.goals_for for r in rows) / played, sum(r.goals_against for r in rows) / played


def team_strengths(
    current: dict[Hashable, Tally],
    previous: dict[Hashable, Tally],
    team_ids: list[int],
    relegated: list[Hashable],
    k: int = K,
) -> tuple[dict[int, dict], float, str]:
    promoted_prior = _rate(previous[key] for key in relegated if key in previous)
    previous_league = _rate(previous.values())
    prior_kind = "previous_season" if previous_league else "league_average"
    default = (DEFAULT_GOALS, DEFAULT_GOALS)

    strengths: dict[int, dict] = {}
    for team_id in team_ids:
        now = current.get(team_id, Tally())
        before = previous.get(team_id)
        if before and before.played:
            prior = (before.goals_for / before.played, before.goals_against / before.played)
            previous_played = before.played
        else:
            prior = promoted_prior or default
            previous_played = 0
        strengths[team_id] = {
            "attack": round((now.goals_for + k * prior[0]) / (now.played + k), 4),
            "defense": round((now.goals_against + k * prior[1]) / (now.played + k), 4),
            "matches_used": now.played + previous_played,
        }

    league_prior = previous_league[0] if previous_league else DEFAULT_GOALS
    current_played = sum(r.played for r in current.values())
    current_goals = sum(r.goals_for for r in current.values())
    league_avg = round((current_goals + k * league_prior) / (current_played + k), 4)
    return strengths, league_avg, prior_kind
