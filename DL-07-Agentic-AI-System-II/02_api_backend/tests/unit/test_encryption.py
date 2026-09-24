from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.encryption import ColumnCipher, EncryptionError, parse_keys

KEY_A = base64.b64encode(b"a" * 32).decode()
KEY_B = base64.b64encode(b"b" * 32).decode()


def cipher(raw: str = f"k2:{KEY_B},k1:{KEY_A}") -> ColumnCipher:
    return ColumnCipher.from_secret(SecretStr(raw))


def test_round_trip_and_format() -> None:
    sealed = cipher().encrypt("ถนนปิด", column="feedback.comment")

    assert sealed.startswith("enc:v1:k2:")
    assert "ถนน" not in sealed
    assert cipher().decrypt(sealed, column="feedback.comment") == "ถนนปิด"


def test_each_value_gets_a_new_nonce() -> None:
    first = cipher().encrypt("same", column="c")
    second = cipher().encrypt("same", column="c")
    assert first != second


def test_value_is_bound_to_its_column() -> None:
    sealed = cipher().encrypt("secret", column="messages.content")
    with pytest.raises(EncryptionError):
        cipher().decrypt(sealed, column="feedback.comment")


def test_tampered_value_is_rejected() -> None:
    sealed = cipher().encrypt("secret", column="c")
    broken = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")
    with pytest.raises(EncryptionError):
        cipher().decrypt(broken, column="c")
    with pytest.raises(EncryptionError):
        cipher().decrypt("enc:v1:k2:not base64!", column="c")


def test_rotation_reads_old_keys_and_writes_the_active_one() -> None:
    old = cipher(f"k1:{KEY_A}").encrypt("before rotation", column="c")
    rotated = cipher()

    assert rotated.decrypt(old, column="c") == "before rotation"
    assert rotated.encrypt("after", column="c").startswith("enc:v1:k2:")
    with pytest.raises(EncryptionError):
        cipher(f"k3:{KEY_B}").decrypt(old, column="c")


def test_plaintext_from_before_encryption_is_returned_as_is() -> None:
    assert cipher().decrypt("written in 5.8", column="c") == "written in 5.8"


def test_dev_key_without_configuration() -> None:
    dev = ColumnCipher.from_secret(None)
    assert dev.decrypt(dev.encrypt("x", column="c"), column="c") == "x"
    assert dev.encrypt("x", column="c").startswith("enc:v1:dev:")


@pytest.mark.parametrize(
    "raw",
    [
        "no-separator",
        f"bad-id!:{KEY_A}",
        "k1:not-base64!!",
        f"k1:{base64.b64encode(b'short').decode()}",
        f"k1:{KEY_A},k1:{KEY_B}",
    ],
)
def test_bad_key_lists_are_refused(raw: str) -> None:
    with pytest.raises(ValueError, match="key"):
        parse_keys(raw)


def test_settings_validate_the_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMN_ENCRYPTION_KEYS", "broken")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("COLUMN_ENCRYPTION_KEYS", f"k1:{KEY_A}")
    assert Settings().secrets.column_encryption_keys is not None


def test_production_needs_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("DEV_JWT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("PSEUDONYM_SECRET", "p" * 32)
    monkeypatch.setenv("IP_HASH_SECRET", "i" * 32)
    monkeypatch.setenv("JWKS_URL", "https://idp.example/jwks")
    with pytest.raises(ValidationError, match="COLUMN_ENCRYPTION_KEYS"):
        Settings()
    monkeypatch.setenv("COLUMN_ENCRYPTION_KEYS", f"k1:{KEY_A}")
    assert Settings().secrets.column_encryption_keys is not None
