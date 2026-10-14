"""Build eval/golden_trivia.jsonl from the cleaned trivia file (week5 #5). Same output every run.

    python -m scripts.build_golden

Fixes the defects week5 found in the week4 generator:
- the size is exact (largest remainder), not `size // categories` questions per category
- categories keep their share of the knowledge base, so a score reflects real traffic
- `partial` lower-cases before dropping stopwords, so it keeps the topic, not "Who ..."
- answers are trivia doc_ids, not week4 chunk numbers that did not match entry numbers
- `slang` covers more terms; questions with none of them simply have no slang variant
"""

from __future__ import annotations

import json
import math
import random
import re
import zlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.kb.chunking import split_qa
from app.kb.documents import Document
from app.kb.trivia import load_trivia_documents

SERVICE = Path(__file__).parents[1]
TRIVIA_FILE = SERVICE / "data" / "football_trivia_qa.txt"
GOLDEN_FILE = SERVICE.parents[1] / "eval" / "golden_trivia.jsonl"
SIZE = 60
SEED = 42
PARTIAL_WORDS = 6

STOPWORDS = frozenset(
    "a an and are as at be been by did do does ever for from had has have he her his how "  # noqa: SIM905
    "i in is it its many most of on only or she that the their this to was were what when "
    "where which who whom whose why with you".split()
)

# Formal term -> how fans type it. Longest first so "UEFA Champions League" wins.
SLANG: tuple[tuple[str, str], ...] = (
    ("UEFA European Championship", "Euros"),
    ("UEFA Champions League", "UCL"),
    ("English Premier League", "EPL"),
    ("European Championship", "Euros"),
    ("Manchester United", "Man Utd"),
    ("Manchester City", "Man City"),
    ("Tottenham Hotspur", "Spurs"),
    ("Champions League", "UCL"),
    ("FIFA World Cup", "World Cup"),
    ("Premier League", "Prem"),
    ("national team", "national side"),
    ("goalkeeper", "keeper"),
    ("footballer", "player"),
    ("referee", "ref"),
    ("manager", "gaffer"),
    ("scored", "netted"),
    ("football", "footy"),
)
_SLANG = [
    (re.compile(rf"\b{re.escape(formal)}\b", re.IGNORECASE), casual) for formal, casual in SLANG
]

NATURAL = (
    "hey do you know {q}",
    "quick question {q}",
    "{q} any idea",
    "can you tell me {q}",
    "i was wondering {q}",
    "{q}",
)


def allocate(counts: Counter[str], size: int) -> dict[str, int]:
    """Largest remainder: shares proportional to `counts` that add up to exactly `size`."""
    total = sum(counts.values())
    quotas = {key: size * n / total for key, n in counts.items()}
    shares = {key: math.floor(q) for key, q in quotas.items()}
    by_remainder = sorted(quotas, key=lambda key: (-(quotas[key] - shares[key]), key))
    for key in by_remainder[: size - sum(shares.values())]:
        shares[key] += 1
    return shares


def make_partial(question: str) -> str:
    """A keyword query: the content words of the question, in order."""
    without_brackets = re.sub(r"\(.*?\)", " ", question)
    words = re.findall(r"[a-z0-9'-]+", without_brackets.lower())
    content = [w for w in words if w not in STOPWORDS and len(w) > 1]
    return " ".join(content[:PARTIAL_WORDS])


def make_slang(question: str) -> str | None:
    slang = question
    for pattern, casual in _SLANG:
        slang = pattern.sub(casual, slang)
    return slang if slang != question else None


def make_natural(question: str, *, seed_text: str) -> str:
    """How someone types in a chat box: lower case, no question mark, a filler around it."""
    core = " ".join(question.rstrip("?").lower().split())
    template = NATURAL[zlib.crc32(seed_text.encode()) % len(NATURAL)]
    return template.format(q=core)


def build_items(documents: Sequence[Document], *, size: int, seed: int) -> list[dict[str, Any]]:
    by_topic: dict[str, list[Document]] = {}
    for document in documents:
        by_topic.setdefault(document.topic or "", []).append(document)
    shares = allocate(Counter({t: len(docs) for t, docs in by_topic.items()}), size)

    rng = random.Random(seed)  # noqa: S311 - a repeatable sample, not a secret
    chosen: list[Document] = []
    for topic in sorted(by_topic):
        chosen += rng.sample(sorted(by_topic[topic], key=lambda d: d.doc_id), shares[topic])

    items: list[dict[str, Any]] = []
    for document in sorted(chosen, key=lambda d: d.doc_id):
        question, answer = split_qa(document.text)
        variants = {"verbatim": question}
        slang = make_slang(question)
        if slang:
            variants["slang"] = slang
        variants["partial"] = make_partial(question)
        variants["natural"] = make_natural(question, seed_text=document.doc_id)
        items.append(
            {
                "id": f"gt-{document.doc_id}",
                "doc_id": document.doc_id,
                "category": document.topic,
                "answer": answer,
                "variants": variants,
            }
        )
    return items


def main() -> None:
    documents, _ = load_trivia_documents(str(TRIVIA_FILE))
    items = build_items(documents, size=SIZE, seed=SEED)
    GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_FILE.open("w", encoding="utf-8", newline="\n") as out:
        for item in items:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
    coverage = Counter(name for item in items for name in item["variants"])
    print(f"{len(items)} items -> {GOLDEN_FILE}")
    print("categories:", dict(Counter(item["category"] for item in items).most_common()))
    print("variants:", dict(coverage))


if __name__ == "__main__":
    main()
