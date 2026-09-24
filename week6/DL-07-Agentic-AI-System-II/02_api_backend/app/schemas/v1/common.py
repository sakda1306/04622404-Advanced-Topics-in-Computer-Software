"""Shapes shared across the v1 contract (docs/02_api_spec.md section 3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldErrorItem(_Strict):
    field: str
    message: str
    code: str


class ProblemResponse(_Strict):
    """RFC 9457 Problem Details — the shape of every error response (app/api/problem.py).

    FastAPI documents its own `HTTPValidationError` for 422 by default; `custom_openapi`
    in app/main.py replaces every generated 422 (and adds this for other error statuses
    declared per-route) with this schema so the exported contract matches what the API
    actually sends.
    """

    type: str
    title: str
    status: int
    code: str
    detail: str | None
    instance: str
    request_id: str | None
    correlation_id: str | None
    errors: list[FieldErrorItem] | None
