"""Login, preferences and admin user management."""

from __future__ import annotations

import uuid

from sqlalchemy import Subquery, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, utcnow
from app.core.errors import AppError, ErrorCode
from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.db.models import Message, User
from app.response_log.cursor import before_cursor, encode_cursor
from app.schemas.admin import AdminUser, UserPatch
from app.schemas.common import Page
from app.schemas.user import RegisterRequest
from app.services.audit import write_audit


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.username == username.strip().lower()))
    # The hash is checked even for unknown users so both paths take the same time.
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        raise AppError(ErrorCode.UNAUTHENTICATED, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if user.disabled:
        raise AppError(ErrorCode.ACCOUNT_DISABLED)
    user.last_login_at = utcnow()
    await db.commit()
    return user


async def register_user(db: AsyncSession, body: RegisterRequest) -> User:
    if await db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise AppError(ErrorCode.USERNAME_TAKEN)
    user = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="user",
        disabled=False,
        language="th",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(ErrorCode.USERNAME_TAKEN) from exc
    return user


def _admin_user(user: User, message_count: int) -> AdminUser:
    return AdminUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,  # type: ignore[arg-type]
        disabled=user.disabled,
        created_at=iso(user.created_at) or "",
        last_login_at=iso(user.last_login_at),
        message_count=message_count,
    )


def _message_counts() -> Subquery:
    return (
        select(Message.user_id, func.count().label("n"))
        .where(Message.role == "user")
        .group_by(Message.user_id)
        .subquery()
    )


async def list_users(
    db: AsyncSession, *, q: str | None, limit: int, cursor: str | None
) -> Page[AdminUser]:
    counts = _message_counts()
    query = (
        select(User, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.user_id == User.id)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit + 1)
    )
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.username).like(pattern), func.lower(User.display_name).like(pattern)
            )
        )
    after = before_cursor(cursor, User.created_at, User.id, uuid.UUID)
    if after is not None:
        query = query.where(after)
    rows = (await db.execute(query)).all()
    items = [_admin_user(user, count) for user, count in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = encode_cursor(last.created_at, last.id)
    return Page[AdminUser](items=items, next_cursor=next_cursor)


async def update_user(
    db: AsyncSession, actor: User, user_id: uuid.UUID, patch: UserPatch
) -> AdminUser:
    if user_id == actor.id:
        raise AppError(ErrorCode.CANNOT_MODIFY_SELF)
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.NOT_FOUND)
    before = {"role": user.role, "disabled": user.disabled}
    if patch.role is not None:
        user.role = patch.role
    if patch.disabled is not None:
        user.disabled = patch.disabled
    after = {"role": user.role, "disabled": user.disabled}
    # Committed together with the audit entry.
    await write_audit(db, actor, "user.update", str(user.id), before=before, after=after)
    count = await db.scalar(
        select(func.count()).where(Message.user_id == user.id, Message.role == "user")
    )
    return _admin_user(user, count or 0)
