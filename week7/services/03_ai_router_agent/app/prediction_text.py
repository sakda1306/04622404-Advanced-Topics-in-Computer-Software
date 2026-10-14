"""Draft answers for prediction questions, written from numbers only (no LLM)."""

from datetime import datetime

NEEDS_TEAM_TEXT = "ต้องการทำนายผลนัดระหว่างทีมไหน หรือดูโอกาสทั้งฤดูกาล (แชมป์ / ท็อป 4 / ตกชั้น)"
UNAVAILABLE_TEXT = "ตอนนี้ระบบทำนายผลไม่พร้อมใช้งาน"
TEAM_NOT_FOUND_TEXT = "ไม่พบข้อมูลของทีมนี้ในฤดูกาลปัจจุบัน"
THAI_MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
FOCUS = {
    "title": ("p_title", "โอกาสแชมป์", 5),
    "top4": ("p_top4", "โอกาสติดท็อป 4", 6),
    "relegation": ("p_relegation", "โอกาสตกชั้น", 5),
}


def percent(p: float) -> str:
    rounded = round(p * 100)
    return "<1%" if p > 0 and rounded == 0 else f"{rounded}%"


def thai_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return f"{moment.day} {THAI_MONTHS[moment.month - 1]} {moment.year + 543} {moment:%H:%M}"


def simulation_focus(query: str) -> str:
    text = query.lower()
    if "ตกชั้น" in text or "relegat" in text:
        return "relegation"
    if any(word in text for word in ("ท็อป", "top 4", "top four", "top-4")):
        return "top4"
    return "title"


def _disclaimer(as_of: str | None, n_sims: int | None = None) -> str:
    parts = []
    if n_sims:
        parts.append(f"จำลอง {n_sims:,} ครั้ง")
    when = thai_datetime(as_of)
    if when:
        parts.append(f"ข้อมูล ณ {when}")
    detail = f" ({' · '.join(parts)})" if parts else ""
    return f"ประมาณการจากแบบจำลองสถิติ{detail} ไม่ใช่คำแนะนำการพนัน"


def match_prediction_text(result: dict) -> str:
    data = result.get("data") or {}
    return f"{result.get('content', '').strip()}\n\n{_disclaimer(data.get('as_of'))}"


def summarize_simulation(snapshot: dict, focus: str, team_ids: list[int]) -> str:
    teams = snapshot.get("teams") or []
    if team_ids:
        lines = []
        for team_id in team_ids:
            row = next((t for t in teams if t["team_id"] == team_id), None)
            if row is None:
                lines.append("ไม่พบทีมนี้ในผลจำลองฤดูกาลปัจจุบัน")
                continue
            lines += [
                f"{row['short_name']}: แต้มตอนนี้ {row['points']} · "
                f"แต้มที่คาดเมื่อจบฤดูกาล {round(row['expected_points'])}",
                f"โอกาสแชมป์ {percent(row['p_title'])} · ท็อป 4 {percent(row['p_top4'])} · "
                f"ตกชั้น {percent(row['p_relegation'])}",
            ]
    else:
        key, label, limit = FOCUS.get(focus, FOCUS["title"])
        ranked = sorted(teams, key=lambda t: t[key], reverse=True)[:limit]
        lines = [f"{label}:"] + [
            f"{i}. {t['short_name']} {percent(t[key])}" for i, t in enumerate(ranked, 1)
        ]
    footer = _disclaimer(snapshot.get("as_of"), snapshot.get("n_sims"))
    if snapshot.get("stale"):
        footer += " · ผลนี้อาจยังไม่อัปเดตล่าสุด"
    return "\n".join(lines) + "\n\n" + footer
