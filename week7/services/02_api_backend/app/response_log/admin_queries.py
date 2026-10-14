"""Read side of the admin pages: stats, feedback, messages, logs (CONTRACT §1.1)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.clock import iso, utcnow
from app.core.errors import AppError, ErrorCode
from app.db.models import Feedback, Message, RequestLog, User
from app.response_log.cursor import before_cursor, encode_cursor
from app.schemas.admin import (
    AdminMessage,
    FeedbackItem,
    FeedbackSummary,
    LatencySummary,
    LogItem,
    Stats,
    UserRef,
)
from app.schemas.common import Page, Source, TokenUsage, Trace

ANSWER_PREVIEW_CHARS = 120


def percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile; 0 for no data."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(int(-(-pct * len(ordered) // 100)), 1)
    return ordered[min(rank, len(ordered)) - 1]


async def stats(db: AsyncSession, days: int) -> Stats:
    since = utcnow() - timedelta(days=days)
    answered = (RequestLog.created_at >= since, RequestLog.status == 200)

    by_route = await db.execute(
        select(RequestLog.route, func.count()).where(*answered).group_by(RequestLog.route)
    )
    by_layer = await db.execute(
        select(RequestLog.decided_at_layer, func.count())
        .where(*answered)
        .group_by(RequestLog.decided_at_layer)
    )
    fallback_count = await db.scalar(
        select(func.count()).where(*answered, RequestLog.fallback.is_not(None))
    )
    latencies = list(await db.scalars(select(RequestLog.latency_ms).where(*answered)))
    ratings = await db.execute(
        select(Feedback.rating, func.count())
        .where(Feedback.created_at >= since)
        .group_by(Feedback.rating)
    )
    rating_counts = {rating: count for rating, count in ratings.all()}

    route_counts = {route or "unknown": count for route, count in by_route.all()}
    return Stats(
        days=days,
        total_messages=sum(route_counts.values()),
        by_route=route_counts,
        by_layer={layer or "unknown": count for layer, count in by_layer.all()},
        feedback=FeedbackSummary(up=rating_counts.get(1, 0), down=rating_counts.get(-1, 0)),
        latency_ms=LatencySummary(p50=percentile(latencies, 50), p95=percentile(latencies, 95)),
        fallback_count=fallback_count or 0,
    )


def _fallback_of(message: Message) -> str | None:
    trace = message.trace or {}
    value = trace.get("fallback")
    return str(value) if value else None


async def list_feedback(
    db: AsyncSession,
    *,
    rating: int | None,
    days: int,
    route: str | None,
    limit: int,
    cursor: str | None,
) -> Page[FeedbackItem]:
    question = aliased(Message)
    query = (
        select(Feedback, Message, User, question.content)
        .join(Message, Message.id == Feedback.message_id)
        .join(User, User.id == Feedback.user_id)
        .outerjoin(question, question.id == Message.reply_to_id)
        .where(Feedback.created_at >= utcnow() - timedelta(days=days))
        .order_by(Feedback.created_at.desc(), Feedback.message_id.desc())
        .limit(limit + 1)
    )
    if rating is not None:
        query = query.where(Feedback.rating == rating)
    if route:
        query = query.where(Message.route == route)
    after = before_cursor(cursor, Feedback.created_at, Feedback.message_id, uuid.UUID)
    if after is not None:
        query = query.where(after)

    rows = (await db.execute(query)).all()
    items = [
        FeedbackItem(
            message_id=fb.message_id,
            rating=fb.rating,
            comment=fb.comment,
            created_at=iso(fb.created_at) or "",
            user=UserRef(id=user.id, username=user.username),
            question=question_text,
            answer_preview=message.content[:ANSWER_PREVIEW_CHARS],
            route=message.route,
            fallback=_fallback_of(message),
        )
        for fb, message, user, question_text in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = encode_cursor(last.created_at, last.message_id)
    return Page[FeedbackItem](items=items, next_cursor=next_cursor)


async def admin_message(db: AsyncSession, message_id: uuid.UUID) -> AdminMessage:
    message = await db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise AppError(ErrorCode.NOT_FOUND)
    user = await db.get(User, message.user_id)
    assert user is not None
    question = await db.get(Message, message.reply_to_id) if message.reply_to_id else None
    feedback = await db.get(Feedback, message.id)
    return AdminMessage(
        message_id=message.id,
        request_id=message.request_id,
        session_id=message.session_id,
        user=UserRef(id=user.id, username=user.username),
        question=question.content if question else None,
        answer=message.content,
        sources=[Source.model_validate(s) for s in message.sources or []],
        route=message.route,
        confidence=message.confidence,
        reasoning=message.reasoning,
        trace=Trace.model_validate(message.trace) if message.trace else None,
        token_usage=TokenUsage.model_validate(message.token_usage) if message.token_usage else None,
        latency_ms=message.latency_ms,
        rating=feedback.rating if feedback else None,
        comment=feedback.comment if feedback else None,
        created_at=iso(message.created_at) or "",
    )


async def list_logs(
    db: AsyncSession,
    *,
    request_id: str | None,
    route: str | None,
    fallback: str | None,
    days: int,
    limit: int,
    cursor: str | None,
) -> Page[LogItem]:
    query = select(RequestLog).order_by(RequestLog.created_at.desc(), RequestLog.id.desc())
    if request_id:
        # A request id finds its log whatever its age.
        query = query.where(RequestLog.request_id == request_id)
    else:
        query = query.where(RequestLog.created_at >= utcnow() - timedelta(days=days))
    if route:
        query = query.where(RequestLog.route == route)
    if fallback == "any":
        query = query.where(RequestLog.fallback.is_not(None))
    elif fallback:
        query = query.where(RequestLog.fallback == fallback)
    after = before_cursor(cursor, RequestLog.created_at, RequestLog.id, uuid.UUID)
    if after is not None:
        query = query.where(after)

    rows = list(await db.scalars(query.limit(limit + 1)))
    items = [
        LogItem(
            request_id=r.request_id,
            message_id=r.message_id,
            user_id=r.user_id,
            route=r.route,
            decided_at_layer=r.decided_at_layer,
            fallback=r.fallback,
            status=r.status,
            error_code=r.error_code,
            latency_ms=r.latency_ms,
            created_at=iso(r.created_at) or "",
        )
        for r in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return Page[LogItem](items=items, next_cursor=next_cursor)
