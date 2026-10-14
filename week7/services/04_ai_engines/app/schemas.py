from typing import Literal, Optional
from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GeneralRequest(BaseModel):
    """Body ของ POST /general — ตรงกับ CONTRACT.md §3 เป๊ะ ห้ามเปลี่ยนชื่อ field"""

    request_id: str
    query: str
    history: list[HistoryMessage] = Field(default_factory=list)
    language: Literal["th", "en"] = "th"


class ClassifyRequest(BaseModel):
    """Body ของ POST /local/classify — CONTRACT.md §3"""

    request_id: str
    text: str


class StrengthIn(BaseModel):
    """ความแข็งของทีมจาก 07 — ประตูได้ / เสียเฉลี่ยต่อนัด (CONTRACT v1.7 §3)"""

    attack: float = Field(ge=0)
    defense: float = Field(ge=0)
    matches_used: int = Field(ge=0)


class PredictRequest(BaseModel):
    """Body ของ POST /local/predict — CONTRACT.md §3 (v1.7 เพิ่ม field optional)"""

    request_id: str
    home_team_id: int
    away_team_id: int
    season: str
    home_strength: Optional[StrengthIn] = None
    away_strength: Optional[StrengthIn] = None
    league_avg_goals: Optional[float] = Field(default=None, gt=0)
    home_name: Optional[str] = None
    away_name: Optional[str] = None


class TokenUsage(BaseModel):
    input: int
    output: int


class EngineResult(BaseModel):
    """Response ร่วมของ /general, /local/classify, /local/predict — CONTRACT.md §3"""

    engine: Literal["general_ai", "local_ai"]
    content: str
    data: Optional[dict] = None
    sources: list = Field(default_factory=list)
    model: str
    latency_ms: int
    token_usage: TokenUsage


class ProblemDetail(BaseModel):
    """Error shape ร่วมทุก service — CONTRACT.md §0 (Problem-JSON)"""

    type: str
    title: str
    status: int
    code: str
    detail: str
    service: str = "engines"
    request_id: str


class SimTableRow(BaseModel):
    team_id: int
    name: str
    points: int
    goal_difference: int
    goals_for: int
    played: int


class SimMatch(BaseModel):
    match_id: str
    home_team_id: int
    away_team_id: int


class SimInputs(BaseModel):
    season: str
    as_of: Optional[str] = None
    table: list[SimTableRow]
    remaining: list[SimMatch] = Field(default_factory=list)
    strengths: dict[str, StrengthIn]
    league_avg_goals: float = Field(gt=0)
    relegation_places: int = Field(default=3, ge=0, le=6)


class SimulateRequest(BaseModel):
    """Body ของ POST /local/simulate — CONTRACT v1.7 §3 (ผู้เรียก: football-data)"""

    request_id: str
    inputs: SimInputs
    n_sims: int = Field(default=10000, ge=1000, le=20000)
    seed: Optional[int] = None
