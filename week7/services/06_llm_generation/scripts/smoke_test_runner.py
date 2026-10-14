"""
smoke_test_runner.py
=====================
รันทุกเคสใน curl_tests/cases/ ยิงเข้าเซิร์ฟเวอร์ที่รันอยู่จริง (mock หรือ provider จริงก็ได้)
วัดเวลา, ดึง model/token_usage/latency_ms/safety จาก response จริงของแอป แล้วพิมพ์ตาราง markdown

Schema ที่ยึดตาม (ตัวอย่างจริงจาก /generate):
{
  "request_id": "...",
  "answer": "...",
  "sources": [...],
  "citations_removed": 0,
  "safety": {"blocked": false, "reason": null},
  "model": "mock/llm",
  "latency_ms": 32,
  "token_usage": {"input": 82, "output": 22}
}

วิธีใช้:
    1. เปิดอีก terminal รัน server ก่อน:
         python -m uvicorn app.main:app --port 8000
       (ถ้าจะทดสอบ provider จริง อย่าตั้ง LLM_MOCK=true)

    2. รันสคริปต์นี้จาก services/06_llm_generation:
         python scripts/smoke_test_runner.py

    3. ผลจะโชว์ในหน้าจอ และเซฟเป็น scripts/smoke_test_results.md ด้วย
"""

import json
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
CASES_DIR = Path(__file__).resolve().parents[1] / "curl_tests" / "cases"
OUTPUT_FILE = Path(__file__).resolve().parent / "smoke_test_results.md"

# deadline อ้างอิงจาก app/config.py (generate_deadline_s / report_deadline_s)
DEADLINE_GENERATE = 22.0
DEADLINE_REPORT = 55.0


def endpoint_for(filename: str) -> str:
    if "report_weekly" in filename:
        return "/report/weekly"
    return "/generate"


def deadline_for(endpoint: str) -> float:
    return DEADLINE_REPORT if endpoint == "/report/weekly" else DEADLINE_GENERATE


def run_case(case_file: Path) -> dict:
    endpoint = endpoint_for(case_file.name)
    deadline = deadline_for(endpoint)
    url = BASE_URL + endpoint

    with open(case_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    start = time.perf_counter()
    error = None
    status_code = None
    body = {}
    try:
        resp = httpx.post(url, json=payload, timeout=deadline + 10)
        status_code = resp.status_code
        try:
            body = resp.json()
        except ValueError:
            body = {}
    except httpx.HTTPError as e:
        error = str(e)
    elapsed_measured = time.perf_counter() - start

    # ดึงตาม schema จริงของแอป
    model_used = body.get("model", "-")
    server_latency_ms = body.get("latency_ms", "-")

    token_usage = body.get("token_usage") or {}
    if token_usage:
        token_usage_str = f"in:{token_usage.get('input', '-')} / out:{token_usage.get('output', '-')}"
    else:
        token_usage_str = "-"

    safety = body.get("safety") or {}
    safety_blocked = safety.get("blocked", "-")

    citations_removed = body.get("citations_removed", "-")

    return {
        "case": case_file.name,
        "endpoint": endpoint,
        "status_code": status_code,
        "elapsed_s": round(elapsed_measured, 2),
        "server_latency_ms": server_latency_ms,
        "deadline_s": deadline,
        "within_deadline": elapsed_measured <= deadline if status_code else None,
        "model_used": model_used,
        "token_usage": token_usage_str,
        "safety_blocked": safety_blocked,
        "citations_removed": citations_removed,
        "error": error,
    }


def main():
    if not CASES_DIR.exists():
        print(f"ไม่เจอโฟลเดอร์ {CASES_DIR}")
        return

    case_files = sorted(CASES_DIR.glob("*.json"))
    if not case_files:
        print(f"ไม่เจอไฟล์ .json ใน {CASES_DIR}")
        return

    results = []
    for case_file in case_files:
        print(f"กำลังรัน: {case_file.name} ...")
        result = run_case(case_file)
        results.append(result)
        status = "OK" if result["status_code"] and result["status_code"] < 400 else "FAIL/4xx"
        print(
            f"  -> {status} | {result['status_code']} | "
            f"client={result['elapsed_s']}s server={result['server_latency_ms']}ms | "
            f"model={result['model_used']} | tokens={result['token_usage']}"
        )

    # สร้างตาราง markdown
    lines = [
        "# ผล Smoke Test (สร้างอัตโนมัติโดย smoke_test_runner.py)",
        "",
        f"Base URL: {BASE_URL}",
        "",
        "| เคส | Endpoint | Status | เวลาฝั่ง client (s) | latency_ms (server) | ผ่าน deadline | Model | Token usage (in/out) | Safety blocked | Citations removed | Error |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        deadline_mark = "✅" if r["within_deadline"] else ("❌" if r["within_deadline"] is False else "-")
        lines.append(
            f"| {r['case']} | {r['endpoint']} | {r['status_code']} | {r['elapsed_s']} | "
            f"{r['server_latency_ms']} | {deadline_mark} | {r['model_used']} | {r['token_usage']} | "
            f"{r['safety_blocked']} | {r['citations_removed']} | {r['error'] or '-'} |"
        )

    report = "\n".join(lines)
    print("\n" + report)

    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(f"\nบันทึกผลไว้ที่ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
