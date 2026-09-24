"""API contract for /v1/me (docs/02_api_spec.md section 7.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.profile import ConsentChanges, ProfileChanges
from app.services.ports import ProfileRecord


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nulls(model: BaseModel, prefix: str = "") -> set[str]:
    return {f"{prefix}{name}" for name in model.model_fields_set if getattr(model, name) is None}


class ConsentsView(_Strict):
    live_alerts: bool
    analytics: bool


class MeResponse(_Strict):
    user_id: UUID
    display_name: str | None
    email_masked: str | None
    language: str
    timezone: str
    home_region: str | None
    consents: ConsentsView
    created_at: datetime

    @classmethod
    def from_record(cls, record: ProfileRecord, email_masked: str | None) -> MeResponse:
        profile = record.profile
        return cls(
            user_id=record.user_id,
            display_name=profile.display_name,
            email_masked=email_masked,
            language=profile.language,
            timezone=profile.timezone,
            home_region=profile.home_region,
            consents=ConsentsView(
                live_alerts=profile.consents.live_alerts, analytics=profile.consents.analytics
            ),
            created_at=record.created_at,
        )


class ConsentsPatch(_Strict):
    live_alerts: bool | None = None
    analytics: bool | None = None


class MePatch(_Strict):
    """JSON Merge Patch of the profile; `null` clears optional fields (D-76)."""

    # Hard caps for parsing; the business limits are checked in the domain.
    display_name: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=35)
    timezone: str | None = Field(default=None, max_length=64)
    home_region: str | None = Field(default=None, max_length=10)
    consents: ConsentsPatch | None = None

    def to_domain(self) -> ProfileChanges:
        nulls = _nulls(self)
        if self.consents is not None:
            nulls |= _nulls(self.consents, "consents.")
        return ProfileChanges(
            display_name=self.display_name,
            language=self.language,
            timezone=self.timezone,
            home_region=self.home_region,
            consents=(
                ConsentChanges(
                    live_alerts=self.consents.live_alerts, analytics=self.consents.analytics
                )
                if self.consents
                else None
            ),
            explicit_nulls=frozenset(nulls),
        )


class DeletionAccepted(_Strict):
    status: Literal["deleting"] = "deleting"
