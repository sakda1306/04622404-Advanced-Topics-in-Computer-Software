"""All /v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    conversations,
    exports,
    feedback,
    jobs,
    me,
    recommendations,
    service_status,
    trips,
)
from app.api.v1.admin import audit, reviews
from app.api.v1.admin import exports as admin_exports
from app.api.v1.admin import jobs as admin_jobs
from app.api.v1.admin import recommendations as admin_recommendations

router = APIRouter(prefix="/v1")
router.include_router(recommendations.router)
router.include_router(jobs.router)
router.include_router(conversations.router)
router.include_router(trips.router)
router.include_router(feedback.router)
router.include_router(reviews.router)
router.include_router(admin_jobs.router)
router.include_router(admin_recommendations.router)
router.include_router(audit.router)
router.include_router(admin_exports.router)
router.include_router(me.router)
router.include_router(exports.router)
router.include_router(service_status.router)
