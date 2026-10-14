import time

import pytest

from app.simulate import SimulationInputError, simulate_season


def league(n_teams=20, strong_id=1, played=True):
    ids = list(range(1, n_teams + 1))
    table = [
        {"team_id": t, "name": f"Team {t}", "points": 0, "goal_difference": 0, "goals_for": 0, "played": 0}
        for t in ids
    ]
    remaining = [
        {"match_id": f"{h}-{a}", "home_team_id": h, "away_team_id": a}
        for h in ids
        for a in ids
        if h != a
    ] if played else []
    strengths = {
        str(t): {"attack": 2.6 if t == strong_id else 1.3, "defense": 0.6 if t == strong_id else 1.3,
                 "matches_used": 20}
        for t in ids
    }
    return {"season": "2026", "as_of": "2026-09-30T22:50:00+07:00", "table": table,
            "remaining": remaining, "strengths": strengths, "league_avg_goals": 1.35,
            "relegation_places": 3}


def test_same_seed_same_result():
    a, _ = simulate_season(league(8), 2000, 7)
    b, _ = simulate_season(league(8), 2000, 7)
    assert a == b


def test_probabilities_are_distributions():
    data, _ = simulate_season(league(8), 3000, 1)
    n = len(data["teams"])
    for team in data["teams"]:
        assert len(team["position_probs"]) == n
        assert sum(team["position_probs"]) == pytest.approx(1.0, abs=1e-3)
    for position in range(n):
        assert sum(t["position_probs"][position] for t in data["teams"]) == pytest.approx(1.0, abs=1e-3)


def test_stronger_team_is_favourite_and_first():
    data, content = simulate_season(league(8), 3000, 3)
    assert data["teams"][0]["team_id"] == 1
    assert data["teams"][0]["p_title"] == max(t["p_title"] for t in data["teams"])
    assert content.startswith("จำลอง 3,000 ครั้ง:")
    assert "Team 1 แชมป์" in content


def test_top4_and_relegation_use_places():
    data, _ = simulate_season(league(8), 2000, 5)
    assert sum(t["p_top4"] for t in data["teams"]) == pytest.approx(4.0, abs=1e-2)
    assert sum(t["p_relegation"] for t in data["teams"]) == pytest.approx(3.0, abs=1e-2)


def test_no_remaining_matches_uses_current_table():
    inputs = league(4, played=False)
    for points, row in zip([9, 6, 3, 0], inputs["table"]):
        row["points"] = points
    data, _ = simulate_season(inputs, 1000, 1)
    leader = next(t for t in data["teams"] if t["team_id"] == 1)
    assert leader["p_title"] == 1.0
    assert data["remaining_matches"] == 0


def test_missing_strength_is_an_input_error():
    inputs = league(4)
    del inputs["strengths"]["2"]
    with pytest.raises(SimulationInputError):
        simulate_season(inputs, 1000, 1)


def test_team_outside_table_is_an_input_error():
    inputs = league(4)
    inputs["remaining"].append({"match_id": "x", "home_team_id": 1, "away_team_id": 99})
    with pytest.raises(SimulationInputError):
        simulate_season(inputs, 1000, 1)


def test_empty_table_is_an_input_error():
    inputs = league(4)
    inputs["table"] = []
    with pytest.raises(SimulationInputError):
        simulate_season(inputs, 1000, 1)


def test_full_season_is_fast_enough():
    started = time.monotonic()
    simulate_season(league(20), 10000, 42)
    assert time.monotonic() - started < 2.0
