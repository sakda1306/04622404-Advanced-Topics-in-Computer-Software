"""Responses whose status code depends on the outcome (200 / 201 / 202)."""

from __future__ import annotations

from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.schemas.v1.travel import JobAccepted
from app.services.recommendation_service import Accepted


def json_response(
    model: BaseModel, status: int, response: Response, *, location: str | None = None
) -> JSONResponse:
    result = JSONResponse(model.model_dump(mode="json", by_alias=True), status_code=status)
    # Headers set by dependencies (rate limit) are not merged into a returned response.
    for name, value in response.headers.items():
        if name.lower().startswith("ratelimit-"):
            result.headers[name] = value
    if location is not None:
        result.headers["Location"] = location
    return result


def accepted_response(outcome: Accepted, response: Response) -> JSONResponse:
    body = JobAccepted.build(outcome.job_id, outcome.recommendation_id, outcome.conversation_id)
    return json_response(body, 202, response, location=body.status_url)
