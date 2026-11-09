"""CV upload and parse (Contract.md §2.2, PRD FR-0 – FR-4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import ConfirmCvRequest, CvConfirmed, CvDeleted, CvEnvelope, CvOut
from app.infra.models import CvDocument
from app.services import completeness_service, cv_service

router = APIRouter(prefix="/api", tags=["cv"])


def _without_empty(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Optional Contract fields (`skill_id?`, `level?` …) are left out rather than sent as null.
    return [{k: v for k, v in item.items() if v is not None} for item in items]


def _cv_out(doc: CvDocument) -> CvOut:
    parsed = doc.parsed
    return CvOut(
        status="confirmed" if doc.status == "confirmed" else "draft",
        filename=doc.filename,
        skills=_without_empty(parsed.get("skills", [])),
        education=_without_empty(parsed.get("education", [])),
        experience=_without_empty(parsed.get("experience", [])),
        warnings_th=list(parsed.get("warnings_th", [])),
    )


@router.post("/cv")
async def upload_cv(
    file: UploadFile, user: CurrentUser, container: ContainerDep, db: DbDep
) -> CvEnvelope:
    settings = container.settings
    data = await file.read(settings.cv_max_bytes + 1)  # one byte over is enough to refuse it
    doc = await cv_service.upload_cv(
        db,
        user.id,
        data=data,
        filename=file.filename,
        content_type=file.content_type,
        settings=settings,
    )
    return CvEnvelope(cv=_cv_out(doc))


@router.get("/cv")
async def get_cv(user: CurrentUser, db: DbDep) -> CvEnvelope:
    doc = await cv_service.get_cv(db, user.id)
    return CvEnvelope(cv=_cv_out(doc) if doc else None)


@router.put("/cv/confirm")
async def confirm_cv(
    body: ConfirmCvRequest, user: CurrentUser, container: ContainerDep, db: DbDep
) -> CvConfirmed:
    settings = container.settings
    doc = await cv_service.confirm_cv(db, user.id, body.model_dump(), settings)
    return CvConfirmed(
        cv=_cv_out(doc), completeness=await completeness_service.completeness(db, user.id, settings)
    )


@router.delete("/cv")
async def delete_cv(user: CurrentUser, container: ContainerDep, db: DbDep) -> CvDeleted:
    await cv_service.delete_cv(db, user.id)
    return CvDeleted(
        completeness=await completeness_service.completeness(db, user.id, container.settings)
    )
