"""Accounts: register, authenticate, delete (FR-26)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.errors import AppError, ErrorCode
from app.core.security import DUMMY_HASH, hash_password_async, verify_password_async
from app.infra.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_admin(user: User, admin_emails: list[str]) -> bool:
    """Contract v0.3d: an admin is an account whose email is in ADMIN_EMAILS."""
    return user.email in admin_emails


async def register_user(db: AsyncSession, *, email: str, password: str, display_name: str) -> User:
    email = normalize_email(email)
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AppError(ErrorCode.EMAIL_TAKEN)
    user = User(
        email=email,
        password_hash=await hash_password_async(password),
        display_name=display_name,
        consent_at=utcnow(),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:  # two registrations with the same email at once
        await db.rollback()
        raise AppError(ErrorCode.EMAIL_TAKEN) from exc
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == normalize_email(email)))
    # Always run bcrypt, so an unknown email takes as long as a wrong password.
    valid = await verify_password_async(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        raise AppError(ErrorCode.INVALID_CREDENTIALS)
    return user


async def delete_account(db: AsyncSession, user: User) -> None:
    # Child tables cascade from users.id (see app/infra/models.py).
    await db.delete(user)
    await db.commit()
