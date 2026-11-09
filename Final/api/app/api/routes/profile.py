"""Generate, read and edit the profile (Contract.md §2.5, PRD FR-14 – FR-17, FR-27 – FR-34)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import ProfileGenerated, ProfileOut
from app.services import explanation_service, profile_edit_service, profile_service

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("/generate")
async def generate_profile(
    user: CurrentUser, container: ContainerDep, db: DbDep
) -> ProfileGenerated:
    profile: dict[str, Any] = await profile_service.generate_profile(
        db, container.llm, container.settings, user_id=user.id
    )
    matches = await explanation_service.after_generate(
        db,
        container.llm,
        container.knowledge,
        container.settings,
        user_id=user.id,
        profile=profile,
    )
    return ProfileGenerated(profile=profile, matches=matches)


@router.get("")
async def get_profile(user: CurrentUser, db: DbDep) -> ProfileOut:
    return ProfileOut(profile=await profile_service.get_profile(db, user.id))


@router.get("/edits/pending")
async def pending_edits(user: CurrentUser, db: DbDep) -> dict[str, Any]:
    return {"edits": await profile_edit_service.pending(db, user.id)}


@router.post("/edits/{edit_id}/confirm")
async def confirm_edit(
    edit_id: str, user: CurrentUser, container: ContainerDep, db: DbDep
) -> ProfileGenerated:
    result = await profile_edit_service.confirm(
        db, container.settings, user_id=user.id, edit_id=edit_id
    )
    return ProfileGenerated(**result)


@router.post("/edits/{edit_id}/reject")
async def reject_edit(edit_id: str, user: CurrentUser, db: DbDep) -> dict[str, bool]:
    await profile_edit_service.reject(db, user_id=user.id, edit_id=edit_id)
    return {"ok": True}


@router.delete("/skills/{skill_id}")
async def remove_skill(
    skill_id: str, user: CurrentUser, container: ContainerDep, db: DbDep
) -> ProfileGenerated:
    result = await profile_edit_service.remove_skill(
        db, container.settings, user_id=user.id, skill_id=skill_id
    )
    return ProfileGenerated(**result)


@router.post("/skills/{skill_id}/restore")
async def restore_skill(
    skill_id: str, user: CurrentUser, container: ContainerDep, db: DbDep
) -> ProfileGenerated:
    result = await profile_edit_service.restore_skill(
        db, container.settings, user_id=user.id, skill_id=skill_id
    )
    return ProfileGenerated(**result)


@router.get("/removed-skills")
async def removed_skills(user: CurrentUser, db: DbDep) -> dict[str, Any]:
    return {"skills": await profile_edit_service.removed_skills(db, user.id)}


@router.patch("/preferences")
async def update_preferences(
    body: dict[str, Any], user: CurrentUser, container: ContainerDep, db: DbDep
) -> ProfileGenerated:
    result = await profile_edit_service.update_preferences(
        db, container.settings, user_id=user.id, body=body
    )
    return ProfileGenerated(**result)
