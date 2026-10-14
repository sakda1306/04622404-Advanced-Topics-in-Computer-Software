"""X-Request-ID + JSON logging (หนึ่งบรรทัดต่อ event, stdout)"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

logger = logging.getLogger("generation")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)
logger.propagate = False
# เดิมไม่เคยตั้ง level เลย logger จะ inherit จาก root (default WARNING)
# ทำให้ logger.info(...) ใน log_event() ไม่ถูกพิมพ์ออกมาเลยไม่ว่ากรณีไหน
# ตั้งจาก settings.log_level (ค่าเริ่มต้น "INFO" ตาม config.py)
logger.setLevel(settings.log_level)


def log_event(event: str, request_id: str, **fields) -> None:
    payload = {"event": event, "request_id": request_id, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False))


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)
        # route อาจตั้งค่า X-Request-ID เองแล้ว (เช่น จาก body.request_id) ให้เคารพค่านั้น
        final_rid = response.headers.get("X-Request-ID") or rid
        response.headers["X-Request-ID"] = final_rid
        log_event(
            "http_request",
            final_rid,
            path=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
