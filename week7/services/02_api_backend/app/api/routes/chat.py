"""Chat, sessions, history and feedback (CONTRACT §1)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.infra.rate_limit import enforce_rate_limit
from app.response_log.history import get_history, list_sessions, save_feedback
from app.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest, History, SessionList
from app.schemas.common import Ok
from app.services import chat_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatRequest,
    background: BackgroundTasks,
    container: ContainerDep,
    db: DbDep,
    user: CurrentUser,
) -> ChatResponse:
    await enforce_rate_limit(
        container.store, "chat", str(user.id), container.settings.chat_rate_limit_per_minute
    )
    return await chat_service.chat(container, db, user, body, background)


@router.get("/sessions")
async def sessions(db: DbDep, user: CurrentUser) -> SessionList:
    return await list_sessions(db, user)


@router.get("/history/{session_id}")
async def history(
    session_id: UUID,
    db: DbDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> History:
    return await get_history(db, user, session_id, limit)


@router.post("/feedback")
async def feedback(
    body: FeedbackRequest, container: ContainerDep, db: DbDep, user: CurrentUser
) -> Ok:
    await save_feedback(db, container.store, user, body, container.settings.feedback_wait_seconds)
    return Ok()
