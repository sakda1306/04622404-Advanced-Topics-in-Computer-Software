"""Trivia ingest at container start: first run fills the KB, later runs change nothing."""

from __future__ import annotations

from pathlib import Path

from scripts.ingest_trivia import ingest
from tests.conftest import make_settings
from tests.fakes import FakeEmbedder
from tests.test_trivia import SAMPLE


async def test_first_ingest_loads_the_cleaned_entries(tmp_path: Path) -> None:
    trivia = tmp_path / "trivia.txt"
    trivia.write_text(SAMPLE, encoding="utf-8")
    settings = make_settings(tmp_path, trivia_file=str(trivia))
    result = await ingest(settings, FakeEmbedder())
    assert (result.parsed, result.kept) == (6, 2)
    assert result.duplicates == [2, 6]
    assert result.conflicts == [[3, 4]]
    assert result.index_version is not None


async def test_second_ingest_embeds_nothing(tmp_path: Path) -> None:
    trivia = tmp_path / "trivia.txt"
    trivia.write_text(SAMPLE, encoding="utf-8")
    settings = make_settings(tmp_path, trivia_file=str(trivia))
    first = await ingest(settings, FakeEmbedder())
    embedder = FakeEmbedder()
    second = await ingest(settings, embedder)
    assert second.index_version == first.index_version
    assert embedder.calls == []


async def test_ingest_adds_the_thai_nickname_entries(tmp_path: Path) -> None:
    trivia = tmp_path / "trivia.txt"
    trivia.write_text(SAMPLE, encoding="utf-8")
    nicknames = tmp_path / "nicknames.txt"
    nicknames.write_text(
        "[หมวด: Premier League Club Nicknames]\n"
        "Q: Which Premier League club do Thai fans call ผีแดง, and why?\n"
        "A: Manchester United. ผีแดง means Red Devils.\n",
        encoding="utf-8",
    )
    settings = make_settings(tmp_path, trivia_file=str(trivia), nickname_file=str(nicknames))
    result = await ingest(settings, FakeEmbedder())
    assert (result.kept, result.nicknames) == (2, 1)
    embedder = FakeEmbedder()
    await ingest(settings, embedder)
    assert embedder.calls == []
