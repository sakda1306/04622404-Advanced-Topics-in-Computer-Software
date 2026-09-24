from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.mock_data import ALL_SCENARIOS

client = TestClient(app)

def test_get_stored_recommendation_success():
    sample = ALL_SCENARIOS["travel_normally"].model_dump(mode="json")
    with patch("app.db.get_recommendation", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = sample
        resp = client.get("/recommendation/00000000-0000-4000-8000-000000000001?region=TH")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_code"] == "TRAVEL_NORMALLY"

def test_get_stored_recommendation_not_found():
    with patch("app.db.get_recommendation", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = client.get("/recommendation/non-existent-id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "request_id not found"
