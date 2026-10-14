import pytest

from app.poisson import TeamStrength, match_outcome_probabilities


def test_probabilities_sum_to_one():
    home = TeamStrength(attack_goals_per_match=2.1, defense_goals_conceded_per_match=0.9, matches_used=10)
    away = TeamStrength(attack_goals_per_match=1.3, defense_goals_conceded_per_match=1.4, matches_used=10)
    result = match_outcome_probabilities(home, away)
    total = result["home_win"] + result["draw"] + result["away_win"]
    assert total == pytest.approx(1.0, abs=1e-3)


def test_stronger_home_team_favored():
    strong = TeamStrength(attack_goals_per_match=2.5, defense_goals_conceded_per_match=0.7, matches_used=10)
    weak = TeamStrength(attack_goals_per_match=0.8, defense_goals_conceded_per_match=2.0, matches_used=10)
    result = match_outcome_probabilities(strong, weak)
    assert result["home_win"] > result["away_win"]
    assert result["home_win"] > result["draw"]


def test_evenly_matched_teams_have_similar_outcome_split():
    a = TeamStrength(attack_goals_per_match=1.4, defense_goals_conceded_per_match=1.2, matches_used=10)
    b = TeamStrength(attack_goals_per_match=1.4, defense_goals_conceded_per_match=1.2, matches_used=10)
    result = match_outcome_probabilities(a, b)
    # เจ้าบ้านยังได้เปรียบจาก home advantage แต่ไม่ควรต่างกันสุดโต่ง
    assert result["home_win"] > result["away_win"]
    assert result["away_win"] > 0.15


def test_expected_goals_never_zero_or_negative():
    from app.poisson import expected_goals

    tiny = TeamStrength(attack_goals_per_match=0.0, defense_goals_conceded_per_match=0.0, matches_used=1)
    xg = expected_goals(tiny, tiny, is_home=True)
    assert xg > 0


from app.poisson import expected_goals, format_percent


def test_league_average_is_a_parameter():
    team = TeamStrength(attack_goals_per_match=2.0, defense_goals_conceded_per_match=2.0, matches_used=10)
    assert expected_goals(team, team, is_home=False, league_avg=2.0) == pytest.approx(2.0)
    assert expected_goals(team, team, is_home=False) == pytest.approx(2.0 * 2.0 / 1.35, rel=1e-6)


def test_most_likely_score_is_reported():
    strong = TeamStrength(attack_goals_per_match=2.5, defense_goals_conceded_per_match=0.7, matches_used=10)
    weak = TeamStrength(attack_goals_per_match=0.8, defense_goals_conceded_per_match=2.0, matches_used=10)
    score = match_outcome_probabilities(strong, weak)["most_likely_score"]
    assert score["home"] > score["away"]
    assert set(score) == {"home", "away"}


def test_format_percent():
    assert format_percent(0.4849) == "48%"
    assert format_percent(0.004) == "<1%"
    assert format_percent(0.0) == "0%"
    assert format_percent(1.0) == "100%"
