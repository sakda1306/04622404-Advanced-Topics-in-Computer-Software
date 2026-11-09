"""Request and response bodies (Contract.md §2 and §3)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.clock import iso
from app.core.security import MAX_PASSWORD_BYTES
from app.infra.models import User


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _password_fits_bcrypt(value: str) -> str:
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


class RegisterRequest(_Strict):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=50)
    consent: Annotated[bool, Field(strict=True)]

    @field_validator("consent")
    @classmethod
    def _must_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("consent must be true")
        return value

    _check_password = field_validator("password")(_password_fits_bcrypt)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


class LoginRequest(_Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class DeleteAccountRequest(_Strict):
    confirm: Literal["DELETE"]


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str
    is_admin: bool

    @classmethod
    def of(cls, user: User, *, is_admin: bool) -> UserOut:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            created_at=iso(user.created_at),
            is_admin=is_admin,
        )


class UserEnvelope(BaseModel):
    user: UserOut


class Ok(BaseModel):
    ok: Literal[True] = True


class Deleted(BaseModel):
    deleted: Literal[True] = True


class CvSkillIn(_Strict):
    """Contract.md §3 `CvSkill`; `line_no` 0 = added by the user."""

    name: str = Field(min_length=1, max_length=100)
    skill_id: str | None = Field(default=None, max_length=60)
    level: int | None = Field(default=None, ge=1, le=4)
    line_no: int = Field(ge=0, le=100_000)


class EducationIn(_Strict):
    school: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=100)
    field: str | None = Field(default=None, max_length=150)
    start: str | None = Field(default=None, max_length=20)
    end: str | None = Field(default=None, max_length=20)
    line_no: int | None = Field(default=None, ge=0, le=100_000)


class ExperienceIn(_Strict):
    title: str = Field(min_length=1, max_length=150)
    company: str | None = Field(default=None, max_length=150)
    start: str | None = Field(default=None, max_length=20)
    end: str | None = Field(default=None, max_length=20)
    months: int | None = Field(default=None, ge=0, le=1200)
    summary: str | None = Field(default=None, max_length=1000)
    line_no: int | None = Field(default=None, ge=0, le=100_000)


class ConfirmCvRequest(_Strict):
    skills: list[CvSkillIn] = Field(max_length=100)
    education: list[EducationIn] = Field(max_length=20)
    experience: list[ExperienceIn] = Field(max_length=30)


class CvOut(BaseModel):
    """Contract.md §3 `CvParsed`; optional fields are left out when empty."""

    status: Literal["draft", "confirmed"]
    filename: str
    skills: list[dict[str, Any]]
    education: list[dict[str, Any]]
    experience: list[dict[str, Any]]
    warnings_th: list[str]


class CvEnvelope(BaseModel):
    cv: CvOut | None


class CvConfirmed(BaseModel):
    cv: CvOut
    completeness: dict[str, Any]


class CvDeleted(BaseModel):
    deleted: Literal[True] = True
    completeness: dict[str, Any]


class QuestionnaireOut(BaseModel):
    """Contract.md §2.3 `GET /api/questionnaire`."""

    version: str
    sections: list[dict[str, Any]]
    attribution: dict[str, Any]


class AnswersOut(BaseModel):
    answers: dict[str, Any]
    answered: int
    total: int


class AnswerRequest(_Strict):
    # Checked against the question by domain.questionnaire: the allowed shape depends on its type.
    value: Any


class AnswerSaved(BaseModel):
    saved: Literal[True] = True
    completeness: dict[str, Any]


class ChatRequest(_Strict):
    message: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    message_id: str
    answer: str
    route: str
    sources: list[dict[str, Any]] = []
    edit_proposal: dict[str, Any] | None = None
    completeness: dict[str, Any]
    tokens_used: int


class ChatMessageOut(BaseModel):
    message_id: str
    role: str
    text: str
    route: str | None
    sources: list[dict[str, Any]] = []
    created_at: str


class ChatHistoryOut(BaseModel):
    messages: list[ChatMessageOut]


class ProfileOut(BaseModel):
    profile: dict[str, Any] | None


class ProfileGenerated(BaseModel):
    profile: dict[str, Any]
    matches: dict[str, Any]


class RolesOut(BaseModel):
    roles: list[dict[str, Any]]


class RoleDetailOut(BaseModel):
    role: dict[str, Any]
    match: dict[str, Any] | None


class QuotaOut(BaseModel):
    """Contract.md §3 `Quota`."""

    day: str
    requests_used: int
    requests_limit: int
    tokens_used: int
    tokens_limit: int
    reset_at: str
    exhausted: bool


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
