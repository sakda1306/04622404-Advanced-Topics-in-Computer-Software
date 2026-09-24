"""Send a Problem Details response directly from ASGI middleware."""

from __future__ import annotations

import json

from starlette.types import Send

from app.api.problem import PROBLEM_MEDIA_TYPE, problem_body
from app.core.errors import ErrorCode


async def send_problem(
    send: Send,
    code: ErrorCode,
    path: str,
    type_base_url: str,
    headers: dict[str, str] | None = None,
) -> None:
    problem = problem_body(code, instance=path, type_base_url=type_base_url)
    body = json.dumps(problem).encode()
    raw_headers = [
        (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
        (b"content-length", str(len(body)).encode()),
    ]
    raw_headers += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send(
        {
            "type": "http.response.start",
            "status": problem["status"],
            "headers": raw_headers,
        }
    )
    await send({"type": "http.response.body", "body": body})
