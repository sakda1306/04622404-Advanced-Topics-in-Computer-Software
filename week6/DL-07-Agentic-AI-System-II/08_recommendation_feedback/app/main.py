"""
Module: 08_recommendation_feedback — FastAPI service.

Run via Docker Compose (recommended):
    docker compose up -d --build

Or standalone (needs DATABASE_URL / REDIS_URL pointing at reachable
Postgres/Redis instances):
    uvicorn app.main:app --reload --port 8080

Endpoints:
    GET  /health                           -> service + DB + Redis status
    GET  /recommendation/mock/{scenario}    -> mock RecommendationResponse, persisted to DB
        (accepts ?region=TH — emergency contacts are validated against it)
    POST /recommendation/generate          -> live call to Module 07, validate and persist
    POST /feedback                          -> submit explicit user feedback
    GET  /feedback/safety-queue             -> pending human safety reviews
    POST /feedback/{request_id}/review      -> mark a report reviewed (ops-only)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from app import db, feedback as feedback_module, monitoring
from app.adapter import decision_to_recommendation
from app.config import settings
from app.decision_client import DecisionEngineClient
from app.emergency import validate_emergency_content
from app.mock_data import ALL_SCENARIOS
from app.schema import FeedbackSubmission, RecommendationResponse

logger = structlog.get_logger("main")
decision_client = DecisionEngineClient()


async def _retention_cleaner_loop(interval_seconds: float = 86400.0):
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            purged = await db.purge_expired_feedback(settings.feedback_retention_days)
            logger.info("retention_background_cleaner_completed", purged=purged)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("retention_background_cleaner_error", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitoring.init_monitoring()
    await db.wait_for_db()
    cleaner_task = asyncio.create_task(_retention_cleaner_loop())
    try:
        yield
    finally:
        cleaner_task.cancel()
        try:
            await cleaner_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Recommendation & Feedback Service",
    version=settings.recommendation_schema_version,
    lifespan=lifespan,
)


class ReviewRequest(BaseModel):
    reviewer: str
    approve_for_training: bool = True


@app.get("/health")
async def health():
    db_ok = True
    try:
        await db.wait_for_db(retries=1, delay_seconds=0)
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "schema_version": settings.recommendation_schema_version,
        "database": "ok" if db_ok else "unreachable",
    }

@app.get("/recommendation/mock/{scenario}")
async def get_mock_recommendation(
    scenario: str, user_id: str = "anon-demo-user", region: Optional[str] = None
):
    if scenario not in ALL_SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Options: {list(ALL_SCENARIOS)}",
        )
    response = ALL_SCENARIOS[scenario]
    await db.save_recommendation(response, pseudonymous_user_id=user_id)
    monitoring.record_recommendation_viewed(response.action_code.value)
    # Stored as produced (audit); contacts are re-validated every time we serve.
    return validate_emergency_content(response, region)


@app.get("/recommendation/{request_id}", response_model=RecommendationResponse)
async def get_stored_recommendation(request_id: str, region: Optional[str] = None):
    """
    Internal query endpoint: re-fetch a previously served and logged recommendation.
    Re-validates emergency contacts against the current traveler region.
    """
    payload = await db.get_recommendation(request_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="request_id not found")
    try:
        response = RecommendationResponse.model_validate(payload)
    except ValidationError:
        logger.error("stored_recommendation_invalid", request_id=request_id)
        raise HTTPException(
            status_code=500, detail="stored recommendation does not match current schema"
        )
    return validate_emergency_content(response, region)


@app.post("/recommendation/generate", response_model=RecommendationResponse)
async def generate_recommendation(
    payload: dict,
    user_id: str = "anon-user",
    region: Optional[str] = None,
):
    """
    Call Module 07 (Decision & LLM Engine) live via HTTP POST /v1/decisions,
    adapt the DecisionResponse into RecommendationResponse, validate emergency
    contacts, record metrics, and persist to PostgreSQL.
    """
    decision = await decision_client.request_decision(payload)
    response = decision_to_recommendation(decision, traveler_region=region)
    await db.save_recommendation(response, pseudonymous_user_id=user_id)
    monitoring.record_recommendation_viewed(response.action_code.value)
    return response


@app.post("/feedback")
async def submit_feedback(feedback: FeedbackSubmission):
    escalated = await feedback_module.submit_feedback(feedback)
    monitoring.record_feedback_submitted(feedback.category.value)
    if feedback.category.value == "UNSAFE":
        monitoring.record_unsafe_feedback()
    return {
        "received": True,
        "request_id": feedback.request_id,
        "escalated_to_safety_review": escalated,
    }


@app.get("/feedback/safety-queue")
async def safety_queue():
    pending = await feedback_module.pending_safety_review()
    return {"pending_count": len(pending), "items": pending}


@app.post("/feedback/{request_id}/review")
async def review_feedback(request_id: str, review: ReviewRequest):
    await feedback_module.mark_reviewed(
        request_id, reviewer=review.reviewer, approve_for_training=review.approve_for_training
    )
    return {"request_id": request_id, "reviewed": True}


@app.post("/feedback/cleanup")
async def manual_retention_cleanup():
    """Manual/Cron trigger to purge feedback older than FEEDBACK_RETENTION_DAYS."""
    count = await db.purge_expired_feedback(settings.feedback_retention_days)
    return {
        "status": "completed",
        "retention_days": settings.feedback_retention_days,
        "purged_count": count,
    }


@app.get("/")
async def root():
    return {
        "service": "08_recommendation_feedback",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "try": "/recommendation/mock/travel_normally",
    }
