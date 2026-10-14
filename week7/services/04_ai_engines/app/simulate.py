"""
จำลองฤดูกาลที่เหลือแบบ Monte Carlo ด้วย Poisson model (CONTRACT v1.7 §3 /local/simulate)

pure function ไม่มี state · 07 เตรียม inputs (ตาราง, นัดที่เหลือ, ความแข็งทีม) มาให้ทั้งหมด
"""
import numpy as np

from .poisson import TeamStrength, expected_goals, format_percent


class SimulationInputError(ValueError):
    """inputs ไม่ครบหรือขัดกันเอง → endpoint ตอบ 422"""


def _strengths(inputs: dict, team_ids: list[int]) -> dict[int, TeamStrength]:
    result = {}
    for team_id in team_ids:
        raw = inputs["strengths"].get(str(team_id))
        if raw is None:
            raise SimulationInputError(f"missing strength for team {team_id}")
        result[team_id] = TeamStrength(
            attack_goals_per_match=float(raw["attack"]),
            defense_goals_conceded_per_match=float(raw["defense"]),
            matches_used=int(raw.get("matches_used", 0)),
        )
    return result


def simulate_season(inputs: dict, n_sims: int, seed: int | None) -> tuple[dict, str]:
    table = inputs["table"]
    if not table:
        raise SimulationInputError("table is empty")
    team_ids = [int(row["team_id"]) for row in table]
    index = {team_id: i for i, team_id in enumerate(team_ids)}
    strengths = _strengths(inputs, team_ids)
    league_avg = float(inputs["league_avg_goals"])
    remaining = inputs["remaining"]
    n_teams, n_matches = len(team_ids), len(remaining)

    home_onehot = np.zeros((n_matches, n_teams), dtype=np.int64)
    away_onehot = np.zeros((n_matches, n_teams), dtype=np.int64)
    home_xg = np.empty(n_matches)
    away_xg = np.empty(n_matches)
    for m, match in enumerate(remaining):
        home, away = int(match["home_team_id"]), int(match["away_team_id"])
        if home not in index or away not in index:
            raise SimulationInputError(f"match {match.get('match_id')} has a team outside the table")
        home_onehot[m, index[home]] = 1
        away_onehot[m, index[away]] = 1
        home_xg[m] = expected_goals(strengths[home], strengths[away], True, league_avg)
        away_xg[m] = expected_goals(strengths[away], strengths[home], False, league_avg)

    rng = np.random.default_rng(seed)
    points = np.tile(np.array([row["points"] for row in table], dtype=np.int64), (n_sims, 1))
    goal_diff = np.tile(np.array([row["goal_difference"] for row in table], dtype=np.int64), (n_sims, 1))
    goals_for = np.tile(np.array([row["goals_for"] for row in table], dtype=np.int64), (n_sims, 1))
    if n_matches:
        home_goals = rng.poisson(home_xg, size=(n_sims, n_matches))
        away_goals = rng.poisson(away_xg, size=(n_sims, n_matches))
        home_points = np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
        away_points = np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))
        points += home_points @ home_onehot + away_points @ away_onehot
        goals_for += home_goals @ home_onehot + away_goals @ away_onehot
        margin = home_goals - away_goals
        goal_diff += margin @ home_onehot - margin @ away_onehot

    # จัดอันดับ: แต้ม → ผลต่างประตู → ประตูได้ → สุ่ม (np.lexsort ใช้ key ตัวสุดท้ายเป็นหลัก)
    tiebreak = rng.random((n_sims, n_teams))
    order = np.lexsort((tiebreak, -goals_for, -goal_diff, -points), axis=-1)
    positions = np.empty_like(order)
    positions[np.arange(n_sims)[:, None], order] = np.arange(n_teams)
    position_probs = np.stack([(positions == p).mean(axis=0) for p in range(n_teams)], axis=1)
    expected_points = points.mean(axis=0)

    relegation = int(inputs.get("relegation_places", 3))
    teams = []
    for i, row in enumerate(table):
        probs = [round(float(p), 4) for p in position_probs[i]]
        teams.append({
            "team_id": team_ids[i],
            "points": int(row["points"]),
            "expected_points": round(float(expected_points[i]), 1),
            "p_title": probs[0],
            "p_top4": round(float(position_probs[i, : min(4, n_teams)].sum()), 4),
            "p_relegation": round(float(position_probs[i, n_teams - relegation:].sum()), 4) if relegation else 0.0,
            "position_probs": probs,
        })
    teams.sort(key=lambda t: (-t["expected_points"], -t["points"]))

    names = {int(row["team_id"]): row.get("name") or str(row["team_id"]) for row in table}
    top = sorted(teams, key=lambda t: -t["p_title"])[:3]
    content = f"จำลอง {n_sims:,} ครั้ง: " + " · ".join(
        f"{names[t['team_id']]} แชมป์ {format_percent(t['p_title'])}" for t in top
    )
    data = {
        "season": inputs.get("season"),
        "as_of": inputs.get("as_of"),
        "n_sims": n_sims,
        "remaining_matches": n_matches,
        "teams": teams,
    }
    return data, content
