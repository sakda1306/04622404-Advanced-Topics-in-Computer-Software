from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.services.pagination import Cursor, build_page, decode_cursor, encode_cursor, page_limit

AT = datetime(2026, 9, 17, 8, 0, 0, 123456, tzinfo=UTC)


def raw(data: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def field_of(error: AppError) -> str:
    assert error.code is ErrorCode.VALIDATION_ERROR
    assert error.errors is not None
    return error.errors[0].field


def test_cursor_round_trip() -> None:
    cursor = Cursor(AT, new_id())

    encoded = encode_cursor(cursor)

    assert decode_cursor(encoded) == cursor
    assert "=" not in encoded
    assert all(c.isalnum() or c in "-_" for c in encoded)


@pytest.mark.parametrize("value", [None, ""])
def test_no_cursor(value: str | None) -> None:
    assert decode_cursor(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "not base64 !!",
        raw("just a string"),
        raw({"t": AT.isoformat()}),
        raw({"id": str(new_id())}),
        raw({"t": "yesterday", "id": str(new_id())}),
        raw({"t": "2026-09-17T08:00:00", "id": str(new_id())}),
        raw({"t": AT.isoformat(), "id": "not-a-uuid"}),
        raw({"t": 5, "id": str(new_id())}),
        "a" * 201,
    ],
)
def test_invalid_cursor_is_422(value: str) -> None:
    with pytest.raises(AppError) as info:
        decode_cursor(value)

    assert field_of(info.value) == "cursor"


def test_page_limit() -> None:
    assert page_limit(None, maximum=50) == 20
    assert page_limit(50, maximum=50) == 50
    assert page_limit(1, maximum=50) == 1


@pytest.mark.parametrize("value", [0, -1, 51])
def test_page_limit_out_of_range(value: int) -> None:
    with pytest.raises(AppError) as info:
        page_limit(value, maximum=50)

    assert field_of(info.value) == "limit"


def test_build_page_with_more_rows() -> None:
    rows = [Cursor(AT, new_id()) for _ in range(3)]

    page = build_page(rows, 2, key=lambda row: row)

    assert page.items == rows[:2]
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == rows[1]


def test_build_page_last_page() -> None:
    rows = [Cursor(AT, new_id()) for _ in range(2)]

    page = build_page(rows, 2, key=lambda row: row)

    assert page.items == rows
    assert page.next_cursor is None
