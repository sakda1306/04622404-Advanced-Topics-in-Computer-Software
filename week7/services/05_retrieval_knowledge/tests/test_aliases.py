"""Team nicknames -> official names for the BM25 query (week5 #1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.search.aliases import AliasIndex, load_alias_file, parse_teams
from tests.conftest import TEST_DATA

ARSENAL = {"Arsenal", "Arsenal FC"}
UNITED = {"Man United", "Manchester United FC"}
LIVERPOOL = {"Liverpool", "Liverpool FC"}
CITY = {"Man City", "Manchester City FC"}
SPURS = {"Tottenham", "Tottenham Hotspur FC"}


@pytest.fixture(scope="module")
def aliases() -> AliasIndex:
    return load_alias_file(str(TEST_DATA / "team_aliases.json"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("เมื่อวานปืนใหญ่ชนะไหม", ARSENAL),
        ("ผีชนะไหม", UNITED),
        ("แมนยูแพ้", UNITED),
        ("ผีแดงชนะ", UNITED),
        ("หงส์แดงเจอผี", LIVERPOOL | UNITED),
        ("เรือใบถล่มไก่เดือยทอง", CITY | SPURS),
        ("Did the gunners win?", ARSENAL),
        ("SPURS lost again", SPURS),
        ("ปืนใหญ่ หรือ ปืน", ARSENAL),
    ],
)
def test_nicknames_expand_to_official_names(
    aliases: AliasIndex, text: str, expected: set[str]
) -> None:
    assert set(aliases.expand(text)) == expected


@pytest.mark.parametrize("text", ["ผีเสื้อบินได้", "spursy weather", "Arsenal 2-1 Chelsea", ""])
def test_no_false_matches(aliases: AliasIndex, text: str) -> None:
    # "ผีเสื้อ" (butterfly) must not become Manchester United.
    assert aliases.expand(text) == []


def test_several_texts_and_no_duplicate_names(aliases: AliasIndex) -> None:
    names = aliases.expand("gunners vs man city", None, "ปืนใหญ่เจอเรือใบ")
    assert set(names) == ARSENAL | CITY
    assert len(names) == len(set(names))


def test_missing_file_gives_an_empty_index(tmp_path: Path) -> None:
    index = load_alias_file(str(tmp_path / "missing.json"))
    assert index.team_count == 0
    assert index.expand("ปืนใหญ่") == []


def test_bundled_fallback_file_covers_twenty_teams() -> None:
    path = Path(__file__).parents[1] / "data" / "team_aliases.json"
    teams = parse_teams(json.loads(path.read_text(encoding="utf-8")))
    assert len(teams) == 20
    assert len({t.team_id for t in teams}) == 20
    assert all(t.aliases and t.names for t in teams)
