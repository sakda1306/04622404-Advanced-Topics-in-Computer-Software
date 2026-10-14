"""Pydantic v2 schemas ตาม CONTRACT.md v1.1 หัวข้อ 4"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    """รับแบบหลวม (extra=allow) ส่งกลับตามที่รับมา ห้ามทำหายหรือแปลงชื่อ field"""

    model_config = ConfigDict(extra="allow")

    ref: int
    doc_id: str | None = None
    title: str | None = None
    category: str | None = None
    origin: str | None = None
    season: str | None = None
    matchweek: int | None = None
    team_ids: list[int] | None = None
    fetched_at: str | None = None
    url: str | None = None


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    content: str


class Context(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: int
    text: str
    source: Source


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str | None = None
    mode: Literal["grounded", "passthrough"]
    query: str = ""
    language: str = "th"
    contexts: list[Context] = Field(default_factory=list)
    scope_team_ids: list[int] = Field(default_factory=list)
    draft: str | None = None
    history: list[HistoryMessage] = Field(default_factory=list)


class SafetyInfo(BaseModel):
    blocked: bool = False
    reason: str | None = None


class GenerateResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[Source] = Field(default_factory=list)
    citations_removed: int = 0
    safety: SafetyInfo
    model: str
    latency_ms: int
    token_usage: TokenUsage


# --- /report/weekly ---


class TeamRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    team_id: int
    name: str


class HalfTime(BaseModel):
    home: int | None = None
    away: int | None = None


class Score(BaseModel):
    home: int | None = None
    away: int | None = None
    half_time: HalfTime | None = None


class MatchEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    minute: int | None = None
    type: str
    team_id: int | None = None
    player: str | None = None
    assist: str | None = None


class Match(BaseModel):
    model_config = ConfigDict(extra="allow")

    match_id: str
    external_ids: dict | None = None
    season: str
    matchweek: int
    kickoff: str
    status: Literal["SCHEDULED", "LIVE", "FINISHED", "POSTPONED", "CANCELLED"]
    home: TeamRef
    away: TeamRef
    score: Score | None = None
    events: list[MatchEvent] = Field(default_factory=list)
    # 07 (api-football) ส่ง lineups/statistics เป็น list เสมอ ส่วนแหล่งอื่นอาจส่งเป็น dict
    # หรือไม่ส่งเลย (None) — รับแบบหลวมตามกติกาหัวข้อ 4 แล้วส่งต่อ/ใช้งานตามที่มาจริง
    # ห้าม normalize/ทำหายเพื่อไม่ให้ขัดกับรูปแบบที่ 07 ส่งจริง
    lineups: dict | list | None = None
    statistics: dict | list | None = None
    fetched_at: str | None = None
    detail_source: str = "none"


class StandingRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    position: int
    team_id: int
    name: str
    played: int
    won: int
    draw: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str | None = None


class Scorer(BaseModel):
    model_config = ConfigDict(extra="allow")

    player: str
    team_id: int
    goals: int
    assists: int | None = None


class WeeklyReportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str | None = None
    season: str
    matchweek: int
    language: str = "th"
    matches: list[Match]
    standings: list[StandingRow] = Field(default_factory=list)
    top_scorers: list[Scorer] = Field(default_factory=list)


class WeeklyReportResponse(BaseModel):
    request_id: str
    title: str
    markdown: str
    highlights: list[str] = Field(default_factory=list)
    model: str
    latency_ms: int
    token_usage: TokenUsage
