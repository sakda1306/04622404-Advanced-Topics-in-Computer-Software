import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .llm_client import AnswerTooLongError, LLMUnavailableError, call_general_ai
from .local_classifier import ModelNotLoadedError, classify as classify_intent, model_version
from .schemas import (
    ClassifyRequest,
    EngineResult,
    GeneralRequest,
    PredictRequest,
    ProblemDetail,
    SimulateRequest,
    StrengthIn,
    TokenUsage,
)
from .poisson import (
    LEAGUE_AVG_GOALS_PER_MATCH,
    TeamStrength,
    format_percent,
    match_outcome_probabilities,
)
from .simulate import SimulationInputError, simulate_season
from .token_budget import trim_history_to_budget

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("engines")

app = FastAPI(title="engines (04_ai_engines)")

# วัดกับ LLM จริง (2026-10-03): prompt เดิมตีความ "ล้ำหน้า" เป็น "ก้าวหน้ากว่าคนอื่น" แต่งรายละเอียดเพิ่ม
# (เช่น แมนซิตี้ "จากลอนดอน") และตอบ "เล่าประวัติ..." ยาวจนเกิน GENERAL_MAX_TOKENS → 503
# - ทุกคำถามอยู่ในบริบทฟุตบอล + คำศัพท์ไทยที่ใช้บ่อย
# - router (03) ต่อท้ายคำถามด้วยวงเล็บ "ชื่อทีมในคำถาม: ผีแดง = Manchester United FC" เมื่อผู้ใช้เรียกทีมด้วยฉายา
# - ตอบตรงคำถาม 2-5 ประโยค ไม่เพิ่มเรื่องที่ไม่ได้ถาม ไม่แต่งตัวเลขที่ไม่แน่ใจ
SYSTEM_PROMPT_TH = (
    "คุณเป็นผู้ช่วยตอบคำถามฟุตบอล โดยเฉพาะพรีเมียร์ลีก ตอบเป็นภาษาไทยแบบเป็นกันเอง "
    'เรียกตัวเองว่า "ผม" และลงท้ายด้วย "ครับ" เสมอ ตอบให้กระชับ 2 ถึง 5 ประโยค '
    "ทุกคำถามอยู่ในบริบทฟุตบอล ให้ตีความคำตามความหมายในฟุตบอล เช่น ล้ำหน้า = offside, "
    "จุดโทษ = penalty, ดวลจุดโทษ = penalty shoot-out, ต่อเวลาพิเศษ = extra time, "
    "ใบเหลือง/ใบแดง = yellow/red card, ประตูตัวเอง = own goal "
    'ถ้าท้ายคำถามมีวงเล็บ "ชื่อทีมในคำถาม" ให้ใช้บอกว่าฉายานั้นคือสโมสรใด โดยไม่ต้องพูดถึงวงเล็บนั้น '
    "ตอบตรงคำถามเลย ไม่ต้องเกริ่น และไม่ต้องเพิ่มเรื่องที่ไม่ได้ถาม "
    "ใส่เฉพาะข้อเท็จจริงที่มั่นใจ ถ้าไม่แน่ใจตัวเลข ปี สถิติ ชื่อ หรือรายละเอียดใด ให้ตัดทิ้งหรือบอกว่าไม่แน่ใจ "
    "ห้ามแต่งขึ้นเอง "
    "ถ้าคำถามต้องการข้อมูลสด เช่น ผลการแข่งขันล่าสุด ตารางคะแนน หรือโปรแกรมการแข่งขัน "
    "ให้บอกตรง ๆ ว่าคุณไม่มีข้อมูลสดในส่วนนี้ อย่าเดาผลหรือสกอร์เด็ดขาด"
)
SYSTEM_PROMPT_EN = (
    "You are an assistant that answers football questions, especially about the Premier League. "
    "Answer in English in a friendly way, in 2 to 5 sentences. "
    "Read every question as a football question (for example, offside, penalty shoot-out, extra time). "
    'If the question ends with a note in parentheses, "Teams named in the question", use it to tell '
    "which club a nickname means, without mentioning the note. "
    "Answer the question directly without an introduction and do not add topics that were not asked. "
    "State only facts you are sure of; leave out or say you are unsure about any number, year, "
    "statistic or name you are not sure of, and never make one up. "
    "If the question needs live data such as recent results, standings, or fixtures, "
    "say plainly that you don't have live data for that — never guess a score or result."
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    CONTRACT.md §0: ถ้าไม่มี X-Request-ID ให้สร้าง UUID แล้วส่งต่อ/ใส่ log ทุกครั้ง

    [ข้อ 4] ครอบ call_next ด้วย try/except เอง เพราะถ้า exception หลุดออกจาก call_next
    Starlette จะจัดการผ่าน ServerErrorMiddleware ซึ่งอยู่ชั้นนอกสุด (นอก middleware นี้)
    — โค้ดด้านล่าง (ใส่ X-Request-ID, log http_request) จะไม่ถูกรันเลย ทำให้ response ของ error
    ไม่มี request_id ให้ไล่ข้ามบริการ ขัด CONTRACT §0 จึงต้องจับเองตรงนี้แทนที่จะพึ่ง
    @app.exception_handler(Exception) เพียงอย่างเดียว
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    t0 = time.monotonic()

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            '{"event":"unhandled_exception","error":"%s","request_id":"%s"}',
            str(exc),
            request_id,
        )
        response = _problem(
            status=500,
            code="INTERNAL_ERROR",
            title="Internal server error",
            detail="เกิดข้อผิดพลาดที่ไม่คาดคิดใน engines",
            request_id=request_id,
        )

    ms = int((time.monotonic() - t0) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        '{"event":"http_request","path":"%s","status":%d,"ms":%d,"request_id":"%s"}',
        request.url.path,
        response.status_code,
        ms,
        request_id,
    )
    return response


def _problem(*, status: int, code: str, title: str, detail: str, request_id: str) -> JSONResponse:
    body = ProblemDetail(
        type=f"https://errors.football-assistant.local/{code.lower().replace('_', '-')}",
        title=title,
        status=status,
        code=code,
        detail=detail,
        service=settings.SERVICE_NAME,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        media_type="application/problem+json",
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.post("/general")
def general(body: GeneralRequest, request: Request):
    # [ข้อ 5] ใช้ request.state.request_id (ตั้งค่าโดย request_id_middleware) เป็นค่าเดียว
    # ทั้ง response header, body และ log — ไม่ใช้ body.request_id อีกต่อไป เพราะถ้าผู้เรียกส่ง
    # request_id มาแค่ใน body (ไม่ใส่ header X-Request-ID) ค่าที่ตอบกลับจะคนละค่ากับ header/log
    # ทำให้ trace ข้ามบริการไม่ได้ตาม CONTRACT §0
    request_id = request.state.request_id

    system_prompt = SYSTEM_PROMPT_TH if body.language == "th" else SYSTEM_PROMPT_EN

    # D4: ตัด history เก่าสุดออกจนกว่าจะอยู่ในงบ token โดยประมาณ (เก็บข้อความใหม่สุดไว้ก่อน)
    history_dicts = [{"role": h.role, "content": h.content} for h in body.history[-10:]]
    trimmed_history = trim_history_to_budget(
        history_dicts,
        system_prompt=system_prompt,
        query=body.query,
        max_input_tokens=settings.GENERAL_MAX_INPUT_TOKENS,
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": body.query})

    t0 = time.monotonic()
    try:
        content, model_used, token_usage = call_general_ai(
            messages=messages,
            max_tokens=settings.GENERAL_MAX_TOKENS,
            request_id=request_id,
        )
    except AnswerTooLongError as e:
        # [รีวิว PR #21 ข้อ 2] CONTRACT.md §8 กำหนด code สำหรับกรณี provider ใช้ไม่ได้ไว้แค่
        # LLM_UNAVAILABLE เท่านั้น จึงคงใช้ code เดิมตาม Contract (ไม่เพิ่ม code ใหม่ ไม่ต้องคุย/
        # แก้ Contract กับเจ้าของ 03) แต่ยังแยก except ไว้จาก LLMUnavailableError ทั่วไป เพื่อใส่
        # detail อธิบายสาเหตุที่แท้จริงว่าเป็นเพราะคำตอบยาวเกิน token budget ไม่ใช่ provider ล่มจริง ๆ
        return _problem(
            status=503,
            code="LLM_UNAVAILABLE",
            title="LLM providers unavailable",
            detail=(
                f"Groq และ Gemini ตอบสำเร็จแต่คำตอบยาวเกิน GENERAL_MAX_TOKENS "
                f"({settings.GENERAL_MAX_TOKENS}) ทุกครั้ง — ไม่ใช่ provider ล่ม "
                f"ลองถามให้เจาะจง/สั้นลง หรือแจ้งทีมถ้าเจอบ่อยเพื่อพิจารณาขยับเพดาน: {e}"
            ),
            request_id=request_id,
        )
    except LLMUnavailableError as e:
        return _problem(
            status=503,
            code="LLM_UNAVAILABLE",
            title="LLM providers unavailable",
            detail=f"ทั้ง Groq และ Gemini เรียกไม่สำเร็จ: {e}",
            request_id=request_id,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    result = EngineResult(
        engine="general_ai",
        content=content,
        data=None,
        sources=[],
        model=model_used,
        latency_ms=latency_ms,
        token_usage=TokenUsage(**token_usage),
    )
    return result.model_dump()


@app.post("/local/classify")
def local_classify(body: ClassifyRequest, request: Request):
    """D3 — router ใช้เส้นนี้เป็นชั้น classifier ก่อนตัดสินใจ route (CONTRACT.md §3)"""
    # [ข้อ 5] เหตุผลเดียวกับ /general — ใช้ request.state.request_id เป็นค่าเดียว
    request_id = request.state.request_id

    t0 = time.monotonic()
    try:
        result_data = classify_intent(body.text)
        model_used = model_version()
    except ModelNotLoadedError as e:
        return _problem(
            status=503,
            code="MODEL_UNAVAILABLE",
            title="Local classifier model unavailable",
            detail=str(e),
            request_id=request_id,
        )
    latency_ms = int((time.monotonic() - t0) * 1000)

    result = EngineResult(
        engine="local_ai",
        content=f"intent: {result_data['label']} ({result_data['score']:.2f})",
        data=result_data,
        sources=[],
        model=model_used,
        latency_ms=latency_ms,
        token_usage=TokenUsage(input=0, output=0),  # ไม่ได้เรียก LLM
    )
    return result.model_dump()


def _strength(s: StrengthIn) -> TeamStrength:
    return TeamStrength(
        attack_goals_per_match=s.attack,
        defense_goals_conceded_per_match=s.defense,
        matches_used=s.matches_used,
    )


@app.post("/local/predict")
def local_predict(body: PredictRequest, request: Request):
    """
    ทำนายผลนัดด้วย Poisson model · 07 (football-data) คำนวณความแข็งของทีมแล้วส่งมา (CONTRACT v1.7)
    ถ้าไม่ส่ง strength มา ยังตอบ 501 ตาม CONTRACT §3 เพื่อไม่ให้ผู้เรียกรุ่นเก่าพัง
    """
    request_id = request.state.request_id
    if body.home_strength is None or body.away_strength is None:
        return _problem(
            status=501,
            code="NOT_IMPLEMENTED",
            title="Prediction feature not available yet",
            detail="ต้องส่ง home_strength และ away_strength (เรียกผ่าน 07 /football/predict)",
            request_id=request_id,
        )
    t0 = time.monotonic()
    probs = match_outcome_probabilities(
        _strength(body.home_strength),
        _strength(body.away_strength),
        league_avg=body.league_avg_goals or LEAGUE_AVG_GOALS_PER_MATCH,
    )
    home = body.home_name or f"ทีม {body.home_team_id}"
    away = body.away_name or f"ทีม {body.away_team_id}"
    score = probs["most_likely_score"]
    content = (
        f"{home} ชนะ {format_percent(probs['home_win'])} · เสมอ {format_percent(probs['draw'])} · "
        f"{away} ชนะ {format_percent(probs['away_win'])} · "
        f"สกอร์ที่น่าจะเป็นที่สุด {score['home']}–{score['away']}"
    )
    data = {
        **probs,
        "method": "poisson-v1",
        "matches_used": min(body.home_strength.matches_used, body.away_strength.matches_used),
    }
    result = EngineResult(
        engine="local_ai",
        content=content,
        data=data,
        sources=[],
        model="poisson-v1",
        latency_ms=int((time.monotonic() - t0) * 1000),
        token_usage=TokenUsage(input=0, output=0),
    )
    return result.model_dump()


@app.post("/local/simulate")
def local_simulate(body: SimulateRequest, request: Request):
    """จำลองฤดูกาลที่เหลือ (CONTRACT v1.7 §3) · sync def → FastAPI รันใน threadpool ไม่บล็อก event loop"""
    request_id = request.state.request_id
    t0 = time.monotonic()
    try:
        data, content = simulate_season(body.inputs.model_dump(), body.n_sims, body.seed)
    except SimulationInputError as e:
        return _problem(
            status=422,
            code="VALIDATION_ERROR",
            title="Invalid simulation inputs",
            detail=str(e),
            request_id=request_id,
        )
    result = EngineResult(
        engine="local_ai",
        content=content,
        data=data,
        sources=[],
        model="poisson-mc-v1",
        latency_ms=int((time.monotonic() - t0) * 1000),
        token_usage=TokenUsage(input=0, output=0),
    )
    return result.model_dump()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.error(
        '{"event":"unhandled_exception","error":"%s","request_id":"%s"}', str(exc), request_id
    )
    return _problem(
        status=500,
        code="INTERNAL_ERROR",
        title="Internal server error",
        detail="เกิดข้อผิดพลาดที่ไม่คาดคิดใน engines",
        request_id=request_id,
    )