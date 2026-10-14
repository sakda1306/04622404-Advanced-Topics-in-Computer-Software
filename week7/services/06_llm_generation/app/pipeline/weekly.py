"""POST /report/weekly หัวข้อ 12 — ลูกผสมโค้ด (ตัวเลข) + LLM (ภาษาธรรมชาติ)"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import Settings
from app.errors import AppValidationError, LLMUnavailable
from app.language import language_name
from app.llm.client import LLMClient
from app.middleware import log_event
from app.numeric_guard import check_score_mismatch
from app.schemas import (
    Match,
    Scorer,
    StandingRow,
    TokenUsage,
    WeeklyReportRequest,
    WeeklyReportResponse,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
)


def _yy(season: str) -> str:
    try:
        return str(int(season) + 1)[-2:]
    except ValueError:
        return "??"


def _title(season: str, matchweek: int, language: str) -> str:
    if language == "th":
        return f"สรุปพรีเมียร์ลีก {season}/{_yy(season)} นัดที่ {matchweek}"
    return f"Premier League {season}/{_yy(season)} Matchweek {matchweek} Round-up"


def _escape_pipe(name: str) -> str:
    return name.replace("|", "\\|")


def _has_full_score(m: Match) -> bool:
    """FINISHED แล้วต้องมีสกอร์ครบทั้งสองฝั่ง ไม่ใช่แค่ home
    เดิมเช็คแค่ m.score.home is not None ทำให้กรณี away เป็น None (ข้อมูลไม่ครบ
    จากต้นทาง) หลุดผ่านไป format ออกมาเป็น "2-None" — เพิ่มเช็ค away ด้วยทุกจุด
    """
    return (
        m.status == "FINISHED"
        and m.score is not None
        and m.score.home is not None
        and m.score.away is not None
    )


def _results_section(
    matches: list[Match], season: str, matchweek: int, language: str
) -> str:
    header = (
        f"Premier League {season}/{_yy(season)} · นัดที่ {matchweek}"
        if language == "th"
        else f"Premier League {season}/{_yy(season)} · Matchweek {matchweek}"
    )
    lines = [f"## {'ผลการแข่งขัน' if language == 'th' else 'Results'}", "", header, ""]
    for m in matches:
        home, away = _escape_pipe(m.home.name), _escape_pipe(m.away.name)
        if _has_full_score(m):
            lines.append(f"- {home} {m.score.home}-{m.score.away} {away}")
        elif m.status == "FINISHED":
            lines.append(
                f"- {home} vs {away} — "
                f"{'ข้อมูลสกอร์ไม่ครบ' if language == 'th' else 'Score data incomplete'}"
            )
        elif m.status == "POSTPONED":
            lines.append(
                f"- {home} vs {away} — {'เลื่อนการแข่งขัน' if language == 'th' else 'Postponed'}"
            )
        elif m.status == "CANCELLED":
            lines.append(
                f"- {home} vs {away} — {'ยกเลิก' if language == 'th' else 'Cancelled'}"
            )
        elif m.status == "SCHEDULED":
            lines.append(
                f"- {home} vs {away} — {'ยังไม่แข่ง' if language == 'th' else 'Scheduled'} ({m.kickoff})"
            )
        else:
            lines.append(f"- {home} vs {away} — {m.status}")
    return "\n".join(lines)


def _standings_section(
    standings: list[StandingRow], season: str, matchweek: int, language: str
) -> str:
    if not standings:
        return ""
    header = (
        f"Premier League {season}/{_yy(season)} · นัดที่ {matchweek}"
        if language == "th"
        else f"Premier League {season}/{_yy(season)} · Matchweek {matchweek}"
    )
    lines = [f"## {'ตารางคะแนน' if language == 'th' else 'Standings'}", "", header, ""]
    lines.append(
        "| # | ทีม | P | W | D | L | GF | GA | GD | Pts |"
        if language == "th"
        else "| # | Team | P | W | D | L | GF | GA | GD | Pts |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in sorted(standings, key=lambda r: r.position):
        name = _escape_pipe(row.name)
        lines.append(
            f"| {row.position} | {name} | {row.played} | {row.won} | {row.draw} | {row.lost} | "
            f"{row.goals_for} | {row.goals_against} | {row.goal_difference} | {row.points} |"
        )
    return "\n".join(lines)


def _scorers_section(
    scorers: list[Scorer], season: str, matchweek: int, language: str
) -> str:
    if not scorers:
        return ""
    header = (
        f"Premier League {season}/{_yy(season)} · นัดที่ {matchweek}"
        if language == "th"
        else f"Premier League {season}/{_yy(season)} · Matchweek {matchweek}"
    )
    lines = [f"## {'ดาวซัลโว' if language == 'th' else 'Top Scorers'}", "", header, ""]
    lines.append(
        "| ผู้เล่น | ประตู | แอสซิสต์ |"
        if language == "th"
        else "| Player | Goals | Assists |"
    )
    lines.append("|---|---|---|")
    # 07 sends assists=None when football-data.org did not report them; never show that as 0.
    unreported = "ไม่มีข้อมูล" if language == "th" else "not reported"
    for s in sorted(scorers, key=lambda s: -s.goals)[:10]:
        assists = unreported if s.assists is None else s.assists
        lines.append(f"| {_escape_pipe(s.player)} | {s.goals} | {assists} |")
    return "\n".join(lines)


def _fallback_highlights(
    matches: list[Match],
    standings: list[StandingRow],
    scorers: list[Scorer],
    language: str,
) -> list[str]:
    """สร้าง highlights แบบ template จากข้อมูลด้วยโค้ด เมื่อ LLM/guard ล้มเหลว"""
    out = []
    finished = [m for m in matches if _has_full_score(m)]
    if finished:
        biggest = max(
            finished, key=lambda m: abs((m.score.home or 0) - (m.score.away or 0))
        )
        if language == "th":
            out.append(
                f"{biggest.home.name} พบ {biggest.away.name} จบด้วยสกอร์ {biggest.score.home}-{biggest.score.away}"
            )
        else:
            out.append(
                f"{biggest.home.name} {biggest.score.home}-{biggest.score.away} {biggest.away.name}"
            )
    if standings:
        top = min(standings, key=lambda r: r.position)
        out.append(
            f"{top.name} อยู่อันดับ {top.position} ด้วย {top.points} แต้ม"
            if language == "th"
            else f"{top.name} lead the table with {top.points} points"
        )
    if scorers:
        best = max(scorers, key=lambda s: s.goals)
        out.append(
            f"{best.player} ทำประตูสูงสุด {best.goals} ประตู"
            if language == "th"
            else f"{best.player} tops the scoring charts with {best.goals} goals"
        )
    return out or (
        ["ไม่มีไฮไลต์สำหรับสัปดาห์นี้"]
        if language == "th"
        else ["No highlights available this week"]
    )


def _parse_llm_json(text: str) -> dict | None:
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def run_weekly_report(
    req: WeeklyReportRequest,
    *,
    llm: LLMClient,
    settings: Settings,
    request_id: str,
) -> WeeklyReportResponse:
    start = time.monotonic()
    language = req.language if req.language in ("th", "en") else "th"

    if not req.matches:
        raise AppValidationError("matches ต้องไม่ว่าง")

    for m in req.matches:
        if m.season != req.season or m.matchweek != req.matchweek:
            log_event("weekly_mismatch", request_id, match_id=m.match_id)

    results_md = _results_section(req.matches, req.season, req.matchweek, language)
    standings_md = _standings_section(
        req.standings, req.season, req.matchweek, language
    )
    scorers_md = _scorers_section(req.top_scorers, req.season, req.matchweek, language)

    known_scores: set[tuple[int, int]] = set()
    for m in req.matches:
        if _has_full_score(m):
            known_scores.add((m.score.home, m.score.away))

    slim_data = {
        "season": req.season,
        "matchweek": req.matchweek,
        "matches": [
            {
                "home": m.home.name,
                "away": m.away.name,
                "status": m.status,
                "score": {"home": m.score.home, "away": m.score.away}
                if m.score
                else None,
                "events": [
                    {
                        "minute": e.minute,
                        "type": e.type,
                        "player": e.player,
                        "assist": e.assist,
                    }
                    for e in m.events
                ]
                if m.detail_source == "api-football"
                else [],
            }
            for m in req.matches
        ],
        "standings_top5": [
            {"position": r.position, "name": r.name, "points": r.points}
            for r in sorted(req.standings, key=lambda r: r.position)[:5]
        ],
        "top_scorers": [
            {"player": s.player, "goals": s.goals} for s in req.top_scorers[:5]
        ],
    }

    prompt = _env.get_template("weekly_report.j2").render(
        language_name=language_name(language),
        data_json=json.dumps(slim_data, ensure_ascii=False),
    )
    messages = [{"role": "user", "content": prompt}]

    intro = ""
    highlights: list[str] = []
    model_used = "none"
    token_usage = TokenUsage()

    remaining = settings.report_deadline_s - (time.monotonic() - start)

    # เดิมไม่ครอบ try/except เลย ถ้า provider หลักและสำรองล่มพร้อมกัน
    # LLMUnavailable จะหลุดออกไปให้ error handler ตอบ 503 ทั้งที่ผลบอล/ตาราง/
    # ดาวซัลโว สร้างได้อยู่แล้วจากโค้ดล้วน ๆ (ไม่ต้องพึ่ง LLM) และมี
    # _fallback_highlights() เตรียมไว้ใช้อยู่แล้วสำหรับกรณีนี้โดยเฉพาะ
    # จับ LLMUnavailable ตรงนี้แล้วใช้ fallback highlights แทน เพื่อให้รายงาน
    # ยังส่งได้ (แค่ไม่มี LLM-generated highlights) แทนที่จะตอบ 503 ทั้งที่มีข้อมูล
    try:
        result = await llm.chat(
            messages,
            temperature=settings.temperature_report,
            max_tokens=settings.report_max_output_tokens,
            deadline=remaining,
            purpose="report_highlights",
        )
    except LLMUnavailable:
        log_event(
            "llm_unavailable_fallback",
            request_id,
            where="weekly_report",
        )
        highlights = _fallback_highlights(
            req.matches, req.standings, req.top_scorers, language
        )
    else:
        parsed = _parse_llm_json(result.text)
        if parsed and isinstance(parsed.get("highlights"), list):
            candidate_highlights = [str(h)[:120] for h in parsed["highlights"]][:6]
            candidate_text = (
                " ".join(candidate_highlights) + " " + str(parsed.get("intro", ""))
            )
            mismatches = check_score_mismatch(candidate_text, known_scores)
            if mismatches:
                log_event(
                    "numeric_guard_failed",
                    request_id,
                    mismatches=str(mismatches),
                    where="weekly_report",
                )
                highlights = _fallback_highlights(
                    req.matches, req.standings, req.top_scorers, language
                )
            else:
                highlights = candidate_highlights
                intro = str(parsed.get("intro", ""))[:300]
                model_used = result.model
                token_usage = TokenUsage(
                    input=result.usage.input, output=result.usage.output
                )
        else:
            log_event("report_llm_parse_failed", request_id)
            highlights = _fallback_highlights(
                req.matches, req.standings, req.top_scorers, language
            )

    highlights_header = (
        f"Premier League {req.season}/{_yy(req.season)} · นัดที่ {req.matchweek}"
        if language == "th"
        else f"Premier League {req.season}/{_yy(req.season)} · Matchweek {req.matchweek}"
    )
    highlights_title = "ไฮไลต์" if language == "th" else "Highlights"
    highlights_lines = [f"## {highlights_title}", "", highlights_header, ""]
    if intro:
        highlights_lines.append(intro)
        highlights_lines.append("")
    for h in highlights:
        highlights_lines.append(f"- {h}")
    highlights_md = "\n".join(highlights_lines)

    sections = [results_md, highlights_md]
    if standings_md:
        sections.append(standings_md)
    if scorers_md:
        sections.append(scorers_md)
    markdown = "\n\n".join(sections)

    return WeeklyReportResponse(
        request_id=request_id,
        title=_title(req.season, req.matchweek, language),
        markdown=markdown,
        highlights=highlights,
        model=model_used,
        latency_ms=int((time.monotonic() - start) * 1000),
        token_usage=token_usage,
    )
