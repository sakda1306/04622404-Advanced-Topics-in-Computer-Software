from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.core.crypto import keyed_hash
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.core.security import Principal
from app.services.ports import UserRef
from app.services.user_service import UserService


class FakeRepository:
    def __init__(self, *, deleting: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.deleting = deleting

    async def get_or_create_user(
        self, issuer: str, subject: str, *, pseudonym: Callable[[UUID], str]
    ) -> UserRef:
        self.calls.append((issuer, subject))
        user_id = new_id()
        return UserRef(user_id, pseudonym(user_id), "th", None, deletion_requested=self.deleting)


async def test_principal_is_mapped_to_a_pseudonymous_user() -> None:
    repo = FakeRepository()
    secret = SecretStr("s" * 32)
    principal = Principal(
        subject="alice",
        issuer="https://idp",
        scopes=frozenset(),
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        email="alice@example.org",
    )

    user = await UserService(repo, secret).resolve(principal)  # type: ignore[arg-type]

    assert repo.calls == [("https://idp", "alice")]
    assert user.pseudonymous_id == keyed_hash(secret, str(user.id))
    assert "alice" not in user.pseudonymous_id


async def test_a_user_being_deleted_is_refused() -> None:
    principal = Principal(
        subject="bob",
        issuer="https://idp",
        scopes=frozenset(),
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    service = UserService(FakeRepository(deleting=True), None)  # type: ignore[arg-type]

    with pytest.raises(AppError) as info:
        await service.resolve(principal)

    assert info.value.code is ErrorCode.FORBIDDEN
    assert info.value.detail == "This account is being deleted."
