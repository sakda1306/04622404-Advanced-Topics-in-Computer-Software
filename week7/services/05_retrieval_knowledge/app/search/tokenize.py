"""Tokens for BM25 and alias matching (from week4 src/hybrid_retriever.py).

Latin words and numbers are lower-cased and folded to plain letters ("Čech" -> "cech",
"Ødegaard" -> "odegaard"), because the router's English rewrite rarely carries accents
while the knowledge base often does. Thai runs are split into words with pythainlp,
because Thai has no spaces between words; they are not folded, since Thai vowel and tone
marks carry meaning. Tokens keep their reading order, which alias matching relies on.
"""

from __future__ import annotations

import re
import unicodedata

from pythainlp.tokenize import word_tokenize

_THAI_RUN = r"[ก-๙]+"
_TOKEN = re.compile(rf"{_THAI_RUN}|[^\W_ก-๙]+")
_THAI = re.compile(_THAI_RUN)
# Letters that NFKD does not split into a base letter plus a mark.
_LATIN_EXTRA = str.maketrans({"ø": "o", "ß": "ss", "æ": "ae", "œ": "oe", "đ": "d", "ł": "l"})


def _fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).translate(_LATIN_EXTRA)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN.finditer(text):
        word = match.group()
        if _THAI.fullmatch(word):
            tokens.extend(t for t in word_tokenize(word, engine="newmm") if t.strip())
        else:
            tokens.append(_fold(word))
    return tokens
