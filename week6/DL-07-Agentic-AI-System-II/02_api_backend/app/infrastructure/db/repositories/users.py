"""The user's profile, consents and account deletion (docs/03_data_design.md 3.1, 6.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.profile import Consents, Profile
from app.infrastructure.db.models import FeedbackModel, JobModel, TripModel, UserModel
from app.services.ports import ProfileRecord

DELETED_PSEUDONYM = "deleted"


def _record(row: UserModel) -> ProfileRecord:
    return ProfileRecord(
        user_id=row.id,
        profile=Profile(
            display_name=row.display_name,
            language=row.language,
            timezone=row.timezone,
            home_region=row.home_region,
            consents=Consents(
                live_alerts=row.consent_live_alerts,
                live_alerts_at=row.consent_live_alerts_at,
                analytics=row.consent_analytics,
                analytics_at=row.consent_analytics_at,
            ),
        ),
        created_at=row.created_at,
    )


class SqlUserRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def profile(self, user_id: UUID) -> ProfileRecord | None:
        async with self._sessions() as session:
            row = await session.get(UserModel, user_id)
            return _record(row) if row is not None else None

    async def update_profile(
        self, user_id: UUID, profile: Profile, *, now: datetime
    ) -> ProfileRecord | None:
        async with self._sessions() as session, session.begin():
            row = await session.get(UserModel, user_id, with_for_update=True)
            if row is None:
                return None
            row.display_name = profile.display_name
            row.language = profile.language
            row.timezone = profile.timezone
            row.home_region = profile.home_region
            consents = profile.consents
            row.consent_live_alerts = consents.live_alerts
            row.consent_live_alerts_at = consents.live_alerts_at
            row.consent_analytics = consents.analytics
            row.consent_analytics_at = consents.analytics_at
            row.updated_at = now
            if not consents.live_alerts:
                # Withdrawing the consent stops live alerts on every trip (D-77).
                await session.execute(
                    update(TripModel)
                    .where(TripModel.user_id == user_id, TripModel.alerts_enabled)
                    .values(alerts_enabled=False, alerts_consent_at=None, updated_at=now)
                )
            return _record(row)

    async def request_deletion(self, user_id: UUID, *, now: datetime) -> bool:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(UserModel)
                .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
                .values(deleted_at=now, updated_at=now)
                .returning(UserModel.id)
            )
            return result.scalar_one_or_none() is not None

    async def recent_job_ids(self, user_id: UUID, *, since: datetime) -> list[UUID]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(JobModel.id)
                .where(JobModel.user_id == user_id, JobModel.created_at >= since)
                .order_by(JobModel.created_at)
            )
            return list(rows.all())

    async def delete_account(self, user_id: UUID) -> str | None:
        async with self._sessions() as session, session.begin():
            pseudonym = await session.scalar(
                select(UserModel.pseudonymous_id).where(UserModel.id == user_id).with_for_update()
            )
            if pseudonym is None:
                return None
            # Feedback outlives the account without anything that points back to it.
            await session.execute(
                update(FeedbackModel)
                .where(FeedbackModel.pseudonymous_id == pseudonym)
                .values(comment=None, pseudonymous_id=DELETED_PSEUDONYM)
            )
            # Conversations, messages, trips, requests, recommendations and jobs cascade.
            await session.execute(delete(UserModel).where(UserModel.id == user_id))
            return pseudonym

    async def pending_deletions(self, *, older_than: datetime, limit: int) -> list[UUID]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(UserModel.id)
                .where(UserModel.deleted_at.is_not(None), UserModel.deleted_at < older_than)
                .order_by(UserModel.deleted_at)
                .limit(limit)
            )
            return list(rows.all())
