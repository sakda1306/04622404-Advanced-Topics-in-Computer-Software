"""Chat and the completeness meter (Contract.md §2.4, PRD FR-8, FR-9, FR-14)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import ChatHistoryOut, ChatMessageOut, ChatOut, ChatRequest
from app.core.clock import iso
from app.services import chat_service, completeness_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def send_message(
    body: ChatRequest, user: CurrentUser, container: ContainerDep, db: DbDep
) -> ChatOut:
    turn = await chat_service.send_message(
        db,
        container.llm,
        container.knowledge,
        container.settings,
        user_id=user.id,
        message=body.message,
        jev=container.jev,
    )
    return ChatOut(
        message_id=turn.message_id,
        answer=turn.answer,
        route=turn.route,
        sources=turn.sources,
        edit_proposal=turn.edit_proposal,
        completeness=turn.completeness,
        tokens_used=turn.tokens_used,
    )


@router.get("/chat/history")
async def chat_history(
    user: CurrentUser,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query(max_length=36)] = None,
) -> ChatHistoryOut:
    rows = await chat_service.history(db, user.id, limit=limit, before=before)
    return ChatHistoryOut(
        messages=[
            ChatMessageOut(
                message_id=row.id,
                role=row.role,
                text=row.text,
                route=row.route,
                sources=row.sources,
                created_at=iso(row.created_at),
            )
            for row in rows
        ]
    )


@router.get("/profile/completeness")
async def get_completeness(user: CurrentUser, container: ContainerDep, db: DbDep) -> dict[str, Any]:
    return await completeness_service.completeness(db, user.id, container.settings)
