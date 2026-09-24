from __future__ import annotations

import pytest

from app.domain.sanitizer import clean_text, safe_url, strip_internal, truncate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello  ", "hello"),
        ("line1\r\nline2\rline3", "line1\nline2\nline3"),
        ("tab\tok", "tab\tok"),
        ("bell\x07null\x00esc\x1b", "bellnullesc"),
        ("rtl‮override​zero", "rtloverridezero"),
        ("é", "é"),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_clean_text(raw: str | None, expected: str | None) -> None:
    assert clean_text(raw) == expected


def test_truncate_keeps_short_text_and_cuts_long_text() -> None:
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdef", 4) == "abc…"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.tmd.go.th/warn?id=1", "https://www.tmd.go.th/warn?id=1"),
        (" https://example.org ", "https://example.org"),
        ("http://example.org", None),
        ("javascript:alert(1)", None),
        ("data:text/html;base64,xx", None),
        ("https://user:pw@example.org", None),
        ("https:///no-host", None),
        ("ftp://example.org", None),
        ("https://example.org/" + "a" * 2100, None),
        ("https://[::1", None),  # malformed IPv6 must not raise
        ("https://exa mple.org", None),
        ("https://example.org:99999/x", None),
        ("https://example.org:8443/x", "https://example.org:8443/x"),
        ("", None),
        (None, None),
    ],
)
def test_safe_url(raw: str | None, expected: str | None) -> None:
    assert safe_url(raw) == expected


def test_strip_internal_removes_internal_fields_at_any_depth() -> None:
    payload = {
        "summary": "ok",
        "diagnostics": {"trace_id": "t"},
        "prompt": "system prompt",
        "_debug": 1,
        "internal_score": 3,
        "routes": {
            "primary": {"route_id": "r1", "cost": 12, "legs": [{"mode": "BUS", "trace": "x"}]}
        },
    }

    assert strip_internal(payload) == {
        "summary": "ok",
        "routes": {"primary": {"route_id": "r1", "legs": [{"mode": "BUS"}]}},
    }


def test_strip_internal_does_not_modify_the_input() -> None:
    payload = {"a": {"diagnostics": 1}}

    strip_internal(payload)

    assert payload == {"a": {"diagnostics": 1}}
