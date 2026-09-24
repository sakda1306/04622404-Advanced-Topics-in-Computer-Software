from __future__ import annotations

import pytest

from app.core.ids import accept_client_id, new_id


def test_new_id_is_uuid7_and_time_ordered() -> None:
    ids = [new_id() for _ in range(50)]

    assert all(i.version == 7 for i in ids)
    assert ids == sorted(ids)


@pytest.mark.parametrize("value", ["abc-123", "0192f0c2-aaaa-7bbb-8ccc-123456789abc", "a.b:c_d"])
def test_accepts_safe_client_ids(value: str) -> None:
    assert accept_client_id(value) == value


@pytest.mark.parametrize(
    "value",
    [None, "", "x" * 65, "has space", "line\nbreak", "<script>", "ไทย"],
)
def test_rejects_unsafe_client_ids(value: str | None) -> None:
    assert accept_client_id(value) is None
