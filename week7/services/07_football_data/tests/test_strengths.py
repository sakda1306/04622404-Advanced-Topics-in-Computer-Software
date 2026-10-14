import pytest

from app.strengths import DEFAULT_GOALS, K, tally, team_strengths


def test_tally_counts_both_sides():
    result = tally([(1, 2, 3, 1), (2, 1, 0, 0)])
    assert (result[1].played, result[1].goals_for, result[1].goals_against) == (2, 3, 1)
    assert (result[2].played, result[2].goals_for, result[2].goals_against) == (2, 1, 3)


def test_blends_current_with_previous_season():
    current = tally([(1, 2, 2, 1)])
    previous = tally([(1, 2, 3, 0), (2, 1, 0, 1)])
    strengths, league_avg, prior = team_strengths(current, previous, [1, 2], relegated=[])
    # team 1 last season: 4 goals for / 0 against in 2 games → 2.0 / 0.0 per match
    assert strengths[1]["attack"] == pytest.approx((2 + K * 2.0) / (1 + K), abs=1e-4)
    assert strengths[1]["defense"] == pytest.approx((1 + K * 0.0) / (1 + K), abs=1e-4)
    assert strengths[1]["matches_used"] == 3
    assert prior == "previous_season"
    assert league_avg > 0


def test_promoted_team_uses_relegated_average():
    previous = tally([(1, "down-a", 1, 3), (1, "down-b", 1, 1)])
    strengths, _, _ = team_strengths({}, previous, [1, 5], relegated=["down-a", "down-b"])
    # down-a: 1 game, scored 3, conceded 1 · down-b: 1 game, scored 1, conceded 1
    assert strengths[5]["attack"] == pytest.approx(2.0, abs=1e-4)  # (3 + 1) / 2
    assert strengths[5]["defense"] == pytest.approx(1.0, abs=1e-4)  # (1 + 1) / 2
    assert strengths[5]["matches_used"] == 0


def test_no_previous_season_uses_league_average():
    current = tally([(1, 2, 4, 0)])
    strengths, league_avg, prior = team_strengths(current, {}, [1, 2], relegated=[])
    assert prior == "league_average"
    assert strengths[1]["attack"] == pytest.approx((4 + K * DEFAULT_GOALS) / (1 + K), abs=1e-4)
    assert league_avg == pytest.approx((4 + K * DEFAULT_GOALS) / (2 + K), abs=1e-4)


def test_no_matches_at_all_is_league_average_for_everyone():
    strengths, league_avg, _ = team_strengths({}, {}, [1, 2], relegated=[])
    assert strengths[1] == {"attack": DEFAULT_GOALS, "defense": DEFAULT_GOALS, "matches_used": 0}
    assert league_avg == DEFAULT_GOALS
