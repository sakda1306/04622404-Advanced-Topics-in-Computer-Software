"""Saved questionnaire answers (PRD FR-5 – FR-7, Contract.md §2.3). No LLM call, no quota."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.domain.questionnaire import (
    InvalidAnswer,
    Questionnaire,
    check_answer,
    load_questionnaire,
)
from app.infra.models import Answer


def questionnaire_for(settings: Settings) -> Questionnaire:
    return load_questionnaire(settings.data_dir)


async def get_answers(db: AsyncSession, user_id: str) -> dict[str, Any]:
    rows = await db.execute(
        select(Answer.question_id, Answer.value).where(Answer.user_id == user_id)
    )
    return {question_id: value for question_id, value in rows}


async def save_answer(
    db: AsyncSession, user_id: str, question_id: str, value: Any, settings: Settings
) -> None:
    question = questionnaire_for(settings).question(question_id)
    if question is None:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)
    try:
        stored = check_answer(question, value)
    except InvalidAnswer as problem:
        field = {"field": "value", "message": problem.message, "code": problem.code}
        raise AppError(ErrorCode.VALIDATION_ERROR, details={"fields": [field]}) from problem

    if stored is None:
        await db.execute(
            delete(Answer).where(Answer.user_id == user_id, Answer.question_id == question_id)
        )
    else:
        # One statement, so two saves of the same question cannot collide (the web auto-saves).
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(Answer).values(
            user_id=user_id, question_id=question_id, value=stored, updated_at=utcnow()
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[Answer.user_id, Answer.question_id],
                set_={
                    "value": statement.excluded.value,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        )
    await db.commit()
