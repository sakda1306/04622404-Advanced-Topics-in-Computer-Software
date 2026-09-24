"""Pytest fixtures for live Docker Compose end-to-end integration tests."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest

KEYCLOAK_URL = os.environ.get("INTEGRATION_KEYCLOAK_URL", "http://127.0.0.1:8180")
API_URL = os.environ.get("INTEGRATION_API_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def keycloak_url() -> str:
    return KEYCLOAK_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def dev_token(keycloak_url: str) -> str:
    """Fetch an access token from Keycloak using password grant on dev-cli."""
    token_url = f"{keycloak_url}/realms/travel-safety/protocol/openid-connect/token"
    last_error = None
    for _ in range(12):
        try:
            res = httpx.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": "dev-cli",
                    "username": "dev-user",
                    "password": "dev-password-change-me",
                },
                timeout=10.0,
            )
            if res.status_code == 200:
                return res.json()["access_token"]
            last_error = f"HTTP {res.status_code}: {res.text}"
        except Exception as error:
            last_error = str(error)
        time.sleep(2.0)
    raise RuntimeError(f"Could not obtain Keycloak token from {token_url}: {last_error}")
