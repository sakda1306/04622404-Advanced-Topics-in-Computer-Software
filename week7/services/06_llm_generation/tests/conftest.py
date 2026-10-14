"""FakeLLM + dependency override — pytest ต้องผ่านโดยไม่มี key ไม่ต่อเน็ต"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_MOCK", "true")

# ต้อง import หลังตั้ง LLM_MOCK ด้านบน เพราะ app.config อ่านค่า env ตอน import
# (pydantic-settings) — ตั้งใจไม่ให้อยู่บนสุดของไฟล์ จึงปิด E402 ตรงนี้
from app.config import settings
from app.main import app

settings.llm_mock = True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
