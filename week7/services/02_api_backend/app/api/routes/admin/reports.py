"""Weekly report review (Should): draft -> published -> unpublished, stored in 07."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import AdminUser, ContainerDep, DbDep, actor_tag
from app.core.errors import AppError, ErrorCode
from app.schemas.admin import ReportPatch
from app.services.audit import write_audit

router = APIRouter(prefix="/reports")

SeasonPath = Annotated[str, Path(pattern=r"^\d{4}$")]
MatchweekPath = Annotated[int, Path(ge=1, le=38)]


def report_target(season: str, matchweek: int) -> str:
    return f"weekly-{season}-mw{matchweek:02d}"


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "title": report.get("title"),
        "markdown_chars": len(report.get("markdown") or ""),
    }


@router.get("")
async def list_reports(
    container: ContainerDep,
    status: Literal["draft", "published", "unpublished"] | None = None,
    season: Annotated[str | None, Query(pattern=r"^\d{4}$")] = None,
) -> Any:
    return await container.football.reports(status, season)


@router.get("/{season}/{matchweek}")
async def get_report(season: SeasonPath, matchweek: MatchweekPath, container: ContainerDep) -> Any:
    return await container.football.report(season, matchweek)


@router.patch("/{season}/{matchweek}")
async def edit_report(
    season: SeasonPath,
    matchweek: MatchweekPath,
    body: ReportPatch,
    container: ContainerDep,
    db: DbDep,
    admin: AdminUser,
) -> Any:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise AppError(ErrorCode.VALIDATION_ERROR, detail="ต้องส่ง title หรือ markdown อย่างน้อยหนึ่งช่อง")
    before = await container.football.report(season, matchweek)
    if before.get("status") == "published":
        raise AppError(ErrorCode.REPORT_NOT_EDITABLE)
    after = await container.football.edit_report(season, matchweek, changes, actor_tag(admin))
    await write_audit(
        db,
        admin,
        "report.edit",
        report_target(season, matchweek),
        before=_summary(before),
        after=_summary(after),
    )
    return after


async def _change_status(
    action: Literal["publish", "unpublish"],
    season: str,
    matchweek: int,
    container: ContainerDep,
    db: DbDep,
    admin: AdminUser,
) -> Any:
    before = await container.football.report(season, matchweek)
    if action == "publish":
        after = await container.football.publish_report(season, matchweek, actor_tag(admin))
    else:
        after = await container.football.unpublish_report(season, matchweek, actor_tag(admin))
    await write_audit(
        db,
        admin,
        f"report.{action}",
        report_target(season, matchweek),
        before={"status": before.get("status")},
        after={"status": after.get("status")},
    )
    return after


@router.post("/{season}/{matchweek}/publish")
async def publish_report(
    season: SeasonPath,
    matchweek: MatchweekPath,
    container: ContainerDep,
    db: DbDep,
    admin: AdminUser,
) -> Any:
    return await _change_status("publish", season, matchweek, container, db, admin)


@router.post("/{season}/{matchweek}/unpublish")
async def unpublish_report(
    season: SeasonPath,
    matchweek: MatchweekPath,
    container: ContainerDep,
    db: DbDep,
    admin: AdminUser,
) -> Any:
    return await _change_status("unpublish", season, matchweek, container, db, admin)
