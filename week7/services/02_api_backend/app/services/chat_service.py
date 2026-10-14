"""POST /api/chat: session -> history -> router -> answer, then log in the background."""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container
from app.clients.football import router_context
from app.core.clock import iso, utcnow
from app.core.errors import AppError
from app.core.ids import current_request_id, new_id
from app.db.models import ChatSession, User
from app.response_log.history import owned_session, router_history, session_title
from app.response_log.recorder import AnsweredTurn, mark_pending, record_answer, record_failure
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    RouteContext,
    RouteRequest,
    RouteUser,
)
from app.schemas.common import Source

LIVE_ORIGINS = frozenset({"football-data.org", "api-football", "generated"})


def data_as_of(sources: list[Source]) -> str | None:
    """The oldest `fetched_at` among live-data sources (CONTRACT §1 ChatResponse)."""
    oldest: tuple[datetime, str] | None = None
    for source in sources:
        if source.origin not in LIVE_ORIGINS or not source.fetched_at:
            continue
        try:
            moment = datetime.fromisoformat(source.fetched_at)
        except ValueError:
            continue
        if moment.tzinfo is None:
            continue
        if oldest is None or moment < oldest[0]:
            oldest = (moment, source.fetched_at)
    return oldest[1] if oldest else None


async def chat(
    container: Container,
    db: AsyncSession,
    user: User,
    body: ChatRequest,
    background: BackgroundTasks,
) -> ChatResponse:
    started = time.perf_counter()
    asked_at = utcnow()
    request_id = current_request_id()
    settings = container.settings

    session: ChatSession | None = None
    history = []
    if body.session_id is not None:
        session = await owned_session(db, body.session_id, user)
        history = await router_history(db, session.id, settings.history_limit)
    session_id = session.id if session else new_id()

    route_request = RouteRequest(
        request_id=request_id,
        session_id=session_id,
        user=RouteUser(id=user.id, favorite_team_id=user.favorite_team_id, language=user.language),
        query=body.message,
        history=history,
        context=RouteContext(**router_context(await container.football.cached_status())),
    )
    try:
        result = await container.router.route(route_request)
    except AppError as exc:
        await record_failure(
            container.sessions,
            request_id=request_id,
            user_id=user.id,
            status=exc.status,
            error_code=exc.code.value,
            latency_ms=int((time.perf_counter() - started) * 1000),
            at=utcnow(),
        )
        raise

    if session is None:
        # Created only once there is an answer, so failed first questions leave no empty chats.
        db.add(
            ChatSession(
                id=session_id,
                user_id=user.id,
                title=session_title(body.message),
                created_at=asked_at,
                updated_at=asked_at,
            )
        )
        await db.commit()

    message_id = new_id()
    answered_at = utcnow()
    latency_ms = int((time.perf_counter() - started) * 1000)
    as_of = data_as_of(result.sources)

    await mark_pending(container.store, message_id, user.id)
    background.add_task(
        record_answer,
        container.sessions,
        container.store,
        AnsweredTurn(
            request_id=request_id,
            session_id=session_id,
            user_id=user.id,
            question=body.message,
            asked_at=asked_at,
            message_id=message_id,
            answered_at=answered_at,
            result=result,
            latency_ms=latency_ms,
            data_as_of=as_of,
        ),
    )
    return ChatResponse(
        request_id=request_id,
        session_id=session_id,
        message_id=message_id,
        answer=result.answer,
        sources=result.sources,
        route=result.route,
        engines_used=result.engines_used,
        confidence=result.confidence,
        latency_ms=latency_ms,
        data_as_of=as_of,
        created_at=iso(answered_at) or "",
        trace=result.trace,
    )
