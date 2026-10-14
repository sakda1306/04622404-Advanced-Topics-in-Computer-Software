"""POST /report/weekly — football-data(07) เรียกเท่านั้น"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.pipeline.weekly import run_weekly_report
from app.routes.generate import get_llm_client, resolve_request_id
from app.schemas import WeeklyReportRequest, WeeklyReportResponse

router = APIRouter()


@router.post("/report/weekly", response_model=WeeklyReportResponse)
async def report_weekly(
    body: WeeklyReportRequest, request: Request, response: Response
):
    request_id = resolve_request_id(body.request_id, request)
    # sync กับ request.state เหมือนใน generate.py — กัน request_id ไม่ตรงกันระหว่าง
    # success response กับ error response (เช่นตอน LLMUnavailable -> 503)
    request.state.request_id = request_id
    response.headers["X-Request-ID"] = request_id
    llm = get_llm_client(request)
    return await run_weekly_report(
        body, llm=llm, settings=settings, request_id=request_id
    )
