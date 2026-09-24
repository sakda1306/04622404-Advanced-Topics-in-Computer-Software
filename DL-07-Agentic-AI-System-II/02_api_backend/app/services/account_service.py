"""Second phase of account deletion, run by the `delete_account` task (D-79)."""

from __future__ import annotations

from uuid import UUID

from app.core.logging import get_logger
from app.domain.enums import ActorType, AuditResult
from app.services.ports import (
    AuditEntry,
    AuditPort,
    ExportRepository,
    ObjectStorePort,
    UserRepository,
)

log = get_logger(__name__)


class AccountService:
    def __init__(
        self,
        *,
        users: UserRepository,
        audit: AuditPort,
        exports: ExportRepository | None = None,
        store: ObjectStorePort | None = None,
    ) -> None:
        self._users = users
        self._audit = audit
        self._exports = exports
        self._store = store

    async def delete(self, user_id: UUID, *, correlation_id: str) -> bool:
        """Delete the user's rows; False when they are already gone (safe to run twice)."""
        files = await self._exports.object_keys(user_id) if self._exports else []
        pseudonym = await self._users.delete_account(user_id)
        await self._delete_files(files)
        if pseudonym is None:
            log.info("account_already_deleted")
            return False
        # The audit row names the pseudonym, never the login subject (data design 6.2).
        await self._audit.write(
            AuditEntry(
                actor_type=ActorType.SYSTEM,
                actor_ref=pseudonym,
                action="user.delete",
                target_type=None,
                target_id=None,
                result=AuditResult.SUCCESS,
                correlation_id=correlation_id,
                ip_hash=None,
                metadata={},
            )
        )
        log.info("account_deleted")
        return True

    async def _delete_files(self, keys: list[str]) -> None:
        # Export files live outside the database, so the cascade does not reach them.
        if self._store is None:
            return
        for key in keys:
            try:
                await self._store.delete(key)
            except Exception as exc:  # expired files are also removed by the purge job
                log.warning("export_file_delete_failed", error_type=type(exc).__name__)
