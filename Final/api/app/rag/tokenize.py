"""Tokens for BM25, ported from Team-D-II module 05.

Thai has no spaces between words, so Thai runs are split with pythainlp. Latin words and numbers
are lower-cased, and split from Thai even when no space separates them.
"""

from __future__ import annotations

import re

from pythainlp.tokenize import word_tokenize

_THAI_RUN = r"[ก-๙]+"
_TOKEN = re.compile(rf"{_THAI_RUN}|[^\W_ก-๙]+")
_THAI = re.compile(_THAI_RUN)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN.finditer(text):
        word = match.group()
        if _THAI.fullmatch(word):
            tokens.extend(t for t in word_tokenize(word, engine="newmm") if t.strip())
        else:
            tokens.append(word.lower())
    return tokens
