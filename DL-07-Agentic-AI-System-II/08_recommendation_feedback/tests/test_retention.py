from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_feedback_cleanup_endpoint():
    with patch("app.db.purge_expired_feedback", new_callable=AsyncMock) as mock_purge:
        mock_purge.return_value = 5
        resp = client.post("/feedback/cleanup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["purged_count"] == 5
        assert data["retention_days"] == 180
        mock_purge.assert_called_once_with(180)
