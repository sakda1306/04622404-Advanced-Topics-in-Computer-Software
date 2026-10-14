"""Write chat turns and request logs after the answer has been sent (CONTRACT §1).

`/api/chat` marks the new message id as pending before it answers; the background
write clears the mark. `/api/feedback` uses the mark to tell "still being written"
(wait, then 409 MESSAGE_NOT_READY) from "does not exist" (404).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.core.logging import get_logger
from app.db.models import ChatSession, Message, RequestLog
from app.infra.store import Store
from app.schemas.chat import RouteResponse

log = get_logger(__name__)

PENDING_TTL_SECONDS = 60


def pending_key(message_id: uuid.UUID) -> str:
    return f"pending:message:{message_id}"


async def mark_pending(store: Store, message_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await store.set_json(pending_key(message_id), str(user_id), PENDING_TTL_SECONDS)


@dataclass(frozen=True, slots=True)
class AnsweredTurn:
    request_id: str
    session_id: uuid.UUID
    user_id: uuid.UUID
    question: str
    asked_at: datetime
    message_id: uuid.UUID
    answered_at: datetime
    result: RouteResponse
    latency_ms: int
    data_as_of: str | None


async def record_answer(
    sessions: async_sessionmaker[AsyncSession], store: Store, turn: AnsweredTurn
) -> None:
    result = turn.result
    trace = result.trace
    question_id = new_id()
    try:
        async with sessions() as db, db.begin():
            db.add(
                Message(
                    id=question_id,
                    session_id=turn.session_id,
                    user_id=turn.user_id,
                    role="user",
                    content=turn.question,
                    request_id=turn.request_id,
                    sources=[],
                    created_at=turn.asked_at,
                )
            )
            # Flushed first: the answer row points at the question.
            await db.flush()
            db.add(
                Message(
                    id=turn.message_id,
                    session_id=turn.session_id,
                    user_id=turn.user_id,
                    role="assistant",
                    content=result.answer,
                    request_id=turn.request_id,
                    reply_to_id=question_id,
                    sources=[s.model_dump(mode="json") for s in result.sources],
                    route=result.route,
                    engines_used=list(result.engines_used),
                    confidence=result.confidence,
                    reasoning=result.reasoning,
                    trace=trace.model_dump(mode="json") if trace else None,
                    token_usage=(
                        result.token_usage.model_dump(mode="json") if result.token_usage else None
                    ),
                    latency_ms=turn.latency_ms,
                    data_as_of=turn.data_as_of,
                    # Strictly after the question so history keeps the pair in order.
                    created_at=max(turn.answered_at, turn.asked_at + timedelta(microseconds=1)),
                )
            )
            db.add(
                RequestLog(
                    request_id=turn.request_id,
                    message_id=turn.message_id,
                    user_id=turn.user_id,
                    route=result.route,
                    decided_at_layer=trace.decided_at_layer if trace else None,
                    fallback=trace.fallback if trace else None,
                    status=200,
                    latency_ms=turn.latency_ms,
                    created_at=turn.answered_at,
                )
            )
            await db.execute(
                update(ChatSession)
                .where(ChatSession.id == turn.session_id)
                .values(updated_at=turn.answered_at)
            )
    except Exception:
        log.exception("record_answer_failed", message_id=str(turn.message_id))
    finally:
        await store.delete(pending_key(turn.message_id))


async def record_failure(
    sessions: async_sessionmaker[AsyncSession],
    *,
    request_id: str,
    user_id: uuid.UUID,
    status: int,
    error_code: str,
    latency_ms: int,
    at: datetime,
) -> None:
    try:
        async with sessions() as db, db.begin():
            db.add(
                RequestLog(
                    request_id=request_id,
                    user_id=user_id,
                    status=status,
                    error_code=error_code,
                    latency_ms=latency_ms,
                    created_at=at,
                )
            )
    except Exception:
        log.exception("record_failure_failed")
