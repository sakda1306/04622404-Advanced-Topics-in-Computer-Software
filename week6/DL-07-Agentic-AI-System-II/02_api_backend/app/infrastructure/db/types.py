"""Column types that transform values on the way in and out (D-81)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Dialect, Text
from sqlalchemy.types import TypeDecorator

from app.core.encryption import column_cipher


class EncryptedText(TypeDecorator[str]):
    """TEXT that stores AES-GCM ciphertext; the column name is bound to every value."""

    impl = Text
    cache_ok = True

    def __init__(self, column: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.column = column

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return column_cipher().encrypt(value, column=self.column)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return column_cipher().decrypt(value, column=self.column)
