"""OpenAPI schema contract (docs/04_project_structure.md section 8, row "Contract").

The schema is exported for the Web App team with `make openapi` (scripts/export_openapi.py)
and checked in as openapi.json. These tests keep it honest: it must not drift from the
running app without a deliberate re-export, and it must stay a valid OpenAPI document.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import schemathesis

from app.main import create_app

SNAPSHOT = Path(__file__).resolve().parents[2] / "openapi.json"


@pytest.fixture
def schema() -> dict[str, Any]:
    return create_app().openapi()


def test_openapi_snapshot_matches_the_running_app(schema: dict[str, Any]) -> None:
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert schema == committed, "openapi.json is stale — run `make openapi` and commit it"


def test_openapi_schema_is_structurally_valid(schema: dict[str, Any]) -> None:
    schemathesis.openapi.from_dict(schema).validate()


def test_every_ref_resolves_to_a_component(schema: dict[str, Any]) -> None:
    # validate() above checks the meta-schema only; it does not resolve $refs, and a
    # dangling one breaks client generators and oasdiff.
    components = schema["components"]["schemas"]
    refs = set(re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(schema)))

    assert refs - components.keys() == set()
    assert [name for name, body in components.items() if "$defs" in body] == []


def test_422_responses_use_problem_details_not_the_fastapi_default(
    schema: dict[str, Any],
) -> None:
    # FastAPI documents its own HTTPValidationError for every 422 it infers; the app
    # never sends that body (app/api/error_handlers.py), so nothing should reference it.
    schemas = schema["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas

    validated_operations = [
        operation
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "422" in operation.get("responses", {})
    ]
    assert validated_operations, "expected at least one operation with a 422 response"
    for operation in validated_operations:
        content = operation["responses"]["422"]["content"]
        assert set(content) == {"application/problem+json"}
        assert content["application/problem+json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemResponse"
        }
