import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .chat import chat_enabled, chat_kind
from .teams import TeamDirectory


INTENT_MAP = {
    "trivia_history": ("football_rag", "trivia"),
    "match_result": ("football_rag", "match_report"),
    "fixture_schedule": ("football_rag", "fixtures"),
    "standings_stats": ("football_rag", "standings"),
    "weekly_summary": ("football_rag", "weekly_report"),
    "general_football": ("general_ai", None),
    "prediction": ("local_ai", None),
    "out_of_scope": ("decline", None),
    "player_info": ("football_rag", "player"),
    "chitchat": ("chat", None),
}

# CONTRACT v1.5: the 04 classifier does not know player_info, so these rules are its main entry.
PLAYER_WORDS = ("นักเตะ", "ผู้เล่น", "สควอด", "ผู้รักษาประตู", "กองหน้า", "กองกลาง", "กองหลัง",
                "โค้ช", "ผู้จัดการทีม", "กุนซือ", "ตำแหน่งอะไร", "เล่นตำแหน่ง", "อายุเท่า", "สัญชาติ",
                "squad", "players", "who plays for", "head coach", "manager of", "coach of",
                "how old is", "nationality")
# CONTRACT v1.16: head coach documents come from Wikidata; their questions get their own search text.
COACH_WORDS_TH = ("โค้ช", "ผู้จัดการทีม", "กุนซือ", "เฮดโค้ช", "ผู้ฝึกสอน")
COACH_WORDS_EN = re.compile(r"\b(?:head coach|coach(?:es|ed)?|manager)\b")
NOT_COACH_WORDS = ("general manager", "manager of the month", "assistant", "ผู้ช่วย", "goalkeeper coach",
                   "goalkeeping coach", "fitness coach", "kit manager", "youth", "academy",
                   "manager of the season", "โค้ชผู้รักษาประตู", "โค้ชฟิตเนส", "โค้ชทีมเยาวชน", "เยาวชน")
# "pl" is the league only as a whole word ("players", "play" are not).
PL_ABBR = re.compile(r"(?<![a-z])pl(?![a-z])")  # also "แชมป์plปี 2016"; Python's \b counts Thai as a word
# A person's titles with a club, or the women's team, are not the club's record summary.
PERSON_TITLE = re.compile(
    r"แชมป์[^?]*กับ|สมัย[^?]*กับ|อยู่กับ[^?]*แชมป์|\b(?:titles?|trophies|won|win)\b[^?]*\bwith\b")
# "… win at Liverpool" is a person's titles; "… won at the Emirates" stays the club's own record.
PERSON_TITLE_AT = re.compile(r"\b(?:titles?|trophies|won|win)\b[^?]*\bat\b([^?]*)")
# Leagues below the Premier League: their relegations are not the Premier League record.
OTHER_LEAGUE_WORDS = ("แชมเปียนชิพ", "league one", "league two", "ลีกวัน", "ลีกทู")
OTHER_LEAGUE_EN = re.compile(r"\bchampionship\b")  # singular: "championships" are titles
WOMEN_TEAM = re.compile(r"หญิง|\bwomen\b")
# A two-club comparison also reads "แชมป์…กับ" in Thai (no spaces); it stays a club record question.
COMPARISON_WORDS = ("ระหว่าง", "เทียบกับ", "compared with", "compared to")
# Calendar years without a top-flight season to end or begin in them.
WAR_YEARS = {
    **{year: ("1915/16–1918/19", "First World War") for year in (1916, 1917, 1918)},
    **{year: ("1939/40–1945/46", "Second World War") for year in range(1940, 1946)},
}
# The documents hold the current coach only: a past coach is not theirs to answer.
PAST_COACH_TH = ("เคย", "อดีต", "คนก่อน", "ก่อนหน้า")
PAST_COACH_EN = re.compile(r"\b(?:was|were|used to|former|previous|before|when)\b")
# Goal and table questions stay with the scorer/standings rules or fall through to the LLM.
NOT_PLAYER_WORDS = ("ยิง", "ทำประตู", "กี่ประตู", "กี่ลูก", "ตาราง", "goals", "scored", "assist",
                    "table")

MATCHWEEK_PATTERN = re.compile(r"(?:นัดที่\s*|แมตช์วีค\s*|สัปดาห์ที่\s*|matchweek\s*)(\d+)")
OTHER_COMPETITIONS = ("ลาลีกา", "แชมเปียนส์ลีก", "แชมเปี้ยนส์ลีก", "ยูฟ่า",
                      "บุนเดสลีกา", "กัลโช่", "ฟุตบอลโลก", "la liga",
                      "champions league", "serie a", "bundesliga", "ligue 1", "world cup")
# Whole-season outlook questions (CONTRACT v1.7): answered from 07 /football/simulation.
SEASON_PREDICTION = re.compile(
    r"จะ\s*(?:ได้|เป็น|คว้า)?\s*แชมป์|จะ\s*ตกชั้น|จะ\s*(?:ติด|จบ)\s*(?:ท็อป|อันดับ)|เสี่ยง\s*ตกชั้น"
    r"|(?:มี\s*)?โอกาส\s*(?:ได้\s*)?(?:แชมป์|ติดท็อป|ท็อป|ตกชั้น|จบอันดับ)"
    r"|\bwho will (?:win the (?:premier league|league|title)|be relegated|finish)\b"
    r"|\bchances? of (?:winning the (?:league|title)|(?:a )?top[- ]?(?:4|four)|relegation|being relegated)\b")
# Short follow-ups about one match ("เขายิงกี่ลูก", "who scored?") and the next one ("who do they play next?").
MATCH_GOAL_WORDS = ("ยิงกี่ลูก", "ยิงกี่ประตู", "ได้กี่ประตู", "ยิงได้กี่", "ใครทำประตู", "ใครยิง")
MATCH_RESULT_EN = re.compile(r"\bwho (?:scored|won)\b|\bdid \w+(?: \w+)? win\b|\bhow did \w+(?: \w+)? do\b")
NEXT_MATCH_EN = re.compile(r"\bnext (?:match|game|opponent)\b|\bplay next\b")
RECORD_WORDS_TH = ("มากที่สุด", "เร็วที่สุด", "สถิติ", "ตลอดกาล", "ตลอดมา", "ประวัติศาสตร์", "นัดชิง",
                   "คนแรก", "ทีมแรก", "ครั้งแรก", "ก่อนคนอื่น")
RECORD_WORDS_EN = re.compile(r"\b(?:league|title|trophy|cup|ever|record|fastest|ballon|award)\b")
# Competitions outside the Premier League. Their questions are history, and the trivia documents
# name them in English, so the search text carries the English name instead of "Premier League".
COMPETITION_TERMS = (
    ("ฟุตบอลโลก", "FIFA World Cup"), ("บอลโลก", "FIFA World Cup"), ("เวิลด์คัพ", "FIFA World Cup"),
    ("แชมเปียนส์ลีก", "UEFA Champions League European Cup"),
    ("แชมเปี้ยนส์ลีก", "UEFA Champions League European Cup"),
    ("ถ้วยยุโรป", "UEFA Champions League European Cup"),
    ("แชมป์ยุโรป", "UEFA European Championship Euro UEFA Champions League European Cup"),
    ("ยูโร", "UEFA European Championship Euro"), ("คอนเฟด", "FIFA Confederations Cup"),
    ("โคปา", "Copa America"), ("โอลิมปิก", "Olympic Games football"),
)
INTERNATIONAL_WORDS = (*(thai for thai, _ in COMPETITION_TERMS), "ทีมชาติ", "world cup", "euro",
                       "champions league", "copa america", "olympic", "national team", "confederations")
SEASON_WORDS = ("แชมป์", "ท็อปโฟร์", "ท็อป 4", "ท็อป4", "top 4", "top four", "ตกชั้น", "relegat",
                "อันดับ", "title", "finish")
# v1.11: 07's Premier League archive (past seasons and head-to-head) lives in its own category.
HISTORICAL = "historical"
HEAD_TO_HEAD_WORDS = ("เคยชนะ", "เคยเจอ", "ชนะกี่นัด", "สถิติพบกัน", "สถิติเจอกัน", "ประวัติการพบกัน",
                      "head to head", "head-to-head", "h2h")
# "เจอกันกี่ครั้ง" counts meetings; "เจอกันกี่โมง" / "ชนะกันกี่ลูก" are about one match.
HEAD_TO_HEAD_COUNT = re.compile(r"(?:เจอกัน|ชนะกัน|พบกัน)\s*กี่\s*(?:นัด|ครั้ง|หน)")
# The archive ends last season: questions about this season or one match stay with live data.
CURRENT_WORDS = ("เมื่อวาน", "วันนี้", "คืนนี้", "พรุ่งนี้", "นัดล่าสุด", "นัดก่อน", "นัดหน้า", "นัดต่อไป",
                 "ฤดูกาลนี้", "ซีซั่นนี้", "ปีนี้", "กี่โมง", "กี่ทุ่ม", "this season", "yesterday", "today",
                 "last match", "next match")
# Without a known club, a season question must name the league to be about the Premier League.
PL_WORDS = ("พรีเมียร์ลีก", "premier league", "ลีกอังกฤษ", "epl", "พรีเมียร์ชิพ")
# Former Premier League clubs the team directory does not know (no team_id in 07's archive),
# with the English name the archive documents use.
ARCHIVE_CLUBS = {
    "แบล็คเบิร์น": "Blackburn Rovers", "blackburn": "Blackburn Rovers",
    "โบลตัน": "Bolton Wanderers", "bolton": "Bolton Wanderers",
    "เลสเตอร์": "Leicester City", "leicester": "Leicester City",
    "เวสต์แฮม": "West Ham United", "west ham": "West Ham United",
    "วูล์ฟส์": "Wolverhampton Wanderers", "wolves": "Wolverhampton Wanderers",
    "เบิร์นลีย์": "Burnley", "burnley": "Burnley",
    "เซาธ์แฮมป์ตัน": "Southampton", "southampton": "Southampton",
    "มิดเดิลสโบรช์": "Middlesbrough", "middlesbrough": "Middlesbrough",
    "วัตฟอร์ด": "Watford", "watford": "Watford",
    "นอริช": "Norwich City", "norwich": "Norwich City",
    "สโต๊ค": "Stoke City", "stoke": "Stoke City",
    "สวอนซี": "Swansea City", "swansea": "Swansea City",
    "วีแกน": "Wigan Athletic", "wigan": "Wigan Athletic",
    "พอร์ทสมัธ": "Portsmouth", "portsmouth": "Portsmouth",
    "เรดดิ้ง": "Reading", "reading": "Reading",
    "ดาร์บี้": "Derby County", "derby": "Derby County",
    "เบอร์มิงแฮม": "Birmingham City", "birmingham": "Birmingham City",
    "แบล็คพูล": "Blackpool", "blackpool": "Blackpool",
    "แบรดฟอร์ด": "Bradford City", "bradford": "Bradford City",
    "คาร์ดิฟฟ์": "Cardiff City", "cardiff": "Cardiff City",
    "ชาร์ลตัน": "Charlton Athletic", "charlton": "Charlton Athletic",
    "ฮัดเดอร์สฟิลด์": "Huddersfield Town", "huddersfield": "Huddersfield Town",
    "ลูตัน": "Luton Town", "luton": "Luton Town",
    "โอลด์แฮม": "Oldham Athletic", "oldham": "Oldham Athletic",
    "คิวพีอาร์": "Queens Park Rangers", "qpr": "Queens Park Rangers",
    "เชฟฟิลด์": "Sheffield", "sheffield": "Sheffield",
    "สวินดอน": "Swindon Town", "swindon": "Swindon Town",
    "เวสต์บรอม": "West Bromwich Albion", "west brom": "West Bromwich Albion",
    "วิมเบิลดัน": "Wimbledon", "wimbledon": "Wimbledon",
    "บาร์นสลีย์": "Barnsley", "barnsley": "Barnsley",
}
ARCHIVE_CLUB_WORDS = tuple(ARCHIVE_CLUBS)
HISTORY_SEASON_WORDS = ("แชมป์", "อันดับ", "ตาราง", "ตกชั้น", "แต้ม", "คะแนน", "ผลงาน", "ชนะกี่", "แพ้กี่",
                        "เสมอกี่", "ยิงได้กี่", "ดาวซัลโว", "champion", "title", "table", "relegat", "finish",
                        "points", "who won", "winner")
# Cups are not in the league archive: a league champion must not answer a cup question.
CUP_WORDS = ("เอฟเอคัพ", "fa cup", "ลีกคัพ", "league cup", "คาราบาว", "carabao", "คอมมูนิตี้ชิลด์",
             "community shield", "บัลลงดอร์", "ballon", "คัพ", " cup", "ถ้วย", "efl", "ซีเกมส์", "sea games",
             "เอเชียน", "asian", "ไทยลีก", "thai league", "ดิวิชั่น", "division")
# All-time questions about finishes and points belong to the archive's club records, not this
# season's table (live chat test 2026-10-04: "แต้มรวมทั้งหมด" was answered with this season's 12).
TABLE_WORDS_TH = ("อันดับ", "แต้ม")
TABLE_WORDS_EN = re.compile(r"\b(?:points|finish(?:ed)?|position)\b")
# An explicit all-time marker is enough; a superlative or a total also needs the league named (and a
# finish), since "ทีมไหนแต้มต่ำสุด" or "who has the best points tally" ask about this season's table.
ALL_TIME_TH = ("ตลอดกาล", "ทุกฤดูกาล", "รวมทุก", "ประวัติศาสตร์", "เคยจบ")
ALL_TIME_EN = re.compile(r"\b(?:all[- ]time|ever|in (?:premier league )?history)\b")
SUPERLATIVE_TH = ("ดีที่สุด", "แย่ที่สุด", "สูงสุด", "ต่ำสุด")
SUPERLATIVE_EN = re.compile(r"\b(?:best|worst|highest|lowest)\b")
TOTAL_EN = re.compile(r"\btotal\b")
# A finish in Europe, the second tier or a cup group is not a Premier League record.
NOT_PL_TABLE_WORDS = ("ยุโรป", "europe", "championship", "กลุ่ม", "group")
SCORER_WORDS = ("ยิง", "ประตู", "ดาวซัลโว", "scorer", "goal")
ENGLISH_RECORD_WORDS = ("titles", "won the premier league", "premier league champions", "relegated", "relegation",
                        "runner-up", "runners-up", "most titles")
# Questions about what will happen are predictions, never the archive or a question back.
FUTURE = re.compile(r"จะ|ลุ้น|\bwill\b")
NOW_WORDS = (*CURRENT_WORDS, "ตอนนี้", "ล่าสุด", " now", "currently", "นัดนี้", "สัปดาห์นี้", "this week")
NOW_END = re.compile(r"แล้ว(?:ครับ|คะ|ค่ะ|นะ)?\s*\??\s*$")
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
SEASON_SPAN = re.compile(r"(?<!\d)\d{2,4}\s*/\s*\d{2,4}(?!\d)")
# Title questions the rules ask back about (user choice: always ask, never guess).
TITLE_WORDS_EN = re.compile(r"\b(?:champions?|titles?|won the|winners?)\b")
RANGE_TH = ("ตั้งแต่", "หลังปี", "ก่อนปี", "ระหว่างปี", "ถึงปี")
RANGE_EN = re.compile(r"\b(?:since|between|after|before)\b")
COUNT_TH = ("กี่สมัย", "กี่ครั้ง")
COUNT_EN = re.compile(r"\bhow many\b")
LEAGUE_WIDE_TH = ("ทีมไหน", "สโมสรไหน", "มากที่สุด", "กี่ทีม", "ใคร")
LEAGUE_WIDE_EN = re.compile(r"\b(?:which|who|most)\b")
OTHER_TITLE_WORDS = (*INTERNATIONAL_WORDS, *OTHER_COMPETITIONS, *CUP_WORDS)
# What a bare title question may contain. Anything else (a player, a nation, a foreign club, an award,
# "จะ") names something the question back would talk past, so the rules leave that question alone.
CLARIFY_FILLER_TH = tuple(sorted((
    "พรีเมียร์ลีก", "พรีเมียร์ชิพ", "ลีกสูงสุดอังกฤษ", "ลีกสูงสุด", "ลีกอังกฤษ", "อังกฤษ", "ลีก", "แชมป์",
    "ฤดูกาล", "ปี", "คือ", "ทีมไหน", "สโมสรไหน", "ทีมอะไร", "สโมสร", "ทีม", "ใคร", "ได้", "เป็น", "กี่สมัย",
    "กี่ครั้ง", "ครับ", "คับ", "คะ", "ค่ะ", "นะ", "ไหน", "อะไร", "ของ", "ที่", "บ้าง", "ไหม", "มั้ย", "เหรอ",
    "หรอ", "ใน", "เมื่อ"), key=len, reverse=True))
CLARIFY_FILLER_EN = re.compile(
    r"\b(?:who|won|win|wins|were|was|is|are|did|the|champions?|league|premier|epl|titles?|in|of|how|many|"
    r"has|have|which|team|club|english|top|flight|winners?|season|year)\b")
# A reply to a question back must answer it, never start another topic.
REPLY_TOPIC_WORDS = (*NOW_WORDS, "นัด", "เจอ", "ข่าว", "ผล", "ตาราง", "โปรแกรม", "แต้ม", "อันดับ", "ยิง",
                     "fixture", "news", "table", "score", "result", "points", " vs")
# Club record questions (CONTRACT v1.15): each club's record summary is searched on its own, since a
# shared search let head-to-head and season tables push the summaries out of the top five.
CLUB_RECORD_WORDS = ("แชมป์", "ตกชั้น", "อันดับ", "แต้มรวม", "กี่ฤดูกาล", "title", "champion", "runner-up",
                     "runners-up", "relegat", "finish", "points", "seasons")


def normalize_thai(text: str) -> str:
    """Users often type two sara e (เเ) where they mean sara ae (แ)."""
    return text.replace("เเ", "แ")


def season_prediction(query: str) -> bool:
    return bool(SEASON_PREDICTION.search(query.lower()))


def prediction_kind(query: str, team_ids: list[int]) -> str:
    """season = title / top 4 / relegation outlook · match = two teams · otherwise ask."""
    text = query.lower()
    if season_prediction(text):
        return "season"
    if len(team_ids) >= 2:
        return "match"
    if _has(text, SEASON_WORDS):
        return "season"
    return "needs_team"


@dataclass
class Decision:
    route: str
    intent: str | None
    layer: str
    confidence: float
    reasoning: str
    filters: dict = field(default_factory=dict)
    rewritten_query: str | None = None
    team_ids: list[int] = field(default_factory=list)
    kind: str | None = None  # route `chat` only: the kind of chit-chat (also in `reasoning`)
    clarify_text: str | None = None  # route `clarify`: the question back, in Thai
    clarify_text_en: str | None = None
    record_team_ids: list[int] = field(default_factory=list)  # CONTRACT v1.15: search each club's record


TEAM_CLARIFY = ('หมายถึงแชมป์ของทีมไหนครับ เช่น "แมนยูได้แชมป์พรีเมียร์ลีกกี่สมัย"',
                'Which club do you mean? For example: "How many Premier League titles have Manchester United won?"')
# Our own questions back, recognised in history so a short reply can join the question it answers.
CLARIFY_PREFIXES = ("หมายถึงแชมป์พรีเมียร์ลีกฤดูกาล", "หมายถึงแชมป์ลีกสูงสุดอังกฤษฤดูกาล",
                    "หมายถึงแชมป์รายการไหนครับ", "หมายถึงแชมป์ของทีมไหนครับ",
                    "Do you mean the Premier League ", "Do you mean the English top-flight ",
                    "Which competition do you mean?", "Which club do you mean?")
COMPETITION_CLARIFY_PREFIXES = ("หมายถึงแชมป์รายการไหนครับ", "Which competition do you mean?")


def team_clarify() -> tuple[str, str]:
    return TEAM_CLARIFY


def title_year_clarify(year: int, league_named: bool) -> tuple[str, str]:
    """A calendar year spans two seasons; the Premier League began in 1992/93."""
    ended, began = f"{year - 1}/{year % 100:02d}", f"{year}/{(year + 1) % 100:02d}"
    league, league_en = (("พรีเมียร์ลีก", "Premier League") if year > 1992
                         else ("ลีกสูงสุดอังกฤษ", "English top-flight"))
    if league_named:
        return (f"หมายถึงแชมป์{league}ฤดูกาล {ended} (จบปี {year}) หรือ {began} (เริ่มปี {year}) ครับ",
                f"Do you mean the {league_en} {ended} season (ended in {year}) or {began} (began in {year})?")
    return (f"หมายถึงแชมป์รายการไหนครับ ถ้าเป็น{league} ปี {year} ตรงกับฤดูกาล {ended} (จบปี {year}) "
            f"หรือ {began} (เริ่มปี {year})",
            f"Which competition do you mean? For the {league_en}, {year} covers {ended} (ended in {year}) "
            f"and {began} (began in {year}).")


def _category_filter(intent: str) -> dict:
    if intent == "trivia_history":
        return {"category": ["trivia", HISTORICAL]}
    category = INTENT_MAP[intent][1]
    return {"category": [category]} if category else {}


def classify_intent(label: str, score: float) -> Decision | None:
    if label == "chitchat" and not chat_enabled():
        label = "out_of_scope"
    if label not in INTENT_MAP or score < 0.75:
        return None
    return Decision(INTENT_MAP[label][0], label, "classifier", score, f"classifier: {label}",
                    _category_filter(label))


def from_intent(label: str, confidence: float, layer: str = "llm") -> Decision | None:
    confidence = min(1.0, max(0.0, confidence))
    if label == "clarify":
        return Decision("clarify", None, layer, confidence, "คำถามกำกวม")
    if label not in INTENT_MAP:
        return None
    decision = classify_intent(label, max(0.75, confidence))
    decision.confidence = confidence
    decision.layer = layer
    decision.reasoning = f"{layer}: {label}"
    return decision


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _has_historical_marker(text: str) -> bool:
    if _has(text, ("ตลอดกาล", "ตลอดมา", "ประวัติศาสตร์", "ย้อนหลัง", "ฤดูกาลที่แล้ว",
                   "ซีซั่นที่แล้ว", "ปีที่แล้ว", "ฤดูกาลก่อน", "ซีซั่นก่อน")):
        return True
    return bool(re.search(r"\b(?:all[- ]time|ever|in history|last season|previous season)\b", text))


def _record_question(text: str, current_season: str | None = None) -> bool:
    if (_has_historical_marker(text) or _has(text, RECORD_WORDS_TH) or RECORD_WORDS_EN.search(text)
            or _has(text, INTERNATIONAL_WORDS)):
        return True
    # A year outside the current season ("นัดชิงปี 2005") points at history, not at the latest match.
    season = str(current_season or "")
    allowed = {season, str(int(season) + 1)} if season.isdigit() else set()
    return any(year not in allowed for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text))


def _previous_season(text: str) -> bool:
    return _has(text, ("ฤดูกาลที่แล้ว", "ซีซั่นที่แล้ว", "ปีที่แล้ว", "ฤดูกาลก่อน", "ซีซั่นก่อน")) or bool(
        re.search(r"\b(?:last season|previous season)\b", text)
    )


def _top_scorer_question(text: str) -> bool:
    text = text.replace("ลีกสูงสุด", "")  # "top-flight league", not "most goals"
    return _has(text, ("ดาวซัลโว", "top scorer", "leading scorer", "golden boot")) or (
        _has(text, ("ยิง", "ทำประตู", "goals", "scored"))
        and _has(text, ("เยอะสุด", "เยอะที่สุด", "มากที่สุด", "สูงสุด", "most goals", "top scorer", "leading scorer"))
    )


def _season_in(text: str, current_season: str | None) -> tuple[str, bool] | None:
    """Read explicit season years; a bare year means its starting season."""
    full = re.search(r"(?<!\d)((?:19|20)\d{2})\s*[/\-]\s*((?:19|20)\d{2}|\d{2})(?!\d)", text)
    short = re.search(r"(?<!\d)(\d{2})\s*[/\-]\s*(\d{2})(?!\d)", text) if not full else None
    if full or short:
        match = full or short
        start = int(match.group(1)) if full else 2000 + int(match.group(1))
        if short and int(match.group(1)) >= 50:  # "98/99" is 1998/99; "27/28" stays 2027/28
            start -= 100
        end = int(match.group(2))
        if end != start + 1 and end != (start + 1) % 100:
            return None
        assumed = False
    else:
        years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
        if len(years) == 1:
            start = int(years[0])
            assumed = True
        elif not years and _previous_season(text) and str(current_season or "").isdigit():
            start = int(current_season) - 1
            assumed = False
        else:
            return None
    if str(start) == str(current_season):
        return None
    return str(start), assumed


def historical_scorer_season(query: str, current_season: str | None) -> tuple[str, bool] | None:
    """Read explicit season years; a bare year means its starting season."""
    text = query.lower()
    if not _top_scorer_question(text) or _has(text, ("ตลอดกาล", "ประวัติศาสตร์")) or re.search(
        r"\b(?:all[- ]time|ever|in history)\b", text
    ):
        return None
    return _season_in(text, current_season)


def _head_to_head(text: str) -> bool:
    return _has(text, HEAD_TO_HEAD_WORDS) or bool(HEAD_TO_HEAD_COUNT.search(text))


def _season_label(start: int) -> str:
    return f"{start}/{str(start + 1)[2:]}"


def history_filters(query: str, team_count: int, current_season: str | None) -> dict | None:
    """Questions the 07 Premier League archive answers (CONTRACT v1.11)."""
    text = query.lower()
    if _has(text, (*OTHER_COMPETITIONS, *INTERNATIONAL_WORDS, *CUP_WORDS)):
        return None
    if team_count == 2 and _head_to_head(text) and not _has(text, CURRENT_WORDS):
        return {"category": [HISTORICAL]}
    if not str(current_season or "").isdigit() or not _has(text, HISTORY_SEASON_WORDS):
        return None
    if team_count == 0 and not _has(text, (*PL_WORDS, *ARCHIVE_CLUB_WORDS)):
        return None
    season = _season_in(text, current_season)
    # Before 1992/93 the archive has nothing; trivia may still know (old First Division).
    if season is None or not 1992 <= int(season[0]) < int(current_season):
        return None
    start, assumed = season
    # A bare year may mean the season that starts or ends in it: search both, do not filter.
    return {"category": [HISTORICAL]} if assumed else {"category": [HISTORICAL], "season": start}


def league_wide_scorer_query(query: str, teams: TeamDirectory) -> bool:
    """Limit the verified winner shortcut to league player rankings."""
    text = query.lower()
    if teams.find(query) or MATCHWEEK_PATTERN.search(text) or _has(text, OTHER_COMPETITIONS):
        return False
    if _has(text, ("ทีมไหน", "สโมสรไหน", "which team", "which club", "team with most",
                   "เสียประตู", "conceded", "goals against", "ผู้รักษาประตู", "goalkeeper",
                   "เกมไหน", "นัดไหน", "ในเกม", "ในแมตช์", "which match", "which game",
                   "per match", "against",
                   "รอง", "runner-up", "second place", "อันดับสอง", "อันดับ 2",
                   "ตั้งแต่", "since", "จนถึง", "ถึง", "เดือน", "มกราคม", "กุมภาพันธ์",
                   "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
                   "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")):
        return False
    if re.search(r"\bsecond\b", text) or re.search(r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
                 r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
                 r"dec(?:ember)?)\b", text):
        return False
    return _has(text, ("ใคร", "ดาวซัลโว", "top scorer", "leading scorer", "golden boot")) or bool(
        re.search(r"\bwho\b", text)
    )


def _current_top_scorer(text: str, current_season: str | None = None) -> bool:
    if not _top_scorer_question(text) or _has_historical_marker(text) or _has(text, INTERNATIONAL_WORDS):
        return False
    if historical_scorer_season(text, current_season):
        return False
    years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
    if not years:
        return True
    if not str(current_season or "").isdigit():
        return False
    if all(year == str(current_season) for year in years):
        return True
    next_year = str(int(current_season) + 1)
    return years == [str(current_season), next_year] and bool(re.search(
        rf"(?<!\d){re.escape(str(current_season))}\s*[/\-]\s*{re.escape(next_year)}(?!\d)", text
    ))


def _intent(query: str, current_season: str | None = None) -> str | None:
    text = query.lower()
    if _has(text, OTHER_COMPETITIONS) and _top_scorer_question(text):
        return "out_of_scope"
    if _has(text, ("พนัน", "เดิมพัน", "ราคาบอล", "ทีเด็ด", "แทงบอล", "odds", "betting", "bet ")):
        return "out_of_scope"
    if _has(text, ("อากาศ", "ร้านอาหาร", "bitcoin", "โค้ด python", "เขียนเว็บ", "หุ้น")):
        return "out_of_scope"
    if _has(text, ("ทำนาย", "คาดการณ์", "พยากรณ์ผล", "predict", "who will win", "โอกาสชนะ", "จะชนะ")) or (
            season_prediction(text)):
        return "prediction"
    if _has(text, ("ใบเหลือง", "ใบแดง", "ลูกโทษ")) and _has(
            text, ("เมื่อวาน", "เมื่อคืน", "นัดล่าสุด", "นัดก่อน", "นัดที่", "แมตช์", "เกมล่าสุด", "ผลแข่ง")):
        return "match_result"
    if _has(text, ("กฎ", "ล้ำหน้า", "var ", "ใบเหลือง", "ใบแดง", "แฮนด์บอล", "ลูกโทษ", "แผนการเล่น", "free kick", "ผู้รักษาประตูใช้มือ")):
        return "general_football"
    if _has(text, ("สรุป", "ไฮไลต์", "weekly summary")) and _has(text, ("สัปดาห์", "นัด", "week", "พรีเมียร์ลีก")):
        return "weekly_summary"
    if _has(text, ("แชมป์", "บัลลงดอร์", "ประวัติ", "trivia", "history")):
        return "trivia_history"
    # English title and relegation questions decided here, not by an LLM that rewrites them differently
    # each time; "relegation zone" or "runner-up this season" is this season's table.
    if _has(text, ENGLISH_RECORD_WORDS) and not _has(
            text, (*NOW_WORDS, "zone", "candidate", "battle", "race", "table", "rule")):
        return "trivia_history"
    if _has(text, ("โปรแกรม", "เตะกับใครต่อ", "แข่งกับใครต่อ", "นัดหน้า", "เมื่อไร", "วันไหน", "fixture", "schedule",
                   "นัดต่อไป", "นัดถัดไป", "เจอใครต่อ", "เจอกับใครต่อ")) or NEXT_MATCH_EN.search(text):
        return "fixture_schedule"
    if _top_scorer_question(text):
        return "standings_stats" if _current_top_scorer(text, current_season) else "trivia_history"
    if re.search(r"\bscorers?\b", text):
        return "trivia_history" if _has_historical_marker(text) else "standings_stats"
    if _has(text, ("ตารางคะแนน", "จ่าฝูง", "อันดับ", "กี่แต้ม", "standings", "points", "top of the table",
                   "league table")):
        return "standings_stats"
    if coach_question(text):
        return "player_info"
    if (_has(text, PLAYER_WORDS) or re.search(r"\bposition\b.*\bplay", text)) and not _has(
            text, NOT_PLAYER_WORDS):
        return "player_info"
    if _has(text, MATCH_GOAL_WORDS) or MATCH_RESULT_EN.search(text):
        # "Who scored the fastest goal ever" asks for a record, not for one match.
        return "trivia_history" if _record_question(text, current_season) else "match_result"
    if _has(text, ("เมื่อวาน", "นัดล่าสุด", "นัดก่อน", "ชนะไหม", "ผลนัด", "ผลแข่ง", "จบเท่าไร", "สกอร์", "result")) or re.search(r"\bscore\b", text):
        return "match_result"
    if _has(text, ("ใครได้", "เคยได้", "ประวัติ", "กี่ครั้ง", "บัลลงดอร์", "ใครยิง", "trivia", "history")):
        return "trivia_history"
    if _has(text, INTERNATIONAL_WORDS):
        return "trivia_history"
    return None


def coach_question(text: str) -> bool:
    text = text.lower()
    if _has(text, (*NOT_COACH_WORDS, *NOT_PLAYER_WORDS, *PAST_COACH_TH)):
        return False
    if PAST_COACH_EN.search(text) or re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text):
        return False
    return _has(text, COACH_WORDS_TH) or bool(COACH_WORDS_EN.search(text))


def _competition_names(query: str) -> str:
    names = [english for thai, english in COMPETITION_TERMS if thai in query]
    return " ".join(dict.fromkeys(" ".join(names).split()))


def _rewrite(query: str, intent: str, names: list[str], filters: dict) -> str:
    if not re.search(r"[ก-๙]", query):
        return query
    def keep_question(*parts: str) -> str:
        return " ".join(part for part in (*parts, query.strip()) if part)

    teams = " ".join(names)
    if filters.get("category") == [HISTORICAL]:
        start = filters.get("season")
        # Archive documents name clubs in English; add the ones the team directory cannot.
        lowered = query.lower()
        former = [name for word, name in ARCHIVE_CLUBS.items() if word in lowered and name not in teams]
        teams = " ".join(dict.fromkeys([*names, *former]))
        # The season document opens with "Champions: …"; "standings" alone pulled table chunks instead.
        table = "champions final table" if _title_question(lowered) else "final table standings"
        if start is not None:
            return keep_question(teams, "Premier League", _season_label(int(start)), table)
        year = None if _head_to_head(query.lower()) else re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", query)
        if year is None:
            return keep_question(teams, "Premier League head-to-head record")
        end = int(year.group(1))
        return keep_question(teams, "Premier League", _season_label(end - 1), _season_label(end), table)
    season = filters.get("season", "")
    matchweek = f"matchweek {filters['matchweek']}" if "matchweek" in filters else ""
    dates = " ".join(str(filters[key]) for key in ("date_from", "date_to") if key in filters)
    if intent == "match_result":
        event = "previous match result" if "ก่อนหน้า" in query else "latest match result"
        return keep_question(teams, event, season, matchweek, dates)
    if intent == "fixture_schedule":
        return keep_question(teams, "next Premier League fixture date opponent", season, matchweek, dates)
    if intent == "standings_stats":
        topic = "top scorer" if _top_scorer_question(query.lower()) else "standings points ranking"
        return keep_question(teams, "Premier League", topic, season, matchweek)
    if intent == "weekly_summary":
        return keep_question(teams, "Premier League weekly report summary", season, matchweek, dates)
    if intent == "player_info":
        return keep_question(teams, "Premier League squad players position nationality coach", season)
    years = " ".join(re.findall(r"(?:19|20)\d{2}", query))
    if "บัลลงดอร์" in query:
        return keep_question("Ballon d'Or winner", years)
    competitions = _competition_names(query)
    if competitions:
        return keep_question(teams, competitions, years)
    # A title question about a named Premier League team; without a team the Thai text already
    # names the league and an English prefix only pulled other documents up (Thai golden set).
    if "แชมป์" in query and teams:
        return keep_question(teams, "Premier League title", "count" if "กี่ครั้ง" in query else "")
    # No generic English prefix: it pulled the same unrelated trivia to the top (Thai golden set).
    return keep_question(teams, years)


def enrich(decision: Decision, query: str, context: dict, history: list[dict], teams: TeamDirectory,
           favorite_team_id: int | None = None) -> Decision:
    found = teams.find(query)
    if not found and re.search(r"(แล้ว|นัดนั้น|เขา|ทีมไหน)", query):
        for item in reversed(history[-10:]):
            if item.get("role") == "user":
                found = teams.find(item.get("content", ""))
                if found:
                    break
    if not found and favorite_team_id and re.search(r"(ทีมโปรด|ทีมฉัน|ทีมของฉัน)", query):
        found = [team for team in teams.teams if team.team_id == favorite_team_id]
    decision.team_ids = [team.team_id for team in found]
    if decision.route == "football_rag":
        if decision.intent == "trivia_history":
            decision.rewritten_query = _rewrite(query, decision.intent,
                                                [team.short_name for team in found], decision.filters)
            return decision
        if decision.team_ids:
            decision.filters["team_ids"] = decision.team_ids
        if context.get("season"):
            decision.filters["season"] = str(context["season"])
        text = query.lower()
        now = datetime.fromisoformat(context["now"]) if context.get("now") else datetime.now().astimezone()
        if "เมื่อวาน" in text or "yesterday" in text:
            day = (now - timedelta(days=1)).date().isoformat()
            decision.filters.update(date_from=day, date_to=day)
        elif "วันนี้" in text or "today" in text:
            day = now.date().isoformat()
            decision.filters.update(date_from=day, date_to=day)
        elif "สัปดาห์นี้" in text or "this week" in text:
            monday = (now - timedelta(days=now.weekday())).date()
            decision.filters.update(date_from=monday.isoformat(), date_to=(monday + timedelta(days=6)).isoformat())
        match = MATCHWEEK_PATTERN.search(text)
        if match:
            decision.filters["matchweek"] = int(match.group(1))
        elif decision.intent in ("weekly_summary", "standings_stats") and context.get("current_matchweek") and "สัปดาห์นี้" not in text:
            decision.filters["matchweek"] = int(context["current_matchweek"])
        decision.rewritten_query = _rewrite(query, decision.intent,
                                            [team.short_name for team in found], decision.filters)
        if decision.intent == "player_info" and found and coach_question(query):
            season = decision.filters.get("season")
            label = _season_label(int(season)) if season else ""
            decision.rewritten_query = " ".join(
                part for part in (*(team.name for team in found), "head coach manager", label, query.strip()) if part)
    return decision


def all_time_table_question(text: str, team_known: bool = True) -> bool:
    text = text.replace("ลีกสูงสุด", "")  # "top-flight league", not "highest"
    if not (_has(text, TABLE_WORDS_TH) or TABLE_WORDS_EN.search(text)) or _has(text, SCORER_WORDS):
        return False
    if (_has(text, NOW_WORDS) or NOW_END.search(text) or YEAR.search(text) or SEASON_SPAN.search(text)
            or MATCHWEEK_PATTERN.search(text) or FUTURE.search(text)):
        return False
    if _has(text, ALL_TIME_TH) or ALL_TIME_EN.search(text):
        return True
    # A best or worst finish is over finished seasons ("แล้วจบอันดับดีที่สุดเท่าไหร่" names no league).
    superlative = _has(text, SUPERLATIVE_TH) or bool(SUPERLATIVE_EN.search(text))
    # Without the league named, only a known club makes it a Premier League record ("บุรีรัมย์…" is not).
    if (superlative and team_known and _has(text, ("จบ", "finish"))
            and not _has(text, (*OTHER_TITLE_WORDS, *NOT_PL_TABLE_WORDS))):
        return True
    if not _has(text, PL_WORDS):
        return False
    return _has(text, ("ทั้งหมด",)) or bool(TOTAL_EN.search(text))


def _title_question(text: str) -> bool:
    return _has(text, ("แชมป์",)) or bool(TITLE_WORDS_EN.search(text))


def _range_question(text: str) -> bool:
    return (_has(text, RANGE_TH) or bool(RANGE_EN.search(text))) and bool(YEAR.search(text))


def _range_topic(text: str, current_season: str | None) -> str | None:
    """Titles or table records over a span of past seasons; None leaves the question to the other rules."""
    if (not _range_question(text) or _has(text, (*OTHER_TITLE_WORDS, *SCORER_WORDS, *OTHER_LEAGUE_WORDS))
            or OTHER_LEAGUE_EN.search(text) or _has(text, NOW_WORDS)):
        return None
    if current_season and min(int(year) for year in YEAR.findall(text)) >= int(current_season):
        return None  # the archive ends last season
    if _has(text, ("ตกชั้น", "relegat")):
        return "relegations"
    if _title_question(text):
        return "titles"
    return "table" if _has(text, TABLE_WORDS_TH) or TABLE_WORDS_EN.search(text) else None


SUBJECT_FILLER_TH = tuple(sorted((
    "แล้ว", "จบอันดับ", "จบ", "อันดับ", "ดีที่สุด", "แย่ที่สุด", "สูงสุด", "ต่ำสุด", "เท่าไหร่", "เท่าไร", "ที่", "ใน",
    "พรีเมียร์ลีก", "ลีก", "เคย", "ได้", "กี่", "ครับ", "คะ", "ค่ะ", "นะ", "ล่ะ", "ของ", "ทีม", "แต้ม", "รวม", "ทั้งหมด",
    "ไหม", "มั้ย", "อยู่", "คือ", "อะไร", "ไหน", "ปี", "หรอ", "เหรอ", "นี้", "พวกเขา", "เขา"), key=len, reverse=True))
SUBJECT_FILLER_EN = re.compile(r"\b(?:what|was|is|their|they|its|the|best|worst|highest|lowest|ever|finish(?:ed)?|"
                               r"position|in|premier|league|and|then|how|about|points|total|all[- ]time|so|far)\b")


def _names_another_subject(text: str) -> bool:
    """Words left after the finish-question filler name a subject of their own (another club)."""
    rest = SUBJECT_FILLER_EN.sub(" ", YEAR.sub(" ", text.replace("'s", " ")))
    for word in SUBJECT_FILLER_TH:
        rest = rest.replace(word, " ")
    return bool(re.search(r"[a-zก-๙]", rest))


def _champions_by_year(text: str, current_season: str | None) -> bool:
    """The "both seasons" search: league champions only, past years only, not a range."""
    if "champions by year" not in text or _has(text, OTHER_TITLE_WORDS) or _range_question(text):
        return False
    years = [int(year) for year in YEAR.findall(text)]
    return not (current_season and years and max(years) > int(current_season))


def _champions_by_year_prefix(text: str) -> str:
    """By the year, not the user's wording: 1992 offers 1991/92 (First Division) and 1992/93 (Premier League)."""
    match = re.search(r"champions by year ((?:19|20)\d{2})", text)
    year = int(match.group(1)) if match else 9999
    first_division = "English top-flight First Division champions"
    if year < 1992:
        return first_division
    return f"{first_division} Premier League" if year == 1992 else "Premier League"


def _war_title_year(text: str, found: list) -> int | None:
    """A title question for a year without a top-flight season (clubs allowed)."""
    if not _title_question(text) or len(found) > 2 or _has(text, (*OTHER_TITLE_WORDS, *OTHER_LEAGUE_WORDS)):
        return None
    if OTHER_LEAGUE_EN.search(text):
        return None
    years = [int(year) for year in YEAR.findall(text)]
    return years[0] if len(years) == 1 and years[0] in WAR_YEARS else None


def _names_more_than_a_title(text: str) -> bool:
    rest = CLARIFY_FILLER_EN.sub(" ", YEAR.sub(" ", text))
    for word in CLARIFY_FILLER_TH:
        rest = rest.replace(word, " ")
    return bool(re.search(r"[a-zก-๙]", rest))


def ambiguous_title_year(text: str, found: list) -> int | None:
    """A title question naming one calendar year and no club: the year spans two seasons."""
    if found or not _title_question(text) or _has(text, (*OTHER_TITLE_WORDS, *ARCHIVE_CLUB_WORDS)):
        return None
    if _names_more_than_a_title(text):
        return None
    if season_prediction(text) or _range_question(text) or SEASON_SPAN.search(text):
        return None
    years = YEAR.findall(text)
    return int(years[0]) if len(years) == 1 else None


def title_count_without_team(text: str, found: list, history: list[dict], teams: TeamDirectory) -> bool:
    if found or not _title_question(text) or not (_has(text, COUNT_TH) or COUNT_EN.search(text)):
        return False
    if season_prediction(text) or _has(text, (*LEAGUE_WIDE_TH, *OTHER_TITLE_WORDS, *ARCHIVE_CLUB_WORDS)):
        return False
    if LEAGUE_WIDE_EN.search(text) or _names_more_than_a_title(text):
        return False
    return not any(teams.find(str(item.get("content") or ""))
                   for item in history[-10:] if item.get("role") == "user")


REPLY_QUESTION_WORDS = ("ใคร", "กี่", "ไหม", "อะไร", "เท่าไหร่", "?", "who", "how", "which", "what")


def _answers_the_question_back(reply: str, asked_text: str, teams: TeamDirectory | None) -> bool:
    """Each question back accepts only its own kind of answer, so a merge can never ask it again."""
    season = bool(SEASON_SPAN.search(reply) or YEAR.search(reply))
    if asked_text.startswith(("หมายถึงแชมป์ของทีมไหนครับ", "Which club do you mean?")):
        return bool(teams and teams.find(reply)) or _has(reply, (*ARCHIVE_CLUB_WORDS, *OTHER_TITLE_WORDS))
    if asked_text.startswith(COMPETITION_CLARIFY_PREFIXES):
        return season or _has(reply, (*PL_WORDS, *OTHER_TITLE_WORDS))
    return season


OFFERED_SEASONS = re.compile(r"(?<!\d)(\d{4}/\d{2})(?!\d)")
REPLY_TAIL = re.compile(r"(?:\s*(?:ครับ|คับ|ค่ะ|คะ|นะ|จ้า|[?!.]))+\s*$")
# Fillers around the answer are fine ("ที่จบปี 2025", "both of them"); "before/after the end" and
# "both teams" are not a choice between the two seasons.
ENDED_REPLY = re.compile(r"(?:จบ(?:ปี)?|ended(?: in)?|ending)\s*((?:19|20)\d{2})")
BEGAN_REPLY = re.compile(r"(?:เริ่ม(?:ปี)?|began(?: in)?|starting|start(?:ed)?(?: in)?)\s*((?:19|20)\d{2})")
NOT_A_SEASON_EDGE = re.compile(r"(?:ก่อน|หลัง|before|after)\s*(?:the\s*)?(?:จบ|เริ่ม|end|start|began)")
BOTH_REPLY = ("ทั้งสอง", "ทั้งคู่", "both")
NOT_BOTH_SEASONS = ("ทีม", "team", "club", "สโมสร", "นัด", "match")
FIRST_REPLY = re.compile(r"^(?:อัน|ตัว|อย่าง)?แรก$|^(?:the )?(?:first|former)$")
SECOND_REPLY = re.compile(r"^(?:อัน|ตัว)?หลัง$|^อันที่สอง$|^(?:the )?(?:second|latter)$")


def _season_choice(reply: str, asked_text: str) -> str | None:
    """A season answer to a year question back: a season, "both", or None."""
    offered = OFFERED_SEASONS.findall(asked_text)[:2]
    if len(offered) < 2:
        return None
    ended, began = offered
    year = int(began[:4])
    span = SEASON_SPAN.search(reply)
    if span:
        return span.group(0).replace(" ", "")
    if NOT_A_SEASON_EDGE.search(reply):
        return None
    for pattern, season in ((ENDED_REPLY, ended), (BEGAN_REPLY, began)):
        match = pattern.search(reply)
        if match:
            return season if int(match.group(1)) == year else None
    if _has(reply, BOTH_REPLY) and not _has(reply, NOT_BOTH_SEASONS):
        return "both"
    if FIRST_REPLY.search(reply):
        return ended
    if SECOND_REPLY.search(reply):
        return began
    return None


def _clarify_chain(history: list[dict]) -> tuple[str, list[tuple[str, str]], str] | None:
    """The first question, the earlier (reply, question back) pairs and the latest question back."""
    if len(history) < 2 or history[-1].get("role") != "assistant":
        return None
    asked_text = str(history[-1].get("content") or "")
    if not asked_text.startswith(CLARIFY_PREFIXES):
        return None
    index, earlier = len(history) - 2, []
    # A user turn that is itself a question starts its own chain: the walk stops there.
    while (index >= 2 and len(earlier) < 2 and history[index].get("role") == "user"
           and not _is_a_question(str(history[index].get("content") or ""))
           and history[index - 1].get("role") == "assistant"
           and str(history[index - 1].get("content") or "").startswith(CLARIFY_PREFIXES)):
        earlier.insert(0, (str(history[index].get("content") or "").strip(),
                           str(history[index - 1].get("content") or "")))
        index -= 2
    if history[index].get("role") != "user":
        return None
    return str(history[index].get("content") or "").strip(), earlier, asked_text


def _is_a_question(text: str) -> bool:
    """The gate a reply must pass, inverted: too long, a title question or question words."""
    lowered = REPLY_TAIL.sub("", text.strip()).lower()
    return (len(lowered) > 40 or _title_question(lowered)
            or _has(lowered, (*REPLY_QUESTION_WORDS, *REPLY_TOPIC_WORDS)))


def _league_suffix(asked_text: str) -> str:
    top_flight = "ลีกสูงสุดอังกฤษ" in asked_text or "English top-flight" in asked_text
    if asked_text.startswith("Which competition do you mean?"):
        return " English top-flight" if top_flight else " Premier League"
    return " ลีกสูงสุดอังกฤษ" if top_flight else " พรีเมียร์ลีก"


def resolve_clarify_reply(query: str, history: list[dict], teams: TeamDirectory | None = None) -> str | None:
    """Join a short answer to our question back with the question that needed it (no LLM)."""
    reply = REPLY_TAIL.sub("", query.strip())
    chain = _clarify_chain(history)
    if not reply or len(reply) > 40 or chain is None:
        return None
    first, earlier, asked_text = chain
    if not first:
        return None
    lowered = reply.lower()
    if _title_question(lowered) or _has(lowered, (*REPLY_QUESTION_WORDS, *REPLY_TOPIC_WORDS)):
        return None
    team_question = asked_text.startswith(("หมายถึงแชมป์ของทีมไหนครับ", "Which club do you mean?"))
    choice = None if team_question else _season_choice(lowered, asked_text)
    names_competition = _has(lowered, (*OTHER_TITLE_WORDS, *PL_WORDS))
    if (choice is None and not team_question and not names_competition
            and (YEAR.search(lowered) or SEASON_SPAN.search(lowered))):
        return None  # "จบปี 2023" or "หลังปี 2010" names a year but picks neither offered season
    if choice is None and not _answers_the_question_back(lowered, asked_text, teams):
        return None
    # A season chosen now replaces an earlier season answer to the same question.
    parts = [first, *(answer for answer, asked in earlier
                       if _answers_the_question_back(answer.lower(), asked, teams)
                       and not (choice is not None and (SEASON_SPAN.search(answer) or YEAR.search(answer))))]
    if choice == "both":
        parts.append(f"champions by year {int(OFFERED_SEASONS.findall(asked_text)[1][:4])}")
    elif choice is not None:
        parts.append(choice)
    else:
        parts.append(reply)
    merged = " ".join(part for part in parts if part)
    # "Which competition?" offered the league seasons; a bare season answer means that league.
    if asked_text.startswith(COMPETITION_CLARIFY_PREFIXES) and not _has(
            merged.lower(), (*OTHER_TITLE_WORDS, *PL_WORDS, "ลีกสูงสุดอังกฤษ", "english top-flight")):
        merged += _league_suffix(asked_text)
    return merged


def _record_rewrite(query: str, names: list[str], topic: str) -> str:
    """Search text for the archive's club and league records; English questions stay as asked."""
    if not re.search(r"[ก-๙]", query):
        return query
    if topic == "titles":
        terms = "Premier League titles seasons"
    elif topic == "relegations":
        terms = "Premier League relegations most relegated clubs"
    else:
        terms = ("Premier League record best finish worst finish total points" if names
                 else "Premier League all-time records most points")
    return " ".join(part for part in (*names, terms, query.strip()) if part)


def _person_title(text: str, teams: TeamDirectory | None) -> bool:
    if PERSON_TITLE.search(text):
        return True
    at = PERSON_TITLE_AT.search(text)
    return bool(at and teams and teams.find(at.group(1)))


def club_record_team_ids(decision: Decision, query: str, teams: TeamDirectory | None = None) -> list[int]:
    """The clubs whose all-time record summary this question needs, or [] for any other question."""
    text = query.lower()
    if decision.route != "football_rag" or decision.intent != "trivia_history":
        return []
    if not 1 <= len(decision.team_ids) <= 2 or "season" in decision.filters:
        return []
    if YEAR.search(text) or SEASON_SPAN.search(text) or _head_to_head(text) or WOMEN_TEAM.search(text):
        return []
    comparison = len(decision.team_ids) == 2 or _has(text, COMPARISON_WORDS)
    if _person_title(text, teams) and not comparison:
        return []
    if not _has(text, CLUB_RECORD_WORDS) or _has(text, (*OTHER_TITLE_WORDS, *SCORER_WORDS)):
        return []
    return list(decision.team_ids)


def decide(query: str, context: dict, history: list[dict], teams: TeamDirectory,
           favorite_team_id: int | None = None) -> Decision | None:
    decision = _decide(query, context, history, teams, favorite_team_id)
    if decision is not None:
        decision.record_team_ids = club_record_team_ids(decision, query, teams)
    return decision


def _decide(query: str, context: dict, history: list[dict], teams: TeamDirectory,
            favorite_team_id: int | None = None) -> Decision | None:
    text = PL_ABBR.sub(" premier league ", query.lower().strip()).strip()
    if not text:
        return Decision("clarify", None, "guard", 1.0, "ไม่มีคำถาม")
    matchweek = MATCHWEEK_PATTERN.search(text)
    if matchweek and not 1 <= int(matchweek.group(1)) <= 38:
        return Decision("clarify", None, "guard", 1.0, "เลขนัดต้องอยู่ระหว่าง 1 ถึง 38")
    found = teams.find(query)
    if not found and ("ยูไนเต็ด" in text or re.search(r"(?<![A-Za-z])united(?![A-Za-z])", text)):
        return Decision("clarify", None, "guard", 1.0, "ชื่อ United กำกวม")
    if not found and _has(text, ("นัดนั้น", "ทีมไหนชนะ", "เขายิง")) and not history:
        return Decision("clarify", None, "guard", 1.0, "ขาดทีมที่อ้างถึง")
    if len(found) > 2:
        return Decision("clarify", None, "guard", 1.0, "พบหลายทีมในคำถาม")
    intent = _intent(query, context.get("season"))
    archive_rule = intent not in ("out_of_scope", "prediction") and not FUTURE.search(text)
    # A "both seasons" reply: the champions-by-year section answers the two seasons at once.
    if archive_rule and _champions_by_year(text, context.get("season")):
        decision = enrich(Decision("football_rag", "trivia_history", "rules", 0.9, "แชมป์ตามปี",
                                   {"category": [HISTORICAL]}), query, context, history, teams, favorite_team_id)
        decision.rewritten_query = f"{_champions_by_year_prefix(text)} {query.strip()}"
        return decision
    # A club from the history counts only when this question names no other subject ("แล้วบุรีรัมย์…").
    team_known = bool(found) or (not _names_another_subject(text) and any(
        teams.find(str(item.get("content") or "")) for item in history[-10:] if item.get("role") == "user"))
    if archive_rule and all_time_table_question(text, team_known):
        decision = enrich(Decision("football_rag", "trivia_history", "rules", 0.9, "คำถามสถิติทั้งยุค",
                                   {"category": [HISTORICAL]}), query, context, history, teams, favorite_team_id)
        decision.rewritten_query = _record_rewrite(query, [team.short_name for team in found], "table")
        return decision
    war_year = _war_title_year(text, found) if archive_rule else None
    if war_year is not None:
        # No season ended or began that year: the archive says so, no question back.
        span, war = WAR_YEARS[war_year]
        decision = enrich(Decision("football_rag", "trivia_history", "rules", 0.9, "ปีที่ไม่มีลีกช่วงสงคราม",
                                   {"category": [HISTORICAL]}), query, context, history, teams, favorite_team_id)
        decision.rewritten_query = " ".join([
            *(team.name for team in found),
            f"English top-flight First Division champions {span} no First Division football {war}",
            query.strip()])
        return decision
    year = ambiguous_title_year(text, found) if archive_rule else None
    if year is not None:
        thai, english = title_year_clarify(year, _has(text, PL_WORDS))
        return Decision("clarify", None, "guard", 0.9, "แชมป์ปีเดียวกำกวม",
                        clarify_text=thai, clarify_text_en=english)
    if archive_rule and title_count_without_team(text, found, history, teams):
        thai, english = team_clarify()
        return Decision("clarify", None, "guard", 0.9, "ไม่ระบุทีม",
                        clarify_text=thai, clarify_text_en=english)
    # "ตั้งแต่ปี 2010" is a range: a season filter kept only one season (and dropped the club records).
    topic = _range_topic(text, context.get("season")) if archive_rule else None
    if topic is not None:
        decision = enrich(Decision("football_rag", "trivia_history", "rules", 0.9, "คำถามช่วงเวลา",
                                   {"category": [HISTORICAL]}), query, context, history, teams, favorite_team_id)
        decision.rewritten_query = _record_rewrite(query, [team.short_name for team in found], topic)
        return decision
    # An English club record question names the club the way its archive document does (live chat c39:
    # as asked, other clubs' "all eras" chunks outranked hist-club-manchester-united).
    if (archive_rule and intent == "trivia_history" and found and not re.search(r"[ก-๙]", query)
            and _has(text, ENGLISH_RECORD_WORDS) and not (YEAR.search(text) or SEASON_SPAN.search(text))):
        decision = enrich(Decision("football_rag", "trivia_history", "rules", 0.9, "English club record question",
                                   {"category": [HISTORICAL]}), query, context, history, teams, favorite_team_id)
        terms = "Premier League record relegated" if "relegat" in text else "Premier League record titles"
        decision.rewritten_query = " ".join([*(team.name for team in found), terms, query.strip()])
        return decision
    if intent is None and chat_enabled():
        kind = chat_kind(normalize_thai(text), len(found))
        if kind:
            return Decision("chat", "chitchat", "rules", 0.9, f"คุยทั่วไป: {kind}", kind=kind)
    if intent is None and history and re.search(r"(แล้ว|นัดก่อน|นัดนั้น)", text):
        for item in reversed(history[-10:]):
            if item.get("role") == "user":
                intent = _intent(item.get("content", ""), context.get("season"))
                if intent is not None:
                    break
    if intent not in ("out_of_scope", "prediction"):
        past = history_filters(query, len(found), context.get("season"))
        if past is not None:
            decision = Decision("football_rag", "trivia_history", "rules", 0.9,
                                "คำถามสถิติย้อนหลังพรีเมียร์ลีก", past)
            return enrich(decision, query, context, history, teams, favorite_team_id)
    if intent is None:
        return None
    route = INTENT_MAP[intent][0]
    decision = Decision(route, intent, "guard" if route == "decline" else "rules", 1.0 if route == "decline" else 0.9,
                        f"ตรวจพบ intent {intent}", _category_filter(intent))
    return enrich(decision, query, context, history, teams, favorite_team_id)
