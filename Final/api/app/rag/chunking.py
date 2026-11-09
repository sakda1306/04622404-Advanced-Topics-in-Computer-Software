"""Chunks from /data: one per "## " section, each led by its title (Design.md §6).

`## Sources` is not searched: its links become every chunk's citation data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

_HEADING = "## "
_SOURCES = "Sources"
_ROLE_SECTIONS = {"Role description": "role_description", "Learning path": "learning_path"}
_NOTES = {"work_style.md": "work_style", "soft_skills.md": "soft_skill"}


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    category: str
    role_id: str | None
    title: str
    text: str
    sources: tuple[str, ...]
    status: str = ""  # "draft" until reviewed, so an answer can say so

    def content_hash(self) -> str:
        """Changes when any field changes; an unchanged chunk is not embedded again."""
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    fields = (line.partition(":") for line in head.splitlines())
    return {key.strip(): value.strip() for key, _, value in fields}, body


def _sections(body: str) -> list[tuple[str, str]]:
    """(heading, section text) for each "## " heading, in order."""
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith(_HEADING):
            sections.append((line[len(_HEADING) :].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def _links(section: str) -> tuple[str, ...]:
    lines = (line.strip() for line in section.splitlines())
    return tuple(line[2:].strip() for line in lines if line.startswith("- "))


def _role_chunks(path: Path) -> list[Chunk]:
    fields, body = _split_front_matter(path.read_text(encoding="utf-8"))
    sections = dict(_sections(body))
    missing = [name for name in _ROLE_SECTIONS if not sections.get(name)]
    if missing or "role_id" not in fields:
        raise ValueError(f"{path.name}: missing {missing or 'role_id'}")
    role_id = fields["role_id"]
    doc_id = f"role-{role_id}"
    title = f"{fields['title_th']} ({fields['title_en']})"
    sources = _links(sections.get(_SOURCES, ""))
    return [
        Chunk(
            chunk_id=f"{doc_id}#{category}",
            doc_id=doc_id,
            category=category,
            role_id=role_id,
            title=title,
            text=f"{title}\n{name}\n{sections[name]}",
            sources=sources,
            status=fields.get("status", ""),
        )
        for name, category in _ROLE_SECTIONS.items()
    ]


def _note_chunks(path: Path, category: str) -> list[Chunk]:
    fields, body = _split_front_matter(path.read_text(encoding="utf-8"))
    first_line = next((ln for ln in body.splitlines() if ln.startswith("# ")), "")
    title = first_line[2:].strip() or path.stem
    sections = _sections(body)
    sources = _links(dict(sections).get(_SOURCES, ""))
    searched = [(heading, text) for heading, text in sections if heading != _SOURCES and text]
    return [
        Chunk(
            chunk_id=f"{path.stem}#{position}",
            doc_id=path.stem,
            category=category,
            role_id=None,
            title=title,
            text=f"{title}\n{heading}\n{text}",
            sources=sources,
            status=fields.get("status", ""),
        )
        for position, (heading, text) in enumerate(searched)
    ]


def load_chunks(data_dir: str) -> list[Chunk]:
    root = Path(data_dir)
    chunks = [c for path in sorted((root / "roles").glob("*.md")) for c in _role_chunks(path)]
    for name, category in _NOTES.items():
        path = root / "rag" / name
        if path.exists():
            chunks.extend(_note_chunks(path, category))
    return chunks
