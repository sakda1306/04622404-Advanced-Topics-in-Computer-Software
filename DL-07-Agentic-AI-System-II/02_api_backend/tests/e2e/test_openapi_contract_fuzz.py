"""Live schema fuzz (docs/04_project_structure.md section 8, row "Contract": "fuzz schema").

schemathesis generates inputs from the live openapi.json and calls every GET operation
against the real compose stack; the only requirement is no 5xx. Restricted to GET so a
fuzz run cannot corrupt state other e2e tests in this session depend on (an account
deletion, the safety review queue, ...) — write operations are already covered by the
API-level tests and the other e2e flows.

The schema is fetched from the live server at import time, so this only defines its test
when a stack is actually up; without one there is nothing meaningful to fetch.

    docker compose up -d --build --wait
    E2E_BASE_URL=http://localhost:8000 uv run pytest -m e2e tests/e2e/test_openapi_contract_fuzz.py
"""

from __future__ import annotations

from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error

from tests.e2e.test_data_protection import compose, needs_docker
from tests.e2e.test_recommendation_flow import BASE_URL, token

SCOPES = "travel:read travel:write profile:read profile:write admin:read admin:write safety:review"

if BASE_URL:
    schema = (
        schemathesis.openapi.from_url(f"{BASE_URL}/openapi.json")
        .include(method="GET")
        .exclude(path_regex=r"/events$")  # SSE stream, not a fuzz target
    )

    @pytest.mark.e2e
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @schemathesis.pytest.parametrize(api=schema)
    def test_get_endpoints_never_5xx(case: schemathesis.Case[Any]) -> None:
        case.call_and_validate(
            headers={"Authorization": f"Bearer {token(SCOPES)}"},
            checks=[not_a_server_error],  # type: ignore[list-item]  # schemathesis stub overload
            timeout=10,
        )

    @pytest.mark.e2e
    @needs_docker
    def test_reset_ip_rate_limit_after_the_fuzz_run() -> None:
        # The run above can call one IP-shared bucket (P-31) close to a hundred times;
        # clear it so later e2e tests sharing this runner's IP are not falsely rate limited.
        compose(
            "exec",
            "-T",
            "redis-core",
            "redis-cli",
            "EVAL",
            "for _,k in ipairs(redis.call('keys', ARGV[1])) do redis.call('del', k) end",
            "0",
            "tsa:*:rl:ip:*",
        )
