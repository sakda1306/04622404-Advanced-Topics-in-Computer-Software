"""Role catalogue, matches, one role and its market (Contract.md §2.6, §2.7, PRD FR-18 – FR-22)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, CurrentUser, DbDep
from app.api.schemas import RoleDetailOut, RolesOut
from app.services import explanation_service, market_service, role_service

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("")
async def list_roles(_user: CurrentUser, container: ContainerDep) -> RolesOut:
    return RolesOut(roles=role_service.catalogue(container.settings))


# Before "/{role_id}", or "matches" would be read as a role id.
@router.get("/matches")
async def get_matches(user: CurrentUser, container: ContainerDep, db: DbDep) -> dict[str, Any]:
    matches = await role_service.latest_matches(db, user.id, container.settings)
    return await explanation_service.with_wording(db, user.id, matches)


@router.post("/matches/explain")
async def explain_matches(user: CurrentUser, container: ContainerDep, db: DbDep) -> dict[str, Any]:
    return await explanation_service.explain(
        db, container.llm, container.knowledge, container.settings, user_id=user.id
    )


@router.get("/{role_id}")
async def get_role(
    role_id: str, user: CurrentUser, container: ContainerDep, db: DbDep
) -> RoleDetailOut:
    role, match = await role_service.role_with_match(db, user.id, role_id, container.settings)
    if match is not None:
        match = await explanation_service.one_with_wording(db, user.id, match, container.settings)
    return RoleDetailOut(role=role, match=match)


@router.get("/{role_id}/market")
async def get_role_market(
    role_id: str,
    _user: CurrentUser,
    container: ContainerDep,
    db: DbDep,
    listings: Annotated[int, Query(ge=0, le=market_service.POSTINGS_PER_ROLE)] = 5,
) -> dict[str, Any]:
    return await market_service.role_market(db, role_id, container.settings, listings=listings)
