from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from decision_engine.api import create_app
from decision_engine.config import Settings
from decision_engine.sample_data import scenarios

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def samples():
    return scenarios(NOW)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, audit_log_path=tmp_path / "audit.jsonl")


@pytest.fixture
def client(settings):
    app = create_app(settings)
    app.state.clock = lambda: NOW
    with TestClient(app) as client:
        yield client
