# 06 · LLM Generation

Service ด่านคุณภาพเดียว (single quality gate) ของระบบ "ผู้ช่วยฟุตบอล Premier League"
ทุกคำตอบที่ผู้ใช้เห็น ไม่ว่าจะมาจากการค้นข้อมูล (RAG), General AI, หรือ Local AI ต้องผ่าน service นี้ก่อนเสมอ

ตำแหน่งในผังระบบ:

```
User → web(01) → api(02) → router(03) ┬→ engines(04) /general, /local/*  ─┐
                                       └→ retrieval(05) /search → chunks  ├→ generation(06) /generate → คำตอบ+sources
                                                                            ┘
football-data(07) → generation(06) /report/weekly → เก็บเป็น draft → (admin publish) → upsert เข้า KB (05)
```

หน้าที่หลัก 3 อย่าง:
1. **`POST /generate` (`mode=grounded`)** — ตอบจากข้อมูลอ้างอิงพร้อม citation `[n]` ห้ามแต่งตัวเลข
2. **`POST /generate` (`mode=passthrough`)** — ปรับภาษา + ตรวจ safety ให้คำตอบจาก General AI / Local AI
3. **`POST /report/weekly`** — เขียนรายงานสรุปประจำสัปดาห์จากข้อมูลแมตช์ที่มีโครงสร้าง (เรียกโดย football-data เท่านั้น)

**ด่าน safety ทั้งระบบอยู่ที่ service นี้ที่เดียว** — ห้ามให้ทีเด็ด / อัตราต่อรอง / ชวนเล่นพนัน
**หัวใจของงาน**: ระบบต้องไม่ยอมเดาผลแข่ง — ตัวเลขสกอร์ อันดับ แต้ม วันเวลา ทุกตัวต้องมาจาก context ที่ได้รับ ไม่ใช่จากความจำของโมเดล (ดู "ตัวอย่างที่ระบบไม่ยอมเดาผล" ด้านล่าง)

---

## วิธีรัน

### แบบ dev (ไม่มี LLM key)
```bash
cd services/06_llm_generation
pip install -r requirements.txt
LLM_MOCK=true uvicorn app.main:app --reload --port 8000
```

### แบบมี key จริง (Groq หลัก / Gemini สำรอง)
```bash
export GROQ_API_KEY=...
export GEMINI_API_KEY=...
export GEMINI_MODEL=...   # ชื่อโมเดล Gemini ที่ทีมกำหนด
uvicorn app.main:app --port 8000
```

### ผ่าน docker compose (ของทีม)
```bash
make up   # ต้องขึ้นแม้ยังไม่ใส่ key จริง (health ยังตอบ ok)
```

เปิด debug ออก host ที่ port **8006** → ภายใน container ฟัง port 8000 เสมอ

---

## Endpoints + ตัวอย่าง curl

### `GET /health`
```bash
curl http://localhost:8006/health
# {"status":"ok","service":"generation","version":"0.1.0"}
```

### `POST /generate` (grounded)
```bash
curl -X POST http://localhost:8006/generate \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-1" \
  -d '{
    "mode": "grounded",
    "query": "เมื่อวานปืนใหญ่ชนะไหม",
    "language": "th",
    "contexts": [{
      "ref": 1,
      "text": "Arsenal beat Chelsea 2-1 at home.",
      "source": {"ref": 1, "doc_id": "match-2026-mw05-57-61",
        "title": "Arsenal 2-1 Chelsea", "category": "match_report",
        "origin": "football-data.org", "season": "2026", "matchweek": 5,
        "fetched_at": "2026-09-21T09:00:00+07:00"}
    }],
    "history": []
  }'
```

### `POST /generate` (passthrough)
```bash
curl -X POST http://localhost:8006/generate \
  -H "Content-Type: application/json" \
  -d '{"mode": "passthrough", "query": "", "language": "th",
       "draft": "Arsenal won 2-1 yesterday against Chelsea."}'
```

### `POST /report/weekly`
```bash
curl -X POST http://localhost:8006/report/weekly \
  -H "Content-Type: application/json" \
  -d '{
    "season": "2026", "matchweek": 5, "language": "th",
    "matches": [{
      "match_id": "m-1", "season": "2026", "matchweek": 5,
      "kickoff": "2026-09-20T18:30:00+07:00", "status": "FINISHED",
      "home": {"team_id": 57, "name": "Arsenal"},
      "away": {"team_id": 61, "name": "Chelsea"},
      "score": {"home": 2, "away": 1}, "detail_source": "none"
    }],
    "standings": [], "top_scorers": []
  }'
```

---

## Pipeline `mode=grounded` (9 ขั้น)

```
1 validate → 2 pre-safety (query) → 3 build contexts (sanitize, budget) → 4 prompt
→ 5 LLM call → 6 parse citations → 7 numeric guard (retry ≤1) → 8 post-safety → 9 map sources
```

- **Validate**: `contexts[].ref` ห้ามซ้ำ (422), `query` ห้ามว่าง, `language` นอก `{th,en}` → ใช้ `th`
- **Pre-safety**: คำขอทีเด็ด/ราคาต่อรองชัดเจน → บล็อกทันที ไม่เรียก LLM
- **Contexts ว่าง**: ตอบ "ไม่พบข้อมูลที่เพียงพอ" ทันที ไม่เรียก LLM
- **เตรียม context**: sanitize delimiter, ตรวจ prompt injection (log อย่างเดียว ไม่ตัดทิ้ง), งบ token (`MAX_CONTEXT_TOKENS`=6000) ตัด context ท้ายสุดก่อนถ้าเกิน (คง ref เดิม)
- **Citation**: normalize `[1,2]`/`【1】` → `[1][2]`, ตัด `[n]` ที่ไม่มีจริงทิ้ง (`citations_removed`), `sources` = เฉพาะที่ถูกอ้างจริง เรียงตาม ref
- **Numeric guard**: ดูหัวข้อถัดไป

## Numeric guard — กันเดาตัวเลข (จุดขายของ service)

โมดูล `app/numeric_guard.py` เป็น pure function ไม่ใช้ LLM:

| ชนิด | ตรวจ | เมื่อไม่ผ่าน |
|---|---|---|
| `score_mismatch` (hard) | สกอร์ `a-b`/`a:b` ต้องพบใน context จริง (หรือกลับด้าน) | retry 1 ครั้ง → ยังผิดแทนด้วยข้อความ insufficient |
| `number_not_in_context` (soft) | ตัวเลขอื่น (แต้ม/ประตู/ปี) ไม่พบใน context | log อย่างเดียว |

`NUMERIC_GUARD=strict|warn|off` (ค่าตั้งต้น `strict`) · กันเวลา (`18:30`), ปี/ฤดูกาล (`2026/27`), matchweek, และเลข citation `[n]` ไม่ให้ถูกมองเป็นสกอร์

## Safety (`app/safety/`)

เป้าหมาย: **ห้ามให้ทีเด็ด / อัตราต่อรอง / ชวนเล่นพนัน** — ทำแบบ rule-based (`MODERATION_ENABLED=true`)

| ชั้น | ตรวจ | ผล |
|---|---|---|
| pre-check `query` (grounded) | คำขอทีเด็ด/ราคาต่อรอง | บล็อก, `reason=gambling_request`, ไม่เรียก LLM |
| post-check `answer` (ทุกโหมด) | คำแนะนำเดิมพัน/โปรโมต/odds ที่ไม่ได้มาจาก context | บล็อก, `reason` = `gambling_tips`\|`gambling_promotion`\|`gambling_odds` |
| prompt leak | canary token หลุดในคำตอบ | บล็อก, `reason=prompt_leak` |

ข้อยกเว้น: เกร็ดประวัติที่มี odds อยู่ใน context จริง (เช่น เลสเตอร์ 5000/1) ผ่านได้ในโหมด grounded แต่ passthrough เข้มกว่าเสมอ (ไม่มี context ให้ยกเว้น)

ข้อความปฏิเสธเมื่อ `blocked=true`:
- th: "ขออภัย ระบบนี้ไม่ให้ทีเด็ด อัตราต่อรอง หรือคำแนะนำการเดิมพัน หากสนใจผลการแข่งขัน ตารางคะแนน หรือสถิติ ถามได้เลย"
- en: "Sorry, I can't provide betting tips, odds or gambling advice. I'm happy to help with match results, standings or stats."

## พฤติกรรมเมื่อ LLM ล่ม (fallback)

`LLM_PRIMARY=groq` → ล้มเหลว (timeout/429/5xx/เนื้อหาว่าง) → ลอง `LLM_FALLBACK=gemini` **1 ครั้ง** → ล่มทั้งคู่ → `503 LLM_UNAVAILABLE` (Problem-JSON) · ไม่เริ่มเรียกสำรองถ้าเวลาเหลือ < 5 วินาที (ล้มด้วย 503 ตรง ๆ ดีกว่าให้ผู้เรียก timeout) · `max_retries=0` เสมอกัน SDK retry ซ้ำเอง

---

## ตัวเลขจากสคริปต์วัดผล (D6)

รันด้วย:
```bash
LLM_MOCK=true uvicorn app.main:app --port 8006 &
python scripts/eval_generation.py --base-url http://localhost:8006 \
    --fixtures tests/fixtures --out /tmp/eval_06.json
```

> หมายเหตุ: ตัวเลขจริงต้องรันกับ provider จริง (ไม่ใช่ `LLM_MOCK`) เพื่อวัด `citation_valid_rate`, `numeric_grounded_rate`, `insufficient_correct_rate` ให้ตรงสถานการณ์จริง — ใส่ผลจากการรันจริงของทีมแทนตารางด้านล่างก่อนส่งงาน

| ตัวชี้วัด | ผล |
|---|---|
| `citation_valid_rate` | _(รันแล้วกรอกที่นี่)_ |
| `expected_source_hit_rate` | _(รันแล้วกรอกที่นี่)_ |
| `numeric_grounded_rate` | _(รันแล้วกรอกที่นี่)_ |
| `insufficient_correct_rate` | _(รันแล้วกรอกที่นี่)_ |
| `safety_block_rate` | _(รันแล้วกรอกที่นี่)_ |
| `latency p50/p95` | _(รันแล้วกรอกที่นี่)_ |

---

## วิธีรันเทส

```bash
LLM_MOCK=true pytest tests/ -q     # ไม่ต้องมี key ไม่ต้องต่อเน็ต
ruff check app/ tests/
```

> หมายเหตุ: ยังไม่มีเทสที่ทำเครื่องหมาย `@pytest.mark.live` สำหรับยิง provider จริงในโค้ดชุดนี้ (ดูหัวข้อ "ข้อจำกัดที่รู้อยู่")

---

## ตัวอย่าง 3 เคสที่ระบบไม่ยอมเดาผล (สำหรับนำเสนอ)

1. **ถามผลนัดที่ context ไม่มี** — "ลิเวอร์พูลนัดล่าสุดเจอใคร" โดย context มีแต่ข้อมูล Arsenal vs Chelsea
   → ระบบตอบ "ไม่พบข้อมูลที่เพียงพอในคลังข้อมูลเพื่อตอบคำถามนี้" พร้อม `sources: []` แทนที่จะเดาคู่แข่งขัน

2. **LLM แต่งสกอร์ผิดจาก context** — context ระบุ Arsenal 2-1 Chelsea แต่โมเดลตอบ 3-0
   → `numeric_guard` (hard, `score_mismatch`) จับได้ทันที, สั่ง retry 1 ครั้งพร้อมข้อความเตือนตรง ๆ ว่าตัวเลขไหนผิด ถ้ายังผิดซ้ำ ระบบแทนที่คำตอบด้วยข้อความ "ไม่พบข้อมูลที่เพียงพอ" แทนการปล่อยเลขที่แต่งขึ้นออกไป

3. **นัดที่ยังไม่แข่ง (SCHEDULED)** — context ระบุสถานะ `SCHEDULED` สำหรับนัดสัปดาห์หน้า
   → prompt (กฎข้อ 7) และการตรวจ status บังคับให้ระบบไม่เล่าเป็นผลที่จบแล้วหรือทำนายผล แม้ผู้ใช้จะถามว่า "ใครชนะ"

---

## Env ทั้งหมด (ทุกตัวมีค่าตั้งต้นในโค้ด ไม่บังคับต้องตั้ง)

| ตัวแปร | ค่าตั้งต้น |
|---|---|
| `LLM_PRIMARY` / `LLM_FALLBACK` | `groq` / `gemini` |
| `GROQ_API_KEY`, `GROQ_MODEL` | – / `openai/gpt-oss-120b` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | – / (ตามที่ทีมกำหนด) |
| `GROQ_BASE_URL`, `GEMINI_BASE_URL` | ตาม contract 4.5 |
| `LLM_MOCK` | `false` |
| `MAX_OUTPUT_TOKENS` / `REPORT_MAX_OUTPUT_TOKENS` | `1500` / `3500` |
| `TEMPERATURE_GROUNDED` / `_PASSTHROUGH` / `_REPORT` | `0.2` / `0.2` / `0.4` |
| `REASONING_EFFORT` | `low` |
| `GENERATE_DEADLINE_S` / `REPORT_DEADLINE_S` | `22` / `55` |
| `MAX_CONTEXT_TOKENS` / `CONTEXT_CHAR_LIMIT` | `6000` / `2500` |
| `MODERATION_ENABLED` | `true` |
| `NUMERIC_GUARD` | `strict` |
| `PII_MASKING` / `LLM_MODERATION` | `false` / `false` |
| `LOG_LEVEL` | `INFO` |
| `SERVICE_VERSION` / `GIT_SHA` | `0.1.0` |

---

## ข้อจำกัดที่รู้อยู่ / งานที่ยังไม่ได้ทำ

- Phase F (Could): ยังไม่ทำ PII masking แบบเปิดใช้จริง, LLM moderation, cooldown 429
- `scripts/eval_generation.py` ยังคำนวณเฉพาะ `citation_valid_rate`, `safety_block_rate`, `latency` — ยังไม่ครบ `expected_source_hit_rate` / `numeric_grounded_rate` / `insufficient_correct_rate` (ต้องเพิ่ม field คาดหวังในแต่ละ fixture ก่อน)
- fixtures ยังไม่ครบ 14 ชุดตามหัวข้อ 15.1 (มี 8 ชุด: trivia_1, trivia_2, match_1, match_2, insufficient_1, injection_ctx, gambling_query, historical_odds_ok) — ที่เหลือ (`insufficient_calc`, `followup_history`, `bad_citation`, `scheduled_match`, `passthrough_*`, `weekly_*`) ยังไม่ได้เขียน
- ยังไม่ได้ยิงทดสอบกับ provider จริง (Groq/Gemini) ด้วยมือ — ต้องมี `GROQ_API_KEY`/`GEMINI_API_KEY` ของสมาชิกก่อน
- CI ของโมดูล (GitHub Actions) ยังไม่มี — อยู่นอกขอบเขตไฟล์ที่ 06 แก้ได้เอง (`.github/` เป็นของหัวหน้า/member6 ตามกฎเหล็ก 3.1) ต้องขอให้ทีมเพิ่ม workflow ที่รัน `LLM_MOCK=true pytest tests/ -q` และ `ruff check app/ tests/` บน push/PR ของ `services/06_llm_generation/**`

---

## แก้ไขตามรีวิว PR #11

- แก้ path template (`grounded.py`, `passthrough.py`, `weekly.py`) จากการตัด string ด้วย `/app/` เป็น `Path(__file__).resolve().parents[2] / "prompts"` เพื่อให้โหลด template ได้ทั้ง Windows และ Linux/CI
- `Match.lineups` / `Match.statistics` ใน `schemas.py` รับได้ทั้ง `dict` และ `list` (07/api-football ส่งเป็น list) กัน `/report/weekly` ตอบ 422 เมื่อมีรายละเอียดแมตช์ครบ พร้อมเทส `test_weekly_report_accepts_list_lineups_and_statistics`
- `grounded.py` เก็บสกอร์จาก context ด้วย `numeric_guard.find_score_claims` (เดิมใช้ `re.search` ได้แค่คู่แรกต่อ chunk) กันคำตอบที่อ้างสกอร์คู่ที่สองในรายงานสัปดาห์เดียวกันถูกมองว่าผิดแล้วแทนด้วย insufficient ผิด ๆ พร้อมเทส `tests/test_grounded_pipeline.py`
- ย้ายโครง service มาไว้ใต้ `services/06_llm_generation/` ให้ตรงกับ `GIT_FLOW` และคำสั่งใน README เอง (เดิมอยู่ผิดตำแหน่ง)
- `app/llm/mock.py` (`_respond_translate`) แก้ regex ดึงเนื้อ `<draft>` — เดิม `<draft>\s*(.*?)\s*</draft>` จับ match ผิดตำแหน่งเพราะคำว่า `<draft>` โผล่ซ้ำในประโยคคำสั่งของ template เอง (`"แปลข้อความใน <draft> เป็นภาษา..."`) ทำให้ mock คืนทั้งก้อน system prompt ปนมากับ draft แทนที่จะคืนแค่ draft พบจากการรัน `LLM_MOCK=true` ทดสอบ passthrough translate จริงแล้วคำตอบเพี้ยน แก้เป็น `<draft>\n(.*?)\n</draft>` (บังคับให้ตามด้วยขึ้นบรรทัดใหม่ทันที ตรงกับที่ template ห่อจริง) พร้อมเทส `test_passthrough_translate_extracts_draft_not_whole_prompt`