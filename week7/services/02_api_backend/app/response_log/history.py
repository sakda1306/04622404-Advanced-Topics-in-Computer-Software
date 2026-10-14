"""Sessions, history and feedback for the signed-in user (CONTRACT §1)."""

from __future__ import annotations

import asyncio
import time
import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, utcnow
from app.core.errors import AppError, ErrorCode
from app.db.models import ChatSession, Feedback, Message, User
from app.infra.store import Store
from app.response_log.recorder import pending_key
from app.schemas.chat import (
    FeedbackRequest,
    History,
    MessageOut,
    SessionItem,
    SessionList,
)
from app.schemas.common import HistoryMessage, Source

_FEEDBACK_POLL_SECONDS = 0.2
SESSION_TITLE_CHARS = 60


def session_title(first_message: str) -> str:
    title = " ".join(first_message.split())
    return title if len(title) <= SESSION_TITLE_CHARS else title[: SESSION_TITLE_CHARS - 1] + "…"


async def owned_session(db: AsyncSession, session_id: uuid.UUID, user: User) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND)
    return session


async def list_sessions(db: AsyncSession, user: User, limit: int = 100) -> SessionList:
    rows = await db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(limit)
    )
    return SessionList(
        sessions=[
            SessionItem(session_id=s.id, title=s.title, updated_at=iso(s.updated_at) or "")
            for s in rows
        ]
    )


async def recent_messages(db: AsyncSession, session_id: uuid.UUID, limit: int) -> list[Message]:
    """The last `limit` messages of a session, oldest first."""
    rows = await db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


async def router_history(
    db: AsyncSession, session_id: uuid.UUID, limit: int
) -> list[HistoryMessage]:
    return [
        HistoryMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in await recent_messages(db, session_id, limit)
    ]


async def get_history(db: AsyncSession, user: User, session_id: uuid.UUID, limit: int) -> History:
    await owned_session(db, session_id, user)
    messages = await recent_messages(db, session_id, limit)
    ratings: dict[uuid.UUID, int] = {}
    answer_ids = [m.id for m in messages if m.role == "assistant"]
    if answer_ids:
        rows = await db.execute(
            select(Feedback.message_id, Feedback.rating).where(Feedback.message_id.in_(answer_ids))
        )
        ratings = {message_id: rating for message_id, rating in rows.all()}
    return History(
        session_id=session_id,
        messages=[
            MessageOut(
                message_id=m.id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                sources=[Source.model_validate(s) for s in m.sources or []],
                route=m.route,  # type: ignore[arg-type]
                rating=ratings.get(m.id),
                created_at=iso(m.created_at) or "",
            )
            for m in messages
        ],
    )


async def save_feedback(
    db: AsyncSession, store: Store, user: User, body: FeedbackRequest, wait_seconds: float
) -> None:
    # Read once: the rollback below expires every loaded object, `user` included.
    user_id = user.id
    deadline = time.monotonic() + wait_seconds
    while True:
        message = await db.get(Message, body.message_id, populate_existing=True)
        if message is not None:
            break
        pending = await store.get_json(pending_key(body.message_id))
        # With the store down the pending mark is unknown, so wait instead of answering 404.
        if pending != str(user_id) and store.available:
            raise AppError(ErrorCode.NOT_FOUND)
        if time.monotonic() >= deadline:
            raise AppError(ErrorCode.MESSAGE_NOT_READY)
        await asyncio.sleep(_FEEDBACK_POLL_SECONDS)
        # End the read transaction so the next poll sees the background write.
        await db.rollback()

    if message.user_id != user_id or message.role != "assistant":
        raise AppError(ErrorCode.NOT_FOUND)
    # One statement, so two clicks arriving together cannot both try to insert.
    dialect = postgresql if db.get_bind().dialect.name == "postgresql" else sqlite
    values = {"rating": body.rating, "comment": body.comment, "created_at": utcnow()}
    await db.execute(
        dialect.insert(Feedback)
        .values(message_id=message.id, user_id=user_id, **values)
        .on_conflict_do_update(index_elements=[Feedback.message_id], set_=values)
    )
    await db.commit()
