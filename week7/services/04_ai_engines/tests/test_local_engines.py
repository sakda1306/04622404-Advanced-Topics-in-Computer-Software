from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_local_classify_returns_expected_shape():
    r = client.post("/local/classify", json={"request_id": "c1", "text": "ปืนใหญ่ชนะกี่ลูกเมื่อคืน"})
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "local_ai"
    assert body["data"]["label"] in {
        "trivia_history",
        "match_result",
        "fixture_schedule",
        "standings_stats",
        "weekly_summary",
        "general_football",
        "prediction",
        "out_of_scope",
    }
    assert 0 <= body["data"]["score"] <= 1
    assert len(body["data"]["top_k"]) == 3
    assert body["token_usage"] == {"input": 0, "output": 0}
    assert body["model"] == "tfidf-logreg-v1"
    assert body["content"].startswith("intent: ")


def test_local_classify_high_confidence_match_result():
    r = client.post(
        "/local/classify", json={"request_id": "c2", "text": "เมื่อวานลิเวอร์พูลเจอใคร ผลเท่าไหร่"}
    )
    body = r.json()
    assert body["data"]["label"] == "match_result"


def test_local_classify_model_unavailable_returns_503():
    from app.local_classifier import ModelNotLoadedError

    with patch("app.main.classify_intent", side_effect=ModelNotLoadedError("no model file")):
        r = client.post("/local/classify", json={"request_id": "c3", "text": "test"})
    assert r.status_code == 503
    assert r.json()["code"] == "MODEL_UNAVAILABLE"


def test_local_predict_returns_501_not_implemented():
    r = client.post(
        "/local/predict",
        json={
            "request_id": "body-value-should-be-ignored",
            "home_team_id": 57,
            "away_team_id": 61,
            "season": "2026",
        },
        headers={"X-Request-ID": "p1"},
    )
    assert r.status_code == 501
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["x-request-id"] == "p1"
    body = r.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert body["request_id"] == "p1"


def _predict_body(**extra):
    body = {"request_id": "p1", "home_team_id": 57, "away_team_id": 61, "season": "2026"}
    body.update(extra)
    return body


def test_local_predict_with_strengths_returns_probabilities():
    r = client.post(
        "/local/predict",
        json=_predict_body(
            home_strength={"attack": 2.2, "defense": 0.8, "matches_used": 43},
            away_strength={"attack": 1.1, "defense": 1.6, "matches_used": 40},
            league_avg_goals=1.4,
            home_name="Arsenal",
            away_name="Chelsea",
        ),
    )
    assert r.status_code == 200
    body = r.json()
    data = body["data"]
    assert data["home_win"] + data["draw"] + data["away_win"] == pytest.approx(1.0, abs=1e-3)
    assert data["home_win"] > data["away_win"]
    assert data["method"] == "poisson-v1"
    assert data["matches_used"] == 40
    assert set(data["most_likely_score"]) == {"home", "away"}
    assert body["model"] == "poisson-v1"
    assert body["token_usage"] == {"input": 0, "output": 0}
    assert body["content"].startswith("Arsenal ชนะ ")
    assert "Chelsea ชนะ" in body["content"]
    assert "สกอร์ที่น่าจะเป็นที่สุด" in body["content"]


def test_local_predict_rejects_negative_strength():
    r = client.post(
        "/local/predict",
        json=_predict_body(
            home_strength={"attack": -1, "defense": 0.8, "matches_used": 1},
            away_strength={"attack": 1.1, "defense": 1.6, "matches_used": 1},
        ),
    )
    assert r.status_code == 422


def _sim_body(n_sims=1000, **input_overrides):
    table = [
        {"team_id": t, "name": f"T{t}", "points": 0, "goal_difference": 0, "goals_for": 0, "played": 0}
        for t in (1, 2, 3, 4)
    ]
    inputs = {
        "season": "2026",
        "as_of": "2026-09-30T22:50:00+07:00",
        "table": table,
        "remaining": [{"match_id": "a", "home_team_id": 1, "away_team_id": 2}],
        "strengths": {str(t): {"attack": 1.4, "defense": 1.3, "matches_used": 10} for t in (1, 2, 3, 4)},
        "league_avg_goals": 1.35,
        "relegation_places": 1,
    }
    inputs.update(input_overrides)
    return {"request_id": "s1", "inputs": inputs, "n_sims": n_sims, "seed": 42}


def test_local_simulate_returns_snapshot_data():
    r = client.post("/local/simulate", json=_sim_body())
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "local_ai"
    assert body["model"] == "poisson-mc-v1"
    assert body["data"]["n_sims"] == 1000
    assert body["data"]["remaining_matches"] == 1
    assert len(body["data"]["teams"]) == 4
    assert body["content"].startswith("จำลอง 1,000 ครั้ง:")


def test_local_simulate_validates_n_sims():
    assert client.post("/local/simulate", json=_sim_body(n_sims=10)).status_code == 422
    assert client.post("/local/simulate", json=_sim_body(n_sims=50000)).status_code == 422


def test_local_simulate_unknown_team_is_422_problem():
    body = _sim_body(remaining=[{"match_id": "x", "home_team_id": 1, "away_team_id": 99}])
    r = client.post("/local/simulate", json=body)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
