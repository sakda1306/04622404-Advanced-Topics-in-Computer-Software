"""Register, login, logout, me, delete account (Contract.md §2.1)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.api.deps import Container, ContainerDep, CurrentUser, DbDep
from app.api.schemas import (
    DeleteAccountRequest,
    Deleted,
    LoginRequest,
    Ok,
    RegisterRequest,
    UserEnvelope,
    UserOut,
)
from app.core.security import create_access_token
from app.infra.models import User
from app.services.users import (
    authenticate,
    delete_account,
    is_admin,
    normalize_email,
    register_user,
)

router = APIRouter(prefix="/api", tags=["auth"])


def _set_auth_cookie(response: Response, container: Container, user_id: str) -> None:
    settings = container.settings
    response.set_cookie(
        settings.cookie_name,
        create_access_token(settings, user_id),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookie(response: Response, container: Container) -> None:
    settings = container.settings
    response.delete_cookie(
        settings.cookie_name, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )


def _user_out(user: User, container: Container) -> UserEnvelope:
    return UserEnvelope(
        user=UserOut.of(user, is_admin=is_admin(user, container.settings.admin_emails))
    )


@router.post("/auth/register")
async def register(
    body: RegisterRequest, response: Response, container: ContainerDep, db: DbDep
) -> UserEnvelope:
    user = await register_user(
        db, email=body.email, password=body.password, display_name=body.display_name
    )
    _set_auth_cookie(response, container, user.id)
    return _user_out(user, container)


@router.post("/auth/login")
async def login(
    body: LoginRequest, response: Response, container: ContainerDep, db: DbDep
) -> UserEnvelope:
    limiter = container.login_limiter
    key = normalize_email(body.email)
    limiter.acquire(key)  # counted before the first await, so parallel attempts count too
    user = await authenticate(db, email=body.email, password=body.password)
    limiter.succeed(key)
    _set_auth_cookie(response, container, user.id)
    return _user_out(user, container)


@router.post("/auth/logout")
async def logout(response: Response, container: ContainerDep) -> Ok:
    _clear_auth_cookie(response, container)
    return Ok()


@router.get("/auth/me")
async def me(user: CurrentUser, container: ContainerDep) -> UserEnvelope:
    return _user_out(user, container)


@router.delete("/me")
async def delete_me(
    body: DeleteAccountRequest,
    request: Request,
    user: CurrentUser,
    response: Response,
    container: ContainerDep,
    db: DbDep,
) -> Deleted:
    del body  # validated by the schema: confirm must be "DELETE"
    await delete_account(db, user)
    request.state.quota_user_id = None  # the account is gone: no quota headers
    _clear_auth_cookie(response, container)
    return Deleted()
