"""Dashboard and Feedback & Log pages (Must)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.core.errors import AppError, ErrorCode, FieldError
from app.response_log import admin_queries
from app.schemas.admin import AdminMessage, FeedbackItem, LogItem, Stats
from app.schemas.common import Page, Route, Text

router = APIRouter()

Days = Annotated[int, Query(ge=1, le=90)]
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=200)]


@router.get("/stats")
async def stats(db: DbDep, days: Days = 7) -> Stats:
    return await admin_queries.stats(db, days)


@router.get("/feedback")
async def feedback(
    db: DbDep,
    rating: Annotated[int | None, Query(ge=-1, le=1, description="1 or -1")] = None,
    days: Days = 7,
    route: Route | None = None,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> Page[FeedbackItem]:
    if rating == 0:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, errors=[FieldError("rating", "must be 1 or -1", "invalid")]
        )
    return await admin_queries.list_feedback(
        db, rating=rating, days=days, route=route, limit=limit, cursor=cursor
    )


@router.get("/messages/{message_id}")
async def message(message_id: UUID, db: DbDep) -> AdminMessage:
    return await admin_queries.admin_message(db, message_id)


@router.get("/logs")
async def logs(
    db: DbDep,
    request_id: Annotated[Text | None, Query(max_length=64)] = None,
    route: Route | None = None,
    fallback: Annotated[
        Literal["any", "retrieval_empty", "retrieval_down", "llm_fallback_provider"] | None,
        Query(description="`any` = every answer that used a fallback"),
    ] = None,
    days: Days = 1,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> Page[LogItem]:
    return await admin_queries.list_logs(
        db,
        request_id=request_id,
        route=route,
        fallback=fallback,
        days=days,
        limit=limit,
        cursor=cursor,
    )
