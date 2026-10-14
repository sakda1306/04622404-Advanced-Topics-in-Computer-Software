"""User management (Could): list, change role, disable. Admins cannot change themselves."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbDep
from app.schemas.admin import AdminUser as AdminUserOut
from app.schemas.admin import UserPatch
from app.schemas.common import Page, Text
from app.services import users as user_service

router = APIRouter(prefix="/users")


@router.get("")
async def list_users(
    db: DbDep,
    q: Annotated[Text | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[AdminUserOut]:
    return await user_service.list_users(db, q=q, limit=limit, cursor=cursor)


@router.patch("/{user_id}")
async def update_user(user_id: UUID, body: UserPatch, db: DbDep, admin: AdminUser) -> AdminUserOut:
    return await user_service.update_user(db, admin, user_id, body)
