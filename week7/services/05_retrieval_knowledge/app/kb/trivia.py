"""The trivia knowledge base (football_trivia_qa.txt) cleaned before indexing (week5 #2).

File format, one entry per block, blocks separated by a blank line:

    [หมวด: <topic>]
    Q: <question>
    A: <answer>

- doc_id = trivia-NNNN from the entry's position in the file, so ids stay stable
- same question + same answer -> keep the first entry
- same question + different answers -> drop the whole group: nobody can tell which is right
Answers are compared without accents and word order: "Petr Cech" = "Petr Čech".
"""

from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.kb.documents import Document

_HEADER = re.compile(r"\[หมวด:\s*(.+?)\]")
_PUNCTUATION = str.maketrans("", "", string.punctuation)
TITLE_CHARS = 120


@dataclass(frozen=True, slots=True)
class TriviaEntry:
    number: int
    topic: str
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class DedupeReport:
    parsed: int
    kept: list[TriviaEntry]
    duplicates: list[int]
    conflicts: list[list[int]]


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_trivia(raw: str) -> list[TriviaEntry]:
    entries: list[TriviaEntry] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        header = _HEADER.match(lines[0])
        if not header or not lines[1].startswith("Q:") or not lines[2].startswith("A:"):
            continue
        question, answer = _clean(lines[1][2:]), _clean(lines[2][2:])
        if question and answer:
            entries.append(TriviaEntry(len(entries) + 1, header.group(1).strip(), question, answer))
    return entries


def fold(text: str) -> str:
    """Comparison key: lower case, no accents, no punctuation, single spaces (English text)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().translate(_PUNCTUATION).split())


def dedupe(entries: list[TriviaEntry]) -> DedupeReport:
    groups: dict[str, list[TriviaEntry]] = {}
    for entry in entries:
        groups.setdefault(fold(entry.question), []).append(entry)

    kept: list[TriviaEntry] = []
    duplicates: list[int] = []
    conflicts: list[list[int]] = []
    for group in groups.values():
        answers = {frozenset(fold(e.answer).split()) for e in group}
        if len(answers) > 1:
            conflicts.append([e.number for e in group])
            continue
        kept.append(group[0])
        duplicates.extend(e.number for e in group[1:])
    kept.sort(key=lambda e: e.number)
    return DedupeReport(len(entries), kept, sorted(duplicates), conflicts)


def to_document(entry: TriviaEntry) -> Document:
    return Document(
        doc_id=f"trivia-{entry.number:04d}",
        title=entry.question[:TITLE_CHARS],
        category="trivia",
        origin="kb",
        text=f"Q: {entry.question}\nA: {entry.answer}",
        topic=entry.topic,
    )


def load_trivia_documents(
    path: str | Path, *, first_number: int = 1
) -> tuple[list[Document], DedupeReport]:
    entries = parse_trivia(Path(path).read_text(encoding="utf-8"))
    if first_number != 1:
        entries = [
            TriviaEntry(e.number + first_number - 1, e.topic, e.question, e.answer) for e in entries
        ]
    report = dedupe(entries)
    return [to_document(e) for e in report.kept], report


# The Thai nickname entries (thai_nicknames_qa.txt) are numbered after the trivia file
# (trivia-0001..1996) so their ids keep the trivia-NNNN form of CONTRACT §doc_id. They live
# in their own file so the trivia golden set, sampled from football_trivia_qa.txt, stays as is.
NICKNAME_FIRST_NUMBER = 2001


def load_nickname_documents(path: str | Path) -> tuple[list[Document], DedupeReport]:
    return load_trivia_documents(path, first_number=NICKNAME_FIRST_NUMBER)
