"""/api/football/* — read-only pass-through to 07 football-data (CONTRACT §1, §7)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import ContainerDep, CurrentUser
from app.core.errors import AppError, ErrorCode

router = APIRouter(prefix="/api/football", tags=["football"])

Season = Annotated[str | None, Query(pattern=r"^\d{4}$")]
Matchweek = Annotated[int | None, Query(ge=1, le=38)]
MatchStatus = Literal["SCHEDULED", "LIVE", "FINISHED", "POSTPONED", "CANCELLED"]
TeamId = Annotated[int, Query(ge=1)]


@router.get("/standings")
async def standings(container: ContainerDep, _user: CurrentUser, season: Season = None) -> Any:
    return await container.football.standings(season)


@router.get("/fixtures")
async def fixtures(
    container: ContainerDep,
    _user: CurrentUser,
    season: Season = None,
    matchweek: Matchweek = None,
    team_id: Annotated[int | None, Query(ge=1)] = None,
    status: MatchStatus | None = None,
) -> Any:
    return await container.football.fixtures(
        season=season, matchweek=matchweek, team_id=team_id, status=status
    )


@router.get("/matches/{match_id}")
async def match(
    container: ContainerDep,
    _user: CurrentUser,
    match_id: Annotated[str, Path(max_length=64, pattern=r"^[A-Za-z0-9-]+$")],
) -> Any:
    return await container.football.match(match_id)


@router.get("/predict")
async def predict(
    container: ContainerDep, _user: CurrentUser, home_team_id: TeamId, away_team_id: TeamId
) -> Any:
    if home_team_id == away_team_id:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, detail="home_team_id และ away_team_id ต้องเป็นคนละทีม"
        )
    return await container.football.prediction(home_team_id, away_team_id)


@router.get("/simulation")
async def simulation(container: ContainerDep, _user: CurrentUser, season: Season = None) -> Any:
    return await container.football.simulation(season)


@router.get("/reports/weekly")
async def weekly_report(
    container: ContainerDep, _user: CurrentUser, season: Season = None, matchweek: Matchweek = None
) -> Any:
    # 07 returns only `published` reports on this path.
    return await container.football.published_report(season, matchweek)


@router.get("/status")
async def status(container: ContainerDep, _user: CurrentUser) -> dict[str, Any]:
    data = await container.football.status()
    return {
        "current_season": data.get("current_season"),
        "current_matchweek": data.get("current_matchweek"),
        "last_ingest_at": data.get("last_ingest_at"),
        "quota": data.get("quota"),
    }
