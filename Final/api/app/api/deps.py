"""Shared resources on `app.state` and the auth dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import decode_access_token
from app.infra.jev import JevClient
from app.infra.llm import GroqClient
from app.infra.models import User
from app.infra.rate_limit import AttemptLimiter
from app.rag.knowledge import Knowledge


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    login_limiter: AttemptLimiter
    llm: GroqClient
    knowledge: Knowledge
    jev: JevClient | None = None


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_db(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


async def current_user(request: Request, container: ContainerDep, db: DbDep) -> User:
    settings = container.settings
    token = request.cookies.get(settings.cookie_name)
    user_id = decode_access_token(settings, token) if token else None
    # Loaded on every request, so a deleted account is logged out at once.
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    structlog.contextvars.bind_contextvars(user_id=user.id)
    # Read by QuotaHeadersMiddleware, which adds X-Quota-* to the response.
    request.state.quota_user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(current_user)]
