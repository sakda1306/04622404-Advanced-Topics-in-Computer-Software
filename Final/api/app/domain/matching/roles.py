"""The 26 role profiles from `data/roles/` (PRD FR-18, Design.md §6)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_SECTION = re.compile(r"^## (.+)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Requirement:
    skills: tuple[str, ...]  # one skill, or an any_of group where one is enough
    min_level: int
    weight: int


@dataclass(frozen=True, slots=True)
class RoleProfile:
    role_id: str
    title_th: str
    title_en: str
    career_stage: str
    required: list[Requirement]
    nice_to_have: tuple[str, ...]
    soft_skills: tuple[str, ...]
    work_style: dict[str, float]
    description_th: str
    learning_path_th: str
    author: str
    reviewer: str
    status: str
    sources: list[dict[str, Any]]


def _sections(markdown: str) -> dict[str, str]:
    parts = _SECTION.split(markdown)
    return {
        heading.strip(): text.strip()
        for heading, text in zip(parts[1::2], parts[2::2], strict=True)
    }


def _load_role(folder: Path, role_id: str) -> RoleProfile:
    raw = json.loads((folder / f"{role_id}.json").read_text(encoding="utf-8"))
    sections = _sections((folder / f"{role_id}.md").read_text(encoding="utf-8"))
    return RoleProfile(
        role_id=raw["role_id"],
        title_th=raw["title_th"],
        title_en=raw["title_en"],
        career_stage=raw["career_stage"],
        required=[
            Requirement(
                skills=tuple(item.get("any_of") or [item["skill_id"]]),
                min_level=item["min_level"],
                weight=item["weight"],
            )
            for item in raw["required"]
        ],
        nice_to_have=tuple(raw["nice_to_have"]),
        soft_skills=tuple(raw["soft_skills"]),
        work_style=raw["work_style"],
        description_th=sections["Role description"],
        learning_path_th=sections["Learning path"],
        author=raw["author"],
        reviewer=raw["reviewer"],
        status=raw["status"],
        sources=raw["sources"],
    )


@lru_cache
def load_catalogue(data_dir: str) -> tuple[RoleProfile, ...]:
    """In the order of `data/roles.json`."""
    root = Path(data_dir)
    listed = json.loads((root / "roles.json").read_text(encoding="utf-8"))
    return tuple(_load_role(root / "roles", row["id"]) for row in listed)
