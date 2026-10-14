"""Shared resources on `app.state` and the auth dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.football import FootballDataClient, RetrievalAdminClient
from app.clients.router_client import RouterClient
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import decode_access_token
from app.db.models import User
from app.infra.store import Store


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    store: Store
    http: httpx.AsyncClient
    router: RouterClient
    football: FootballDataClient
    retrieval: RetrievalAdminClient


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_db(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def _token_from(request: Request, cookie_name: str) -> str | None:
    token = request.cookies.get(cookie_name)
    if token:
        return token
    # Bearer is accepted too, for smoke tests and curl.
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value if scheme.lower() == "bearer" and value else None


async def current_user(request: Request, container: ContainerDep, db: DbDep) -> User:
    token = _token_from(request, container.settings.cookie_name)
    claims = decode_access_token(container.settings, token) if token else None
    if claims is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    # Loaded on every request, so a role change or a disabled account applies at once.
    user = await db.get(User, claims.user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if user.disabled:
        raise AppError(ErrorCode.ACCOUNT_DISABLED)
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise AppError(ErrorCode.FORBIDDEN)
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def actor_tag(user: User) -> str:
    """`triggered_by` / `edited_by` value for 07 (CONTRACT §7)."""
    return f"admin:{user.id}"
