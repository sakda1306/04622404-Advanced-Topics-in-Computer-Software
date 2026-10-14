"""Tokens for BM25 and alias matching: English words + Thai words, in reading order."""

from __future__ import annotations

import numpy as np

from app.search.tokenize import tokenize
from tests.fakes import FakeEmbedder


def test_english_is_lowercased_and_kept_in_order() -> None:
    assert tokenize("Arsenal 2-1 Chelsea") == ["arsenal", "2", "1", "chelsea"]


def test_thai_is_split_into_words() -> None:
    assert tokenize("เมื่อวานปืนใหญ่ชนะไหม") == ["เมื่อวาน", "ปืนใหญ่", "ชนะ", "ไหม"]


def test_mixed_text_keeps_reading_order() -> None:
    assert tokenize("ปืนใหญ่ vs Chelsea") == ["ปืนใหญ่", "vs", "chelsea"]


def test_punctuation_only_gives_no_tokens() -> None:
    assert tokenize("?? !! — 🙂") == []


def test_fake_embedder_is_normalised_and_deterministic() -> None:
    embedder = FakeEmbedder()
    a, b, c = embedder.encode(["Arsenal beat Chelsea", "Arsenal beat Chelsea", "Spain"])
    assert a.shape == (64,)
    assert np.isclose(np.linalg.norm(a), 1.0)
    np.testing.assert_array_equal(a, b)
    assert float(a @ c) < 0.5
    assert embedder.calls == [["Arsenal beat Chelsea", "Arsenal beat Chelsea", "Spain"]]


def test_accented_latin_letters_are_folded_not_dropped() -> None:
    # The router's English rewrite usually has no accents; the knowledge base often does.
    assert tokenize("Petr Čech Müller Ødegaard Mbappé Straße") == [
        "petr",
        "cech",
        "muller",
        "odegaard",
        "mbappe",
        "strasse",
    ]
