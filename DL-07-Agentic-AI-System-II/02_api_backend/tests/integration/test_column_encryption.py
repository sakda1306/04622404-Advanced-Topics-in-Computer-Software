"""Free text is stored encrypted (D-81), and migration 0009 encrypts older rows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.ids import new_id
from app.infrastructure.db.models import FeedbackModel, MessageModel
from tests.integration import factories
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


async def test_values_are_encrypted_at_rest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = factories.user()
    chat = factories.conversation(owner)
    message = MessageModel(
        id=new_id(), conversation_id=chat.id, role="user", content="บ้านเลขที่ 12", created_at=NOW
    )
    feedback = FeedbackModel(
        id=new_id(),
        recommendation_id=uuid4(),
        pseudonymous_id="p",
        outcome="UNKNOWN",
        comment="my street is flooded",
        review_status="not_required",
        created_at=NOW,
        expires_at=NOW + timedelta(days=180),
    )
    async with session_factory() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add(chat)
        await session.flush()
        session.add_all([message, feedback])

    async with session_factory() as session:
        raw_content = await session.scalar(
            text("SELECT content FROM messages WHERE id = :id"), {"id": message.id}
        )
        raw_comment = await session.scalar(
            text("SELECT comment FROM feedback WHERE id = :id"), {"id": feedback.id}
        )
        content = await session.scalar(
            select(MessageModel.content).where(MessageModel.id == message.id)
        )
        comment = await session.scalar(
            select(FeedbackModel.comment).where(FeedbackModel.id == feedback.id)
        )

    assert raw_content.startswith("enc:v1:")
    assert "12" not in raw_content
    assert raw_comment.startswith("enc:v1:")
    assert "flooded" not in raw_comment
    assert content == "บ้านเลขที่ 12"
    assert comment == "my street is flooded"


def _run(url: str, fn: Any) -> Any:
    async def _inner() -> Any:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                return await conn.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _seed_plaintext(conn: Connection) -> None:
    user_id, conversation_id = new_id(), new_id()
    conn.execute(
        text(
            "INSERT INTO users (id, oidc_issuer, oidc_subject, pseudonymous_id) "
            "VALUES (:id, 'iss', 'sub-legacy', 'p-legacy')"
        ),
        {"id": user_id},
    )
    conn.execute(
        text(
            "INSERT INTO conversations (id, user_id, language, message_count, expires_at) "
            "VALUES (:id, :user, 'th', 1, now() + interval '30 days')"
        ),
        {"id": conversation_id, "user": user_id},
    )
    conn.execute(
        text(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (:id, :conv, 'user', 'legacy question', now())"
        ),
        {"id": new_id(), "conv": conversation_id},
    )
    conn.execute(
        text(
            "INSERT INTO feedback (id, recommendation_id, pseudonymous_id, outcome, comment, "
            "review_status, created_at, expires_at) VALUES (:id, :rec, 'p-legacy', 'UNKNOWN', "
            "'legacy comment', 'not_required', now(), now() + interval '180 days')"
        ),
        {"id": new_id(), "rec": uuid4()},
    )


def _raw(conn: Connection) -> tuple[str, str]:
    content = conn.execute(
        text("SELECT content FROM messages WHERE role = 'user' LIMIT 1")
    ).scalar_one()
    comment = conn.execute(text("SELECT comment FROM feedback LIMIT 1")).scalar_one()
    return content, comment


def test_migration_encrypts_and_decrypts_existing_rows(empty_db_url: str) -> None:
    config = alembic_config(empty_db_url)
    command.upgrade(config, "0008")
    _run(empty_db_url, _seed_plaintext)

    command.upgrade(config, "0009")
    encrypted = _run(empty_db_url, _raw)
    command.downgrade(config, "0008")
    restored = _run(empty_db_url, _raw)

    assert all(value.startswith("enc:v1:") for value in encrypted)
    assert restored == ("legacy question", "legacy comment")
