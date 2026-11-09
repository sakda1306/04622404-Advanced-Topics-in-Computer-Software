"""Role catalogue and match results (Contract.md §2.6).

Matches are worked out from the saved profile on each read: it is cheap, uses no LLM or quota, and
cannot go out of step with the profile or a changed role file.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.domain.matching.roles import RoleProfile, load_catalogue
from app.domain.matching.scoring import match_list, score_role
from app.domain.matching.skills import SkillTaxonomy
from app.services import cv_service, profile_service


def catalogue(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "role_id": role.role_id,
            "title_th": role.title_th,
            "title_en": role.title_en,
            "summary_th": role.description_th.splitlines()[0],
            "career_stage": role.career_stage,
        }
        for role in load_catalogue(settings.data_dir)
    ]


def matches_for(profile: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return match_list(
        load_catalogue(settings.data_dir),
        profile,
        taxonomy=cv_service.taxonomy_for(settings),
        threshold=settings.match_threshold,
        top_n=settings.top_n_roles,
    )


async def latest_matches(db: AsyncSession, user_id: str, settings: Settings) -> dict[str, Any]:
    profile = await profile_service.get_profile(db, user_id)
    if profile is None:
        raise AppError(ErrorCode.PROFILE_NOT_FOUND)
    return matches_for(profile, settings)


def _detail(role: RoleProfile, taxonomy: SkillTaxonomy) -> dict[str, Any]:
    def named(skill_ids: tuple[str, ...]) -> list[dict[str, Any]]:
        out = []
        for skill_id in skill_ids:
            known = taxonomy.get(skill_id)
            out.append({"skill_id": skill_id, "name_th": known.name_th if known else skill_id})
        return out

    return {
        "role_id": role.role_id,
        "title_th": role.title_th,
        "title_en": role.title_en,
        "description_th": role.description_th,
        "career_stage": role.career_stage,
        "required": [
            {"skills": named(need.skills), "min_level": need.min_level, "weight": need.weight}
            for need in role.required
        ],
        "nice_to_have": named(role.nice_to_have),
        "soft_skills": named(role.soft_skills),
        "learning_path_th": role.learning_path_th,
        "author": role.author,
        "reviewer": role.reviewer,
        "status": role.status,
        "sources": role.sources,
    }


async def role_with_match(
    db: AsyncSession, user_id: str, role_id: str, settings: Settings
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    role = next((r for r in load_catalogue(settings.data_dir) if r.role_id == role_id), None)
    if role is None:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    taxonomy = cv_service.taxonomy_for(settings)
    profile = await profile_service.get_profile(db, user_id)
    match = score_role(role, profile, taxonomy) if profile is not None else None
    return _detail(role, taxonomy), match
