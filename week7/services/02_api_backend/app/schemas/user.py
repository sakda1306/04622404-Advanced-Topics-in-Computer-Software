"""User, login and preferences (CONTRACT.md §1)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db import models
from app.schemas.common import Text

Role = Literal["user", "admin"]
Language = Literal["th", "en"]

# favorite_team_id is an INTEGER column.
MAX_INT32 = 2_147_483_647


class UserOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: Role
    favorite_team_id: int | None
    language: Language

    @classmethod
    def of(cls, user: models.User) -> UserOut:
        return cls(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,  # type: ignore[arg-type]
            favorite_team_id=user.favorite_team_id,
            language=user.language,  # type: ignore[arg-type]
        )


class UserEnvelope(BaseModel):
    user: UserOut


class LoginRequest(BaseModel):
    username: Text = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("กรุณากรอกชื่อที่แสดง")
        return trimmed

    @field_validator("password")
    @classmethod
    def limit_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("รหัสผ่านต้องไม่เกิน 72 ไบต์")
        return value


class PreferencesRequest(BaseModel):
    """Both fields are optional; a field that is sent (even null) is applied."""

    favorite_team_id: int | None = Field(default=None, ge=1, le=MAX_INT32)
    language: Language | None = None
