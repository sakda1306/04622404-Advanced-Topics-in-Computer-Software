"""
PostgreSQL persistence — replaces the earlier in-memory lists with real
writes to the `recommendation_log` and `user_feedback` tables defined in
db_schema.sql (which Postgres runs automatically on first container start
via docker-entrypoint-initdb.d).

Uses SQLAlchemy's async engine with the asyncpg driver, per 01_env.txt.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings
from app.schema import FeedbackSubmission, RecommendationResponse

logger = structlog.get_logger("db")

engine: AsyncEngine = create_async_engine(settings.database_url, echo=False, future=True)


async def wait_for_db(retries: int = 10, delay_seconds: float = 2.0) -> None:
    """Postgres can take a few seconds to accept connections after container
    start; retry instead of failing the whole app on first boot."""
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("db_ready", attempt=attempt)
            return
        except Exception as exc:  # noqa: BLE001 - broad on purpose during startup retry
            logger.warning("db_not_ready", attempt=attempt, error=str(exc))
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("Database did not become ready in time")


async def save_recommendation(response: RecommendationResponse, pseudonymous_user_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO recommendation_log
                    (request_id, schema_version, action_code, risk_level, confidence,
                     confidence_level, short_summary, observed_at, fetched_at, expires_at,
                     pseudonymous_user_id, payload)
                VALUES
                    (:request_id, :schema_version, :action_code, :risk_level, :confidence,
                     :confidence_level, :short_summary, :observed_at, :fetched_at, :expires_at,
                     :pseudonymous_user_id, CAST(:payload AS JSONB))
                ON CONFLICT (request_id) DO NOTHING
                """
            ),
            {
                "request_id": response.request_id,
                "schema_version": response.schema_version,
                "action_code": response.action_code.value,
                "risk_level": response.risk_level.value,
                "confidence": response.confidence,
                "confidence_level": response.confidence_level.value if response.confidence_level else None,
                "short_summary": response.short_summary,
                "observed_at": response.observed_at,
                "fetched_at": response.fetched_at,
                "expires_at": response.expires_at,
                "pseudonymous_user_id": pseudonymous_user_id,
                "payload": response.model_dump_json(),
            },
        )


async def get_recommendation(request_id: str) -> Optional[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT payload FROM recommendation_log WHERE request_id = :rid"),
            {"rid": request_id},
        )
        row = result.first()
        if row is None:
            return None
        payload = row[0]
        # A raw text() query may hand JSONB back as a string depending on the
        # driver codec; normalise so callers always get a dict.
        return json.loads(payload) if isinstance(payload, (str, bytes)) else payload


async def save_feedback(feedback: FeedbackSubmission, escalated: bool) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO user_feedback
                    (request_id, pseudonymous_user_id, category, comment,
                     submitted_at, escalated_to_safety)
                VALUES
                    (:request_id, :pseudonymous_user_id, :category, :comment,
                     :submitted_at, :escalated_to_safety)
                """
            ),
            {
                "request_id": feedback.request_id,
                "pseudonymous_user_id": feedback.pseudonymous_user_id,
                "category": feedback.category.value,
                "comment": feedback.comment,
                "submitted_at": feedback.submitted_at,
                "escalated_to_safety": escalated,
            },
        )


async def mark_reviewed(request_id: str, reviewer: str, approve_for_training: bool = True) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE user_feedback
                SET reviewed = TRUE,
                    reviewed_at = :reviewed_at,
                    reviewed_by = :reviewer,
                    approved_for_training = :approve
                WHERE request_id = :request_id
                """
            ),
            {
                "reviewed_at": datetime.now(timezone.utc),
                "reviewer": reviewer,
                "approve": approve_for_training,
                "request_id": request_id,
            },
        )


async def fetch_pending_safety_review() -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT feedback_id, request_id, pseudonymous_user_id, category,
                       comment, submitted_at
                FROM user_feedback
                WHERE escalated_to_safety = TRUE AND reviewed = FALSE
                ORDER BY submitted_at ASC
                """
            )
        )
        return [dict(row._mapping) for row in result.fetchall()]


async def fetch_reviewed_for_training() -> list[dict[str, Any]]:
    """The ONLY feedback set that may be used for evaluation/retraining."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT feedback_id, request_id, pseudonymous_user_id, category,
                       comment, submitted_at
                FROM user_feedback
                WHERE reviewed = TRUE AND approved_for_training = TRUE
                """
            )
        )
        return [dict(row._mapping) for row in result.fetchall()]


async def purge_expired_feedback(retention_days: int = 180) -> int:
    """
    Purge user feedback rows older than the specified retention window (Contract Register v4 / P-23).
    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("DELETE FROM user_feedback WHERE submitted_at < :cutoff"),
            {"cutoff": cutoff},
        )
        deleted = result.rowcount
        logger.info("feedback_retention_purged", deleted_count=deleted, cutoff=cutoff.isoformat())
        return deleted
