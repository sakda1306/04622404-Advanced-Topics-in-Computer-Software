"""Make the exported OpenAPI schema match the errors the API actually sends.

FastAPI documents its own `HTTPValidationError` for every 422 response it infers
automatically; this app never sends that body (app/api/error_handlers.py always answers
with RFC 9457 Problem Details, app/api/problem.py), so the schema the Web App team reads
from `openapi.json` (`make openapi`, docs/04_project_structure.md section 9) would
mislead them without this fix.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.api.problem import PROBLEM_MEDIA_TYPE
from app.schemas.v1.common import ProblemResponse

_PROBLEM_SCHEMA_NAME = "ProblemResponse"
_DEFAULT_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def _harden_problem_responses(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    problem = ProblemResponse.model_json_schema(ref_template="#/components/schemas/{model}")
    # Pydantic nests referenced models (FieldErrorItem) under $defs; they must be components.
    components.update(problem.pop("$defs", {}))
    components[_PROBLEM_SCHEMA_NAME] = problem
    problem_422 = {
        "description": "Validation error",
        "content": {
            PROBLEM_MEDIA_TYPE: {"schema": {"$ref": f"#/components/schemas/{_PROBLEM_SCHEMA_NAME}"}}
        },
    }
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue  # sibling keys like "parameters" are not HTTP methods
            responses = operation.get("responses")
            if responses and "422" in responses:
                responses["422"] = problem_422
    for name in _DEFAULT_VALIDATION_SCHEMAS:
        components.pop(name, None)


def use_custom_openapi(app: FastAPI) -> None:
    """Wrap `app.openapi` so the first build is hardened, then cached like normal."""
    generate = app.openapi

    def custom_openapi() -> dict[str, Any]:
        already_built = app.openapi_schema is not None
        schema = generate()
        if not already_built:
            _harden_problem_responses(schema)
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
