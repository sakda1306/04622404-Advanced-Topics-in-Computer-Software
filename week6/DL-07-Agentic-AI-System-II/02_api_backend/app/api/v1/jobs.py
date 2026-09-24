"""E-04 job status, E-05 cancel, stream tickets and E-06 SSE (docs/02_api_spec.md section 6)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.types import Receive, Send
from starlette.types import Scope as AsgiScope

from app.api.auth import authenticate, ensure_scopes, require_scopes
from app.api.deps import get_current_user, get_job_service, get_user_service
from app.api.v1.responses import json_response
from app.core.security import Scope
from app.infrastructure.redis.job_state import JobEvent
from app.schemas.v1.jobs import JobResponse, StreamTicketResponse
from app.services.job_service import JobService
from app.services.ports import JobRecord, UserRef
from app.services.user_service import UserService

router = APIRouter(prefix="/jobs", tags=["jobs"])

_SYNTHETIC_ID = "0-0"
_PING = b": ping\n\n"


def format_sse(event: JobEvent | None) -> bytes:
    if event is None:
        return _PING
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    head = f"id: {event.id}\n" if event.id != _SYNTHETIC_ID else ""
    return f"{head}event: {event.event}\ndata: {data}\n\n".encode()


async def event_frames(
    service: JobService,
    user_id: UUID,
    job: JobRecord,
    connection_id: str,
    *,
    last_event_id: str | None,
    disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[bytes]:
    try:
        async for event in service.stream(
            user_id, job, connection_id, last_event_id=last_event_id, disconnected=disconnected
        ):
            yield format_sse(event)
    finally:
        # A client that leaves cancels this task; without the shield the release is
        # cancelled too and the slot stays taken until it expires.
        with anyio.CancelScope(shield=True):
            await service.close_stream(user_id, connection_id)


class _EventStream(StreamingResponse):
    """Closes the event generator however the response ends, so its cleanup always runs."""

    async def __call__(self, scope: AsgiScope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            iterator = self.body_iterator
            if isinstance(iterator, AsyncGenerator):
                await iterator.aclose()


@router.get(
    "/{job_id}",
    summary="Job status",
    response_model=JobResponse,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_READ))],
)
async def get_job(
    job_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    return JobResponse.from_record(await service.get(user.id, job_id))


@router.delete(
    "/{job_id}",
    summary="Cancel a job",
    status_code=202,
    response_model=JobResponse,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_WRITE))],
)
async def cancel_job(
    job_id: UUID,
    response: Response,
    user: UserRef = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> JSONResponse:
    cancelled = await service.cancel(user.id, job_id)
    return json_response(JobResponse.from_record(cancelled), 202, response)


@router.post(
    "/{job_id}/stream-ticket",
    summary="Short-lived ticket for EventSource clients",
    response_model=StreamTicketResponse,
    dependencies=[Depends(require_scopes(Scope.TRAVEL_READ))],
)
async def create_stream_ticket(
    job_id: UUID,
    user: UserRef = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> StreamTicketResponse:
    ticket, expires_in = await service.issue_ticket(user.id, job_id)
    return StreamTicketResponse(ticket=ticket, expires_in=expires_in)


@router.get(
    "/{job_id}/events",
    summary="Job progress as Server-Sent Events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def job_events(
    job_id: UUID,
    request: Request,
    ticket: str | None = Query(default=None, max_length=128),
    last_event_id: str | None = Header(default=None, max_length=64),
    service: JobService = Depends(get_job_service),
    users: UserService = Depends(get_user_service),
) -> StreamingResponse:
    # EventSource cannot send headers, so a single-use ticket is accepted instead (D-06).
    if ticket is not None:
        user_id = await service.redeem_ticket(ticket, job_id)
    else:
        principal = await authenticate(request)
        ensure_scopes(principal, Scope.TRAVEL_READ)
        user_id = (await users.resolve(principal)).id
    job, connection_id = await service.open_stream(user_id, job_id)

    return _EventStream(
        event_frames(
            service,
            user_id,
            job,
            connection_id,
            last_event_id=last_event_id,
            disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
