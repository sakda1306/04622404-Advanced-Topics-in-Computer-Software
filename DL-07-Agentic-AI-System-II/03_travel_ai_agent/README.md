# งาน 03 — Travel AI Agent

ต้นแบบของงาน 03 ตาม `01_env.txt`, `02_step.txt` และ `03_process.txt` ทำหน้าที่รับคำขอจาก Module 02 วางแผนว่าจะเรียก tool ใด เรียก tool ตามลำดับ รวมหลักฐาน แล้วส่งต่อให้ Module 07 เป็นผู้ตัดสิน

**Agent ไม่ตัดสินระดับความปลอดภัยหรือ action เอง** ขั้นตอนนี้เป็นหน้าที่ของกฎใน Module 07 ส่วน agent ทำหน้าที่รวบรวมหลักฐานและประสานงานเท่านั้น

## สถานะรุ่นนี้ (ขั้นที่ 1)

| ส่วน | สถานะ |
|---|---|
| API ให้ 02 เรียก `POST /v1/agent/runs` | ✅ ตาม contract ใน `02_api_backend/docs/02_api_spec.md` §9 |
| Progress แบบ NDJSON / ยกเลิก run ด้วย `DELETE` / `X-Deadline` | ✅ |
| เรียก Module 07 ตัวจริง (`POST /v1/decisions`) | ✅ เทสกับ engine ของ 07 ตัวจริงแบบ in-process |
| Module 04 | 🟡 `transport()` ใช้ TomTom จริง และ `disasters()` ใช้ GDACS จริง; weather/route candidates ยังเป็น mock |
| Module 05 | ✅ เรียก `build_context()` จริงด้วย canonical records จาก 04 |
| Module 06 | ✅ เรียก `RiskKnowledgeService` จริงแบบ in-process และตรวจ output ด้วย contract ของ 03 |
| ส่งต่อ emergency instructions จาก 07 ไป 02 | ✅ ส่งต่อตามเดิมทุกตัวอักษร ไม่แก้ข้อความเอง |
| จำกัด step, tool call และเวลา / ให้ tool ที่ล้มไม่ล้มทั้ง run | ✅ |
| Intent และ planner ด้วย LLM, LangGraph, checkpoint สำหรับคำถามต่อ | ⏳ ขั้นถัดไป ตอนนี้ใช้ `intent_hint` จาก 02 และลำดับ tool ที่กำหนดไว้ตายตัว |
| คำแนะนำฉุกเฉินเฉพาะพื้นที่ | ⏳ 07 ยังตอบชุด fallback เพราะยังไม่มีใครส่ง region ที่ยืนยันแล้วให้ 03 |

## ลำดับการทำงานของหนึ่ง run

```
understand ─▶ fetch_external ─────▶ integrate ─▶ assess ─────────────▶ decide ─▶ finish
 (intent,      weather ┐            (05)         risk → knowledge →    (07)
  ถามกลับ)     transport├ ขนาน                    routes (06)
               disasters│ (04)
               route_candidates┘
                    │
                    └▶ 03 คำนวณ enter_at/exit_at ของแต่ละช่วงจาก departure_time + duration ของ 04
```

- **เส้นทางเป็นของ 04** (`RouteCandidate` ตาม `04/02_step.txt`) ส่ง geometry กับ duration ต่อ leg มา ส่วน 03 เป็นคนใส่เวลาเข้าไป เพราะ 03 ถือ `departure_time` ที่ normalize แล้ว
- **ผลของ 05 ส่งต่อให้ 06 ทั้งก้อน** ไม่ย่อ เพราะ 06 ใช้ `segments`, `coverage` และ `evidence` ในการให้คะแนน (06 รองรับทั้งรูปแบบละเอียดและแบบย่ออยู่แล้ว)

- ถ้าข้อมูลสำคัญผิดหรือขาด เช่น ต้นทางกับปลายทางเป็นจุดเดียวกัน หรือเวลาออกเดินทางผ่านไปแล้ว agent จะตอบ `needs_clarification` และไม่เดาเอง
- ถ้า tool ใดล้ม, timeout หรือส่งข้อมูลที่ไม่ผ่าน schema service นั้นจะถูกบันทึกเป็น `unavailable` แล้ว run ทำงานต่อ ผลลัพธ์จะเป็น `partial_result` และ 07 จะไม่ถือว่าข้อมูลที่ขาดหมายถึงปลอดภัย
- ถ้า 07 ใช้งานไม่ได้ จะตอบ `503 DECISION_UNAVAILABLE` เพราะไม่มีคำแนะนำที่ใช้ได้ให้ส่งกลับ

## ข้อมูลที่ต้องตกลงกับทีม

- **02 (sakda):** `travel_agent/contracts.py` คัดลอกมาจาก contract ของ 02 ถ้าฝั่งไหนแก้ ต้องแก้อีกฝั่งด้วย
- **04 / 05 / 06:** `travel_agent/tools/schemas.py` เป็น**ร่าง** contract ที่ 03 เสนอ ทุก record ต้องมี `source`, `url` (https), `observed_at`, `fetched_at` และ `expires_at` ตามที่ 07 บังคับ
- **04 (supawit):** ต้องผลิต `RouteCandidate` (geometry LineString + duration ต่อ leg) และ record ที่มี `observed_at`/`expires_at` ครบ เพราะ 07 บังคับลำดับ `observed_at <= fetched_at < expires_at` ส่วนพยากรณ์ที่มีแต่ `valid_at` ยังส่งเข้า 07 ไม่ได้จนกว่าจะตกลงกัน
- **05 (supawit):** 03 ส่ง `routes` พร้อม `enter_at`/`exit_at` และ canonical records เข้า `build_context()` แล้ว จากนั้นส่ง context ต่อให้ 06 ทั้งก้อน; `confidence` กับ `active_restriction` ยังต้องตกลงร่วมกัน
- **07 (mekmai):** `confidence` ของ 07 เป็นคะแนนของนโยบาย ไม่ใช่ความมั่นใจของค่าความเสี่ยง 03 จึงส่ง `risk.confidence` ให้ 02 จากค่าของ **06** (ตัวเลข 0–1 ตั้งแต่ 2026-09-21) ซึ่งตรงความหมายกับที่ 02 ใช้เตือนเมื่อต่ำกว่า 0.5 ส่วนคะแนนนโยบายของ 07 ยังไม่ได้ส่งต่อ; `emergency_contact_metadata` ยังไม่มีช่องรับใน contract ของ 02

## เริ่มใช้งานด้วย Python

ต้องมี Python 3.12 ขึ้นไปและ `uv` รันจากโฟลเดอร์นี้:

```powershell
uv sync
Copy-Item .env.example .env
# ใส่ TOMTOM_API_KEY ใน .env; GDACS ไม่ต้องใช้ key
uv run pytest
```

รัน 07 และ 03 พร้อมกัน (เปิด PowerShell 2 หน้าต่างจากโฟลเดอร์นี้):

```powershell
uv run uvicorn decision_engine.api:app --port 8050   # Module 07
uv run uvicorn travel_agent.api:app --port 8010      # Module 03
```

เปิดดู [API docs](http://localhost:8010/docs) แล้วลองส่ง request ตามตัวอย่างใน `tests/conftest.py` (`run_body`) หากต้องการทดสอบแบบจำลองทั้งหมดให้ตั้ง `USE_MOCK_TOOLS=true`; `request.preferences.mock_scenario` รองรับ `low_risk`, `high_risk`, `closure`, `safer_route`, `safer_time` และ `weather_down`

port 8010 ตรงกับค่าเริ่มต้นของ `AGENT_SERVICE_URL` ใน Module 02

## เริ่มใช้งานด้วย Docker Compose

```powershell
docker compose up --build -d
```

`compose.yaml` จะเปิด 03 พร้อม 07 container รันด้วย user ที่ไม่ใช่ root, เป็น read-only และตัด capability ทั้งหมด

## โครงสร้าง

```
travel_agent/
├── api.py          # FastAPI: POST/DELETE /v1/agent/runs, /health, /ready
├── pipeline.py     # AgentState + node ต่าง ๆ + การเรียก tool ที่มี budget/timeout
├── evidence.py     # สร้าง DecisionRequest ให้ 07
├── routes.py       # แปลง RouteCandidate ของ 04 เป็น segments พร้อมเวลาให้ 05
├── response.py     # แปลงผลของ 07 เป็น AgentRunResponse ให้ 02
├── contracts.py    # contract 02 ↔ 03
├── budget.py       # จำกัด step/tool call + AgentError
├── config.py       # ค่าจาก .env
└── tools/
    ├── base.py     # allowlist ของ tool + ToolSet interface
    ├── schemas.py  # ร่าง contract ของ 04/05/06
    ├── live.py     # adapter ของ transport/disaster (04), integration (05) และ risk/knowledge/routes (06) ตัวจริง
    ├── mocks.py    # ข้อมูลจำลองของ 04/05/06
    └── decision.py # HTTP client ของ 07 (retry ด้วย Tenacity)
```
