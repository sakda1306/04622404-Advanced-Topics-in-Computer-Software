"""Map a verified token to our user record (just-in-time provisioning, D-43)."""

from __future__ import annotations

from pydantic import SecretStr

from app.core.crypto import keyed_hash
from app.core.errors import AppError, ErrorCode
from app.core.security import Principal
from app.services.ports import RecommendationRepository, UserRef


class UserService:
    def __init__(
        self, repository: RecommendationRepository, pseudonym_secret: SecretStr | None
    ) -> None:
        self._repo = repository
        self._secret = pseudonym_secret

    async def resolve(self, principal: Principal) -> UserRef:
        # The pseudonym is what the Agent and feedback see; it cannot be reversed to the user.
        user = await self._repo.get_or_create_user(
            principal.issuer,
            principal.subject,
            pseudonym=lambda user_id: keyed_hash(self._secret, str(user_id)),
        )
        if user.deletion_requested:
            # The account is on its way out; nothing may be added to it (D-78).
            raise AppError(ErrorCode.FORBIDDEN, detail="This account is being deleted.")
        return user
