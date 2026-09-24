"""Shared fixtures of the end-to-end tests."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import httpx
import pytest

MOCK_URL = os.environ.get("E2E_MOCK_AGENT_URL", "http://localhost:8010")


@pytest.fixture
def scenario() -> Iterator[Callable[[str], None]]:
    """Switch the mock Agent's scenario; the default comes back after the test."""
    with httpx.Client(base_url=MOCK_URL, timeout=5) as mock:

        def choose(name: str) -> None:
            mock.put("/_mock/scenario", json={"name": name}).raise_for_status()

        yield choose
        choose("low_risk")
