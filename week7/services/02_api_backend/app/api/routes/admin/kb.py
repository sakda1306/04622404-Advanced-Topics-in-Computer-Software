"""Knowledge Base page (Could): index stats, delete one document, rebuild (05 §6)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from app.api.deps import AdminUser, ContainerDep, DbDep
from app.core.ids import current_request_id
from app.schemas.admin import ReindexRequest
from app.services.audit import write_audit

router = APIRouter(prefix="/kb")

# One document per call; there is no bulk delete on purpose.
DocId = Annotated[str, Path(max_length=120, pattern=r"^[A-Za-z0-9._-]+$")]


@router.get("/stats")
async def kb_stats(container: ContainerDep) -> Any:
    return await container.retrieval.stats()


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: DocId, container: ContainerDep, db: DbDep, admin: AdminUser
) -> dict[str, bool]:
    result = await container.retrieval.delete_document(doc_id)
    deleted = bool(result.get("deleted"))
    await write_audit(db, admin, "kb.delete", doc_id, after={"deleted": deleted})
    return {"deleted": deleted}


@router.post("/reindex", status_code=202)
async def reindex(
    body: ReindexRequest, container: ContainerDep, db: DbDep, admin: AdminUser
) -> JSONResponse:
    result = await container.retrieval.rebuild(current_request_id(), body.category)
    await write_audit(
        db,
        admin,
        "kb.reindex",
        body.category or "all",
        after={"job_id": result.get("job_id")},
    )
    return JSONResponse({"job_id": result.get("job_id")}, status_code=202)
