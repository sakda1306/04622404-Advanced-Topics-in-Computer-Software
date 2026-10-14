# CONTRACT.md — ข้อตกลง API ระหว่าง service · ผู้ช่วยฟุตบอล · v1.16

> **กฎเหล็ก**: แก้ไฟล์นี้ได้ผ่าน PR เท่านั้น ต้องได้ approve จากหัวหน้า (sakda1306) + เจ้าของ service ทั้งสองฝั่งที่เกี่ยวข้อง
> เพิ่ม field ใหม่แบบ optional ได้ (ไม่ทำให้คนอื่นพัง) แต่ **ห้ามลบ / เปลี่ยนชื่อ / เปลี่ยนความหมาย field** โดยไม่ bump version และแจ้งในกลุ่ม
> stub ของทุก service (หัวหน้า + member6 ทำให้ใน D1) ต้องตอบตามไฟล์นี้เป๊ะ

| § | ฝั่งเรียก → ฝั่งถูกเรียก | เจ้าของฝั่งถูกเรียก |
|---|---|---|
| 1 | web → api | sakda1306 |
| 1.1 | web → api (admin, `/api/admin`) | sakda1306 |
| 2 | api → router | member2 |
| 3 | router → engines | member3 |
| 4 | router → retrieval | sakda1306 |
| 5 | router / football-data → generation | member4 |
| 6 | football-data → retrieval (index) | sakda1306 |
| 7 | api → football-data | member5 |
| 8 | LLM provider (ใช้ร่วม) | – |

---

## 0. กติการ่วมทุก service

- Content-Type: `application/json; charset=utf-8` (ภาษาไทยต้องไม่เพี้ยน)
- Header **`X-Request-ID`**: ถ้าไม่มีให้สร้าง UUID แล้ว **ส่งต่อทุกครั้ง** ที่เรียก service อื่น และใส่ใน log ทุกบรรทัด (log เป็น JSON หนึ่งบรรทัดต่อ event)
- **`GET /health`** → `200 {"status":"ok","service":"<ชื่อใน compose>","version":"<git-sha หรือ 0.1.0>"}` · ทุก service ต้องมี
- **Error ทุกกรณีตอบรูปแบบเดียว** (Problem-JSON แบบเดียวกับ backend Travel Safety) + HTTP status ที่ถูกต้อง
  ```json
  {
    "type": "https://errors.football-assistant.local/router-timeout",
    "title": "Router timed out",
    "status": 504,
    "code": "ROUTER_TIMEOUT",
    "detail": "คำอธิบายสั้นภาษาไทย",
    "service": "api",
    "request_id": "uuid"
  }
  ```
  Content-Type ของ error = `application/problem+json`
- **Timeout** (ฝั่งเรียกเป็นคนตั้ง):

  | hop | timeout |
  |---|---|
  | web → api | 60s |
  | api → router | 45s |
  | router → retrieval | 10s |
  | router → engines / generation | 25s |
  | football-data → generation (`/report/weekly`) | 60s |
  | football-data → API ภายนอก | 10s · retry 2 ครั้ง (backoff 1s, 3s) |

- **งบเวลารวมใน router ≤ 40 วินาที** (ต่ำกว่า 45s ที่ api รอไว้ 5 วินาที) · timeout ต่อ hop ข้างบนเป็นเพดานต่อ hop ไม่ใช่งบรวม · ขั้นเรียก LLM เพิ่ม (rewrite / แปล) ตั้ง ≤ 8s และนับรวมในงบ
- เวลา: ISO-8601 เขต Asia/Bangkok เช่น `2026-09-21T09:00:00+07:00` · วันแข่งเก็บเป็นเวลา `+07:00` ด้วย
- ID ของเราเป็น UUID string · id จากแหล่งภายนอกเก็บเป็น field แยก (`external_ids`)
- **ฤดูกาล** เขียนด้วยปีที่เริ่ม เช่น ฤดูกาล 2026/27 = `"2026"` (ตรงกับ football-data.org)
- **ทีม** อ้างด้วย `team_id` = id ของ football-data.org เสมอ (07 เป็นคน map id ของ API-Football ให้)
- **`confidence`** = ความมั่นใจของ **router ต่อการเลือก route** เท่านั้น ไม่ใช่ความมั่นใจว่าคำตอบถูก · ชั้น rules = 0.9 · ชั้น classifier = score ของโมเดล · ชั้น LLM = ค่าที่ LLM คืน · ไหลถึงหน้าเว็บโดยไม่แปลงความหมาย
- Service ภายในคุยกันใน docker network เท่านั้น ไม่เปิด auth ระหว่างกัน (port debug เปิดเฉพาะเครื่อง dev)

## Object ที่ใช้ร่วม

```jsonc
// Source — ใช้ทุกที่ที่มีการอ้างอิง
{
  "ref": 1,                                   // เลขที่อ้างใน answer เป็น [1]
  "doc_id": "match-2026-mw05-57-61",          // ดูรูปแบบ doc_id ใน §6
  "title": "Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5",
  "category": "match_report",                 // ดู enum ข้างล่าง
  "origin": "football-data.org",              // kb | football-data.org | api-football | generated
  "season": "2026",                            // null ได้ (trivia)
  "matchweek": 5,                              // null ได้
  "team_ids": [57, 61],                        // [] ได้
  "fetched_at": "2026-09-21T09:00:00+07:00",  // null สำหรับ trivia
  "url": null
}

// TokenUsage
{ "input": 0, "output": 0 }

// Trace — optional แต่ทุกคนบนเส้นทางต้องส่งต่อ หน้าเว็บใช้โชว์ว่า agent ตัดสินใจยังไง
{
  "decided_at_layer": "rules",                // guard | rules | classifier | llm
  "intent": "match_result",
  "rewritten_query": "Arsenal latest match result",   // null ถ้าไม่ได้ rewrite
  "standalone_query": "ใครยิงประตูให้ลิเวอร์พูลในนัดเมื่อวาน",  // v1.8 · null ถ้าไม่ได้ condense หรือไม่ได้ใช้ผล
  "condense": "applied",                       // v1.8 · null | "applied" | "unchanged" | "rejected" | "unavailable" · ไม่นับเป็น fallback
  "search_query_en": "Did Arsenal win yesterday?",   // v1.9 · null ถ้าไม่ได้ค้นด้วยคำค้นอังกฤษ
  "multi_query": "applied",                    // v1.9 · null | "applied" | "rejected" | "unavailable" · ไม่นับเป็น fallback
  "chat": null,                                // v1.12 · null | "applied" | "rejected" | "unavailable" · ไม่นับเป็น fallback · มีค่าเฉพาะ route `chat`
  "filters": { "category": ["match_report"], "team_ids": [57] },
  "fallback": null,                            // null หรือค่าหนึ่งในตาราง "ค่าของ trace.fallback" ด้านล่าง (v1.10)
  "record_search": [61, 57],                   // v1.15 · ทีมที่ค้นสรุปสถิติแยกได้ chunk · "unavailable" เมื่อค้นแยกล้มทุกทีม · ไม่มี field นี้เมื่อไม่ได้ค้นแยก
  "steps": [
    { "name": "router.rules",        "ms": 3 },
    { "name": "retrieval.search",    "ms": 140 },
    { "name": "generation.grounded", "ms": 1520 }
  ]
}

// HistoryMessage
{ "role": "user | assistant", "content": "..." }
```

**enum ที่ล็อกแล้ว**

- `route`: `football_rag` | `general_ai` | `local_ai` | `clarify` | `decline` | `chat` (v1.12)
- `category` (ของเอกสาร): `trivia` | `match_report` | `standings` | `fixtures` | `weekly_report` | `player` | `historical` (v1.11)
- `origin`: `kb` | `football-data.org` | `api-football` | `generated` (เอกสารที่ LLM เขียน เช่น weekly report) | `openfootball` | `fjelstul` (v1.11 คลังย้อนหลังของ 07) · `wikidata` (v1.16 โค้ชคนปัจจุบันของ 07, CC0)
- `topic` ของ `historical` (v1.11): `season_table` | `team_season` | `head_to_head` · (v1.13) `club_record` | `league_records`

**ป้ายภาษาไทยบนหน้าเว็บ** (ห้ามโชว์ enum ดิบ):
`football_rag` → "ตอบจากคลังข้อมูลฟุตบอล" · `general_ai` → "ความรู้ทั่วไป" · `local_ai` → "โมเดลทำนาย" · `clarify` → "ขอข้อมูลเพิ่ม" · `decline` → "นอกขอบเขต" · `chat` → "คุยกับผู้ช่วย" (v1.12)

**ค่าของ `trace.fallback`** (v1.10 รวบรวมค่าที่ router ใช้อยู่จริง · ค่าเดียวต่อคำตอบ · หน้า admin นับเป็น `fallback_count`)

| ค่า | ตั้งเมื่อ |
|---|---|
| `retrieval_empty` | `/search` ไม่คืน chunk ทั้งรอบแรกและรอบที่ตัด filter `matchweek`/`date_*` (§3 ลำดับถอย) |
| `retrieval_down` | `/search` error, timeout หรือ `INDEX_NOT_READY` |
| `classifier_down` | `/local/classify` ล่มหรือคืนค่าที่อ่านไม่ได้ → ไปชั้น LLM |
| `llm_fallback_provider` | ชั้น LLM ของ router ใช้ provider สำรองแทน provider หลัก (§8) |
| `llm_unavailable` | ชั้น LLM ของ router ใช้ไม่ได้ทั้งสอง provider หรือเกิน 8s → ถาม clarify |
| `general_down` | `/general` ล่ม → ตอบ "ตอนนี้ระบบไม่ว่าง…" |
| `generation_down` | `/generate` ล่ม → ตอบ "ตอนนี้ระบบไม่ว่าง…" (ไม่ส่ง draft ที่ยังไม่ผ่าน guard) |
| `simulation_down` | ทำนายผล/จำลองฤดูกาลจาก 07 ไม่ได้ (v1.7) |
| `prediction_needs_team` | คำถามทำนายไม่บอกทีมพอ → ถามกลับ (v1.7) |
| `prediction_team_not_found` | 07 หาทีมที่ขอทำนายไม่เจอ (404) (v1.7) |
| `historical_scorer_unavailable` | แหล่งดาวซัลโวย้อนหลังที่ยืนยันแล้ว (07) ล่มหรือไม่มีฤดูกาลนั้น |
| `historical_scorer_invalid` | ข้อมูลดาวซัลโวย้อนหลังที่ได้ไม่ตรงฤดูกาลที่ถาม |
| `router_timeout` | เกินงบ 40s ของ router (ต่างจาก error `ROUTER_TIMEOUT` ที่ api ตอบเมื่อ router เกิน 45s) |

`trace.condense` (v1.8), `trace.multi_query` (v1.9) และ `trace.chat` (v1.12) เป็นสถานะของขั้นช่วย ไม่ใช่ fallback และไม่นับใน `fallback_count`

---

## 1. web → api (public, prefix `/api`)

auth ใช้ httpOnly cookie ชื่อ `access_token` (JWT HS256, อายุ 8 ชม.) · web เรียก api ผ่าน server-side proxy ของ Next.js

| Method | Path | Request | Response 200 |
|---|---|---|---|
| POST | `/api/auth/login` | `{username, password}` | `{user: User}` + set cookie |
| POST | `/api/auth/logout` | – | `{ok: true}` |
| GET | `/api/auth/me` | – | `{user: User}` หรือ 401 |
| PATCH | `/api/me/preferences` | `{favorite_team_id: 57 \| null, language: "th" \| "en"}` | `{user: User}` |
| POST | `/api/chat` | `ChatRequest` | `ChatResponse` |
| GET | `/api/sessions` | – | `{sessions: [{session_id, title, updated_at}]}` |
| GET | `/api/history/{session_id}` | `?limit=50` | `{session_id, messages: [Message]}` · 404 ถ้าไม่ใช่ของผู้ใช้คนนี้ |
| POST | `/api/feedback` | `{message_id, rating: 1 \| -1, comment?}` | `{ok: true}` |
| GET | `/api/football/standings` | `?season=` (default ฤดูกาลปัจจุบัน) | ส่งต่อจาก §7 |
| GET | `/api/football/fixtures` | `?season=&matchweek=&team_id=&status=` | ส่งต่อจาก §7 |
| GET | `/api/football/matches/{match_id}` | – | ส่งต่อจาก §7 |
| GET | `/api/football/reports/weekly` | `?season=&matchweek=` (ไม่ใส่ = ล่าสุด) | ส่งต่อจาก §7 · **เฉพาะรายงานที่ `published` เท่านั้น** |
| GET | `/api/football/status` | – | `{current_season, current_matchweek, last_ingest_at, quota}` |
| GET | `/api/football/predict` | `?home_team_id=&away_team_id=` (≥1, ต่างกัน) | ส่งต่อจาก §7 `/football/predict` · cache 5 นาที (v1.7) |
| GET | `/api/football/simulation` | `?season=` (ไม่ใส่ = ปัจจุบัน) | ส่งต่อจาก §7 `/football/simulation` (`SimulationSnapshot`) · cache 5 นาที (v1.7) |

```jsonc
// User
{ "id": "uuid", "username": "demo1", "display_name": "Demo 1", "role": "user | admin",
  "favorite_team_id": 57, "language": "th" }

// ChatRequest
{ "session_id": "uuid หรือ null (null = เริ่มบทสนทนาใหม่)", "message": "เมื่อวานปืนใหญ่ชนะไหม" }

// ChatResponse
{
  "request_id": "uuid", "session_id": "uuid", "message_id": "uuid",
  "answer": "markdown พร้อม [1] [2]",
  "sources": [ Source ],
  "route": "football_rag", "engines_used": ["retrieval", "generation"],
  "confidence": 0.9, "latency_ms": 2100,
  "data_as_of": "2026-09-21T09:00:00+07:00",   // fetched_at ที่เก่าที่สุดใน sources ที่เป็นข้อมูลสด · null ถ้าไม่มี
  "created_at": "...",
  "trace": Trace
}

// Message (ใน history)
{ "message_id": "uuid", "role": "user | assistant", "content": "...", "sources": [], "route": "football_rag",
  "rating": 1, "created_at": "..." }

// Stats — ใช้ที่ GET /api/admin/stats (§1.1)
{ "days": 7, "total_messages": 0, "by_route": { "football_rag": 0 }, "by_layer": { "rules": 0 },
  "feedback": { "up": 0, "down": 0 }, "latency_ms": { "p50": 0, "p95": 0 }, "fallback_count": 0 }
```

- api เป็นคนบันทึก log / history / feedback เอง (package `app/response_log` — ไม่ใช่ service แยก) · บันทึกหลังตอบผู้ใช้แบบ background task ห้ามทำให้คำตอบช้า
- **feedback ที่มาถึงก่อน log บันทึกเสร็จ** → api รอ log ของ `message_id` นั้นได้ไม่เกิน 3 วินาที ถ้ายังไม่มีตอบ 409 `MESSAGE_NOT_READY` (web retry 1 ครั้ง)
- rate limit `/api/chat`: 20 ครั้ง/นาที/ผู้ใช้ → 429 `RATE_LIMITED` พร้อม header `Retry-After`

| code | status | เมื่อไร |
|---|---|---|
| `UNAUTHENTICATED` | 401 | ไม่มี/หมดอายุ cookie |
| `VALIDATION_ERROR` | 422 | message ว่าง หรือยาวเกิน 2000 ตัวอักษร |
| `NOT_FOUND` | 404 | session / message ไม่มี หรือไม่ใช่ของผู้ใช้ |
| `RATE_LIMITED` | 429 | เกินโควตา |
| `ROUTER_UNAVAILABLE` | 502 | router ตอบ error หรือ circuit breaker เปิด |
| `ROUTER_TIMEOUT` | 504 | router เกิน 45s |
| `FOOTBALL_DATA_UNAVAILABLE` | 502 | 07 ล่ม (เฉพาะ `/api/football/*`) |
| `SIMULATION_UNAVAILABLE` | 503 | 07 ทำนาย / จำลองไม่ได้ (04 ล่มและไม่มีผลเก่า) · ส่งผ่านจาก 07 (v1.7) |

## 1.1 web → api — ระบบ Admin (prefix `/api/admin`)

**สิทธิ์**: ทุก path ใน §1.1 ต้องมี cookie ที่ `user.role = "admin"` · ไม่ใช่ admin → `403 FORBIDDEN` · web แสดงเมนู `/admin/*` เฉพาะ admin แต่ **api ตรวจสิทธิ์เองทุกครั้ง** (ห้ามเชื่อหน้าเว็บ)
**web เรียกได้แค่ api** — ห้ามเรียก service ภายในตรง · 02 เป็นคนส่งต่อไป 05 / 07
**audit**: ทุก request ที่ไม่ใช่ `GET` บันทึก `AuditEntry` ก่อนตอบ (บันทึกไม่สำเร็จ = action ไม่สำเร็จ ตอบ 500)
**ระดับ**: Must = Dashboard, Pipeline, Feedback & Log · Should = ตรวจรายงาน, Audit · Could = ผู้ใช้, Knowledge Base

| ระดับ | Method | Path | Request | Response 200 | ส่งต่อไปที่ |
|---|---|---|---|---|---|
| Must | GET | `/api/admin/stats` | `?days=7` | `Stats` | – (ข้อมูลใน 02) |
| Must | GET | `/api/admin/pipeline` | – | `{status: <GET /football/status>, jobs: [Job]}` (20 job ล่าสุด) | 07 `/football/status`, `/jobs` |
| Must | POST | `/api/admin/pipeline/ingest` | `{scope: "fixtures" \| "details" \| "all"}` | `202 {job_id, scope}` | 07 `/ingest/run` |
| Must | POST | `/api/admin/reports/generate` | `{season?, matchweek?}` | `202 {job_id}` | 07 `/reports/weekly/run` |
| Must | GET | `/api/admin/jobs/{job_id}` | – | `Job` | 07 `/jobs/{job_id}` |
| Must | GET | `/api/admin/feedback` | `?rating=-1&days=7&route=&limit=50&cursor=` | `{items: [FeedbackItem], next_cursor}` | – |
| Must | GET | `/api/admin/messages/{message_id}` | – | `AdminMessage` | – |
| Must | GET | `/api/admin/logs` | `?request_id=&route=&fallback=&days=1&limit=50&cursor=` | `{items: [LogItem], next_cursor}` | – |
| Should | GET | `/api/admin/reports` | `?status=draft\|published\|unpublished&season=` | `{items: [WeeklyReport]}` | 07 `/reports/weekly/list` |
| Should | GET | `/api/admin/reports/{season}/{matchweek}` | – | `WeeklyReport` (ทุกสถานะ) | 07 |
| Should | PATCH | `/api/admin/reports/{season}/{matchweek}` | `{title?, markdown?}` | `WeeklyReport` · แก้ได้เฉพาะ `draft` / `unpublished` (อื่น ๆ → 409 `REPORT_NOT_EDITABLE`) | 07 |
| Should | POST | `/api/admin/reports/{season}/{matchweek}/publish` | – | `WeeklyReport` (`status: published`) | 07 → 05 upsert |
| Should | POST | `/api/admin/reports/{season}/{matchweek}/unpublish` | – | `WeeklyReport` (`status: unpublished`) | 07 → 05 delete |
| Should | GET | `/api/admin/audit` | `?actor_id=&action=&days=7&limit=50&cursor=` | `{items: [AuditEntry], next_cursor}` | – |
| Could | GET | `/api/admin/users` | `?q=&limit=50&cursor=` | `{items: [AdminUser], next_cursor}` | – |
| Could | PATCH | `/api/admin/users/{user_id}` | `{role?: "user" \| "admin", disabled?: bool}` | `AdminUser` · **แก้ตัวเองไม่ได้** → 409 `CANNOT_MODIFY_SELF` | – |
| Could | GET | `/api/admin/kb/stats` | – | `<GET /index/stats>` | 05 |
| Could | DELETE | `/api/admin/kb/documents/{doc_id}` | – | `{deleted: bool}` · ห้ามลบ `trivia-*` ทีละมาก (ลบทีละ doc เท่านั้น) | 05 `/index/{doc_id}` |
| Could | POST | `/api/admin/kb/reindex` | `{category?: "trivia" \| ...}` | `202 {job_id}` | 05 `/index/rebuild` |

```jsonc
// FeedbackItem
{ "message_id": "uuid", "rating": -1, "comment": "ผลผิด", "created_at": "...",
  "user": { "id": "uuid", "username": "demo1" },
  "question": "ข้อความผู้ใช้ก่อนหน้าคำตอบนี้", "answer_preview": "120 ตัวอักษรแรก",
  "route": "football_rag", "fallback": null }

// AdminMessage — ทุกอย่างของคำตอบหนึ่งข้อ ใช้ไล่ว่าผิดตรงไหน
{ "message_id": "uuid", "request_id": "uuid", "session_id": "uuid",
  "user": { "id": "uuid", "username": "demo1" },
  "question": "...", "answer": "...", "sources": [ Source ],
  "route": "football_rag", "confidence": 0.9, "reasoning": "...",
  "trace": Trace, "token_usage": TokenUsage, "latency_ms": 2100,
  "rating": -1, "comment": "ผลผิด", "created_at": "..." }

// LogItem
{ "request_id": "uuid", "message_id": "uuid", "user_id": "uuid", "route": "football_rag",
  "decided_at_layer": "rules", "fallback": null, "status": 200, "error_code": null,
  "latency_ms": 2100, "created_at": "..." }

// Job (มาจาก 07 ตรง ๆ)
{ "job_id": "uuid", "kind": "ingest | weekly_report", "scope": "fixtures", "status": "queued | running | done | failed",
  "triggered_by": "beat | admin:<user_id>", "started_at": "...", "finished_at": "...", "detail": null }

// AuditEntry
{ "audit_id": "uuid", "actor": { "id": "uuid", "username": "admin" },
  "action": "pipeline.ingest | report.generate | report.edit | report.publish | report.unpublish | user.update | kb.delete | kb.reindex",
  "target": "weekly-2026-mw05", "detail": { "before": {}, "after": {} },
  "request_id": "uuid", "created_at": "..." }

// AdminUser
{ "id": "uuid", "username": "demo1", "display_name": "Demo 1", "role": "user", "disabled": false,
  "created_at": "...", "last_login_at": "...", "message_count": 12 }
```

- บัญชีที่ `disabled: true` → login ไม่ได้ และ cookie เดิมถูกปฏิเสธ (401 `ACCOUNT_DISABLED`) ภายใน 1 นาที
- seed: บัญชี `admin` 1 บัญชี (รหัสอยู่ใน `.env` — `SEED_ADMIN_PASSWORD`) + `demo1`–`demo3` role `user`
- ปุ่มที่ลบหรือเปลี่ยนสถานะ (unpublish, ลบเอกสาร, ระงับบัญชี) web ต้องมีกล่องยืนยันก่อนส่ง

| code | status | เมื่อไร |
|---|---|---|
| `FORBIDDEN` | 403 | ไม่ใช่ admin |
| `ACCOUNT_DISABLED` | 401 | บัญชีถูกระงับ |
| `CANNOT_MODIFY_SELF` | 409 | admin แก้ role / ระงับบัญชีตัวเอง |
| `REPORT_NOT_EDITABLE` | 409 | แก้รายงานที่ `published` อยู่ (ต้อง unpublish ก่อน) |
| `JOB_ALREADY_RUNNING` | 409 | สั่ง ingest / สร้างรายงานซ้ำขณะที่ job ชนิดเดียวกันยังรันอยู่ |

## 2. api → router

`POST /route`

```jsonc
// RouteRequest
{
  "request_id": "uuid", "session_id": "uuid",
  "user": { "id": "uuid", "favorite_team_id": 57, "language": "th" },
  "query": "ข้อความผู้ใช้",
  "history": [ HistoryMessage ],     // ข้อความล่าสุดไม่เกิน 10 รายการ เรียง เก่า → ใหม่ (api ตัดจาก Message เหลือ role + content)
  "context": {                        // api ได้มาจาก GET /football/status ของ 07 (cache 5 นาที)
    "season": "2026", "current_matchweek": 5, "now": "2026-09-22T10:00:00+07:00",
    "last_ingest_at": "2026-09-22T09:30:00+07:00"   // v1.3 optional · ค่าเดียวกับ /football/status · null เมื่อ 07 ล่มหรือยังไม่เคย ingest
  }
}

// RouteResponse
{
  "request_id": "uuid",
  "answer": "...", "sources": [ Source ],
  "route": "football_rag", "engines_used": ["retrieval", "generation"],
  "confidence": 0.9, "reasoning": "เจอชื่อทีม 'ปืนใหญ่' + คำว่า 'ชนะไหม' ในชั้น rules",
  "latency_ms": 1900, "token_usage": TokenUsage,
  "trace": Trace
}
```

- router **ต้องตอบ 200 เสมอ** เมื่อได้คำตอบใด ๆ (รวมถึงคำตอบ fallback) · ตอบ 5xx เฉพาะเมื่อไม่มีอะไรจะตอบเลย
- ถ้าตัวสำรองล่มหมด ให้ตอบ 200 พร้อม `answer` = "ตอนนี้ระบบไม่ว่าง ลองใหม่อีกครั้งในอีกสักครู่" และ `trace.fallback` ระบุสาเหตุ
- (v1.8) เมื่อมี `history` และคำถามดูเป็นคำถามต่อเนื่อง router อาจเรียก LLM เพื่อเขียนคำถามใหม่ให้สมบูรณ์ในตัว (`trace.standalone_query`) · ใช้เลือก route และค้นหาเท่านั้น · `POST /generate` และ `POST /general` ได้ `query` เดิมของผู้ใช้เสมอ · ผลที่เพิ่มทีม ตัวเลข หรือช่วงเวลาซึ่งไม่อยู่ในคำถาม/history หรือตัดทีมที่ผู้ใช้ถามทิ้ง ถูกทิ้ง · คำถามที่ guard ตัดสินเป็น decline/clarify หรือที่ rules ได้ intent ผูกทีมพร้อมทีมแล้ว ไม่ถูก condense · ขั้น condense ใช้เวลารวม ≤ 4s (provider ละ ≤ 2s) นับรวมในงบ 40s · ใช้โมเดลเล็กจาก env `GROQ_CONDENSE_MODEL` / `GEMINI_CONDENSE_MODEL` (ว่าง = ใช้ `GROQ_MODEL` / `GEMINI_MODEL`) · rewrite ต้องเป็นภาษาเดียวกับคำถาม · ปิดได้ด้วย env `ROUTER_CONDENSE_ENABLED=false`
- (v1.9) เส้น `football_rag` ที่คำถามมีภาษาไทย router อาจให้ LLM (โมเดล condense) เขียนคำค้นภาษาอังกฤษแล้วเรียก `POST /search` ครั้งที่สองด้วย payload เดิมที่เปลี่ยนแค่ `query` · รวมผลสองชุดด้วย RRF (k = 60) ตาม `chunk_id` แล้วส่ง 5 อันดับแรกให้ `/generate` ซึ่งได้ `query` เดิมของผู้ใช้เสมอ · คำค้นที่ทีมไม่ตรงกับคำถาม (เพิ่มหรือตัดทีม) หรือมีตัวเลขซึ่งไม่อยู่ในคำถามถูกทิ้ง · LLM ล่ม/ช้า (≤ 4s รวมในงบ 40s) → ใช้ผลค้นครั้งแรก · ปิดได้ด้วย env `ROUTER_MULTI_QUERY_ENABLED=false` · §4 ไม่เปลี่ยน
- (v1.12) ข้อความทักทาย ขอบคุณ ลา และคำถามเรื่องตัวผู้ช่วยเอง (ชื่อ ความสามารถ แหล่งข้อมูล ทีมโปรด ผู้สร้าง) ไป route `chat`: router ให้ LLM (โมเดลเล็ก) เรียบเรียงคำตอบจากแผ่นข้อมูลของระบบ แล้วตรวจก่อนส่ง · ไม่ผ่านการตรวจหรือ LLM ล่ม → ข้อความสำเร็จรูป · route `chat` ไม่เรียก 05/06 จึง `sources: []` และ `engines_used: []` · ข้อความที่มีเนื้อหาฟุตบอลปนยังไปเส้นฟุตบอลตามเดิม · guard (พนัน นอกขอบเขต) มาก่อนเสมอ

## 3. router → engines

### `POST /general` (General AI)
```jsonc
{ "request_id": "uuid", "query": "...", "history": [ HistoryMessage ], "language": "th" }
```

### `POST /local/classify` (Local AI — intent classifier)
```jsonc
{ "request_id": "uuid", "text": "..." }
```

### `POST /local/predict` (Local AI — ทำนายผล · **Could**)
```jsonc
{ "request_id": "uuid", "home_team_id": 64, "away_team_id": 65, "season": "2026",
  // v1.7 optional — ไม่ส่ง strength → 501 NOT_IMPLEMENTED เหมือนเดิม
  "home_strength": { "attack": 1.9, "defense": 0.8, "matches_used": 43 },
  "away_strength": { "attack": 1.6, "defense": 1.1, "matches_used": 43 },
  "league_avg_goals": 1.38, "home_name": "Liverpool", "away_name": "Man City" }
```
ผู้เรียก: **football-data** (v1.7 · router เรียกผ่าน 07 `/football/predict`) · ไม่ส่ง strength → `501 {code: "NOT_IMPLEMENTED"}` แล้ว router แปลงเป็นคำตอบ "ฟีเจอร์ทำนายผลยังไม่เปิดใช้งาน"
`data` = `{home_win, draw, away_win, method: "poisson-v1", matches_used, home_xg, away_xg, most_likely_score: {home, away}}` · `model: "poisson-v1"`

### `POST /local/simulate` (v1.7 · ผู้เรียก: football-data)
```jsonc
{ "request_id": "uuid",
  "inputs": { "season": "2026", "as_of": "2026-09-30T22:50:00+07:00",
    "table": [ { "team_id": 57, "name": "Arsenal", "points": 12, "goal_difference": 4, "goals_for": 9, "played": 5 } ],
    "remaining": [ { "match_id": "uuid", "home_team_id": 57, "away_team_id": 61 } ],
    "strengths": { "57": { "attack": 1.9, "defense": 0.8, "matches_used": 43 } },
    "league_avg_goals": 1.38, "relegation_places": 3 },
  "n_sims": 10000,   // 1,000–20,000
  "seed": 42 }       // optional · ผลซ้ำได้
```
`data` = `{season, as_of, n_sims, remaining_matches, teams: [{team_id, points, expected_points, p_title, p_top4, p_relegation, position_probs: [N ค่า]}]}` เรียง `expected_points` มาก → น้อย · `model: "poisson-mc-v1"` · ทีมใน `remaining` ไม่อยู่ใน `table` / `strengths` หรือ `table` ว่าง → 422 `VALIDATION_ERROR`

ทั้งสามตอบ `EngineResult`

```jsonc
{
  "engine": "general_ai | local_ai",
  "content": "ข้อความผลลัพธ์ (local: สรุปอ่านได้ เช่น 'intent: match_result (0.88)')",
  "data": {                                     // null สำหรับ /general
    "label": "match_result", "score": 0.88,
    "top_k": [["match_result", 0.88], ["standings_stats", 0.07]]
    // /local/predict: { "home_win": 0.46, "draw": 0.27, "away_win": 0.27, "method": "poisson-v1", "matches_used": 38 }
  },
  "sources": [],
  "model": "openai/gpt-oss-120b | tfidf-logreg-v1",   // ชื่อโมเดลที่ใช้จริง ไม่ใช่ชื่อ provider
  "latency_ms": 800, "token_usage": TokenUsage
}
```

### Intent ของ classifier (v1.5) — 9 หมวด และตาราง map → route (**ล็อกแล้ว ห้ามตีความเอง**)

03 ใช้ตารางนี้ที่ชั้น classifier · 04 ห้ามเพิ่ม/เปลี่ยนชื่อ intent โดยไม่แก้ตารางนี้ผ่าน PR

| intent | route | `filters.category` ที่ router ส่งให้ 05 | ตัวอย่าง |
|---|---|---|---|
| `trivia_history` | `football_rag` | `["trivia", "historical"]` · ถามฤดูกาลในอดีตหรือสถิติพบกันชัดเจน → `["historical"]` (+ `season`) (v1.11) | ใครได้บัลลงดอร์ 2008 · ฤดูกาล 2004/05 ใครแชมป์ |
| `match_result` | `football_rag` | `["match_report"]` + `team_ids` / `matchweek` | เมื่อวานผีเจอใคร ผลเท่าไหร่ |
| `fixture_schedule` | `football_rag` | `["fixtures"]` | หงส์เตะกับใครต่อ วันไหน |
| `standings_stats` | `football_rag` | `["standings"]` | ตอนนี้ใครจ่าฝูง / ดาวซัลโว |
| `weekly_summary` | `football_rag` | `["weekly_report"]` + `matchweek` | สรุปพรีเมียร์ลีกสัปดาห์นี้ |
| `player_info` | `football_rag` | `["player"]` + `team_ids` | อาร์เซนอลมีใครบ้าง · ซาก้าเล่นตำแหน่งอะไร · โค้ชลิเวอร์พูลคือใคร |
| `general_football` | `general_ai` | – | อธิบายกฎล้ำหน้า |
| `prediction` | `local_ai` | – | ลิเวอร์พูลกับซิตี้ใครน่าจะชนะ |
| `out_of_scope` | `decline` | – | เรื่องที่ไม่เกี่ยวกับฟุตบอล · ขอทีเด็ด/ราคาพนัน · คำขอที่ทำร้ายผู้อื่น |
| `chitchat` | `chat` | – | (v1.12) ทักทาย ขอบคุณ ลา ถามชื่อ/ความสามารถ/แหล่งข้อมูล/ทีมโปรด/ผู้สร้างของผู้ช่วย · ตอบจากแผ่นข้อมูลของระบบ |

- ใช้ตารางนี้เมื่อ `score ≥ 0.75` เท่านั้น ต่ำกว่านั้นให้ตกไปชั้น LLM
- ชั้น LLM ตอบ intent ได้แค่ 10 ค่านี้ (v1.12 เพิ่ม `chitchat`) หรือ `clarify` (เมื่อชื่อทีม/ช่วงเวลากำกวมจนเลือกไม่ได้)
- **ช่วงเวลาในคำถาม** ("เมื่อวาน", "สัปดาห์นี้", "นัดที่แล้ว") router แปลงเป็น `matchweek` หรือ `date_from/date_to` จาก `context` ก่อนเรียก 05

### ลำดับถอยของเส้น `football_rag` (ห้ามจบด้วย "ไม่มีข้อมูล" เฉย ๆ)
1. 05 คืน `chunks` ว่าง **ด้วย filter** → ค้นซ้ำ 1 ครั้งโดยตัด `matchweek`/`date_*` ออก (เก็บ `category` + `team_ids`)
2. ยังว่าง หรือ 05 ล่ม
   - `filters.category` เป็น `["historical"]` อย่างเดียว (v1.11) → **ห้ามถอยไป `general_ai`** ตอบว่า "ยังไม่มีข้อมูลสถิติย้อนหลังนี้ในระบบ"
   - intent `trivia_history` แบบอื่น → ถอยไป `general_ai` และต่อท้าย "คำตอบนี้มาจากความรู้ทั่วไป ไม่ได้อ้างอิงคลังข้อมูล"
   - intent ข้อมูลแมตช์ (`match_result`, `fixture_schedule`, `standings_stats`, `weekly_summary`, `player_info`) → **ห้ามถอยไป `general_ai`** (LLM จะเดาผล) ตอบว่า "ยังไม่มีข้อมูลของช่วงนี้ในระบบ ข้อมูลล่าสุด ณ `<context.last_ingest_at>`" พร้อม `trace.fallback` · ถ้า `context.last_ingest_at` เป็น null หรือไม่มี field (api รุ่นก่อน v1.3) ให้ตัดท่อน "ข้อมูลล่าสุด ณ ..." ออก ห้ามเดาเวลา

## 4. router → retrieval

`POST /search`

```jsonc
// SearchRequest
{
  "request_id": "uuid",
  "query": "Arsenal latest match result",       // router ส่งคำถามที่ rewrite แล้ว
  "query_original": "เมื่อวานปืนใหญ่ชนะไหม",     // 05 ใช้หาชื่อเล่นทีม · ฝั่ง vector ใช้ `query` (v1.2)
  "top_k": 5,
  "filters": {                                   // ทุก field optional · ไม่ใส่ = ไม่กรอง
    "category": ["match_report"],
    "season": "2026", "matchweek": 5,
    "team_ids": [57],                            // เอกสารที่มีทีมใดทีมหนึ่งในรายการ
    "topic": ["club_record"],                    // (v1.15) เอกสารที่ topic อยู่ในรายการ · topic null ไม่ผ่าน
    "date_from": "2026-09-20", "date_to": "2026-09-22"
  },
  "mode": "hybrid"                               // hybrid (default) | bm25 | vector  — ใช้ตอน eval
}

// SearchResponse
{
  "request_id": "uuid",
  "chunks": [
    { "chunk_id": "match-2026-mw05-57-61#c0", "text": "...", "score": 0.031,
      "bm25_score": 11.2, "vector_score": 0.77, "rerank_score": null,
      "source": Source }
  ],
  "latency_ms": 140,
  "index_version": "2026-09-22T09:05:00+07:00"   // เวลาที่ index เปลี่ยนล่าสุด
}
```

- `score` = คะแนน RRF (k = 60) ตอน `mode=hybrid` · เรียงมาก → น้อย
- ถ้าเปิด reranker (Could) ให้ใส่ `rerank_score` และเรียงตามนั้น
- ไม่เจออะไรเลย → `200` + `chunks: []` (ไม่ใช่ 404)
- ข้อมูลแมตช์ที่ `category` เดียวกันและ `doc_id` เดียวกัน จะมีได้แค่เวอร์ชันล่าสุดเวอร์ชันเดียวใน index เสมอ

| code | status | เมื่อไร |
|---|---|---|
| `INDEX_NOT_READY` | 503 | index ยังโหลดไม่เสร็จตอน retrieval เริ่มระบบ · ใช้กับ `/search` (§4) และทุก endpoint ของ §6 (`/index/upsert`, `DELETE /index/{doc_id}`, `/index/stats`, `/index/rebuild`) · router ถือเป็น retrieval ล่ม แล้วถอยตามลำดับของเส้น `football_rag` (§3) |

## 5. router / football-data → generation

### `POST /generate`

```jsonc
// GenerateRequest
{
  "request_id": "uuid",
  "mode": "grounded | passthrough",
  "query": "คำถามเดิมของผู้ใช้ (ไม่ใช่ที่ rewrite)",
  "language": "th",
  "contexts": [ { "ref": 1, "text": "...", "source": Source } ],   // grounded: จาก 05 · passthrough: []
  "scope_team_ids": [57],                                           // v1.6 optional · 03 ส่งทีมที่ระบุในคำถามให้ 06; [] เมื่อไม่ได้ระบุทีม
  "draft": "ข้อความจาก engine",                                   // passthrough เท่านั้น
  "history": [ HistoryMessage ]
}

// GenerateResponse
{
  "request_id": "uuid",
  "answer": "markdown พร้อม [1] [2]",
  "sources": [ Source ],            // เฉพาะที่ถูกอ้างจริงในคำตอบ เรียงตาม ref
  "citations_removed": 0,           // จำนวน [n] ที่ถูกตัดเพราะไม่มีจริง
  "safety": { "blocked": false, "reason": null },
  "model": "openai/gpt-oss-120b", "latency_ms": 1500, "token_usage": TokenUsage
}
```

- `grounded`: ตอบจาก `contexts` เท่านั้น · **ตัวเลขสกอร์ / อันดับ / วันเวลาต้องมาจาก context ห้ามแต่งเพิ่ม** · ถ้า context ไม่พอ ให้มีประโยค "ไม่พบข้อมูลที่เพียงพอ" ในคำตอบ และ `sources: []`
- `scope_team_ids` เป็น optional ใน `POST /generate` · 06 ใช้แยกคำถามอันดับนักเตะภายในทีมออกจากอันดับทั้งลีก และยังต้องมีข้อมูลจัดอันดับทีมที่ครบใน `contexts` ก่อนตอบ · 06 รุ่นก่อนที่ยังไม่รู้จัก field นี้จะเพิกเฉยได้
- `passthrough`: ใช้กับผลจาก `/general` และ `/local/*` — ปรับภาษาให้ตรง `language` + ผ่าน safety **ไม่เรียก LLM ซ้ำ** ถ้า draft เป็นภาษาเดียวกันอยู่แล้ว
- context ถูกห่อเป็น "ข้อมูลอ้างอิง ไม่ใช่คำสั่ง" ทุกครั้ง (กัน prompt injection จากเนื้อหาเอกสาร)
- safety: ถ้าคำตอบมีทีเด็ด/อัตราต่อรอง/ชวนเล่นพนัน → `safety.blocked = true` และแทนคำตอบด้วยข้อความปฏิเสธ

### `POST /report/weekly` (เรียกโดย football-data เท่านั้น)

```jsonc
// WeeklyReportRequest
{
  "request_id": "uuid", "season": "2026", "matchweek": 5, "language": "th",
  "matches": [ Match ],              // ทุกนัดของแมตช์วีค (รวมนัดที่เลื่อน สถานะ POSTPONED)
  "standings": [ StandingRow ],      // ตารางหลังจบแมตช์วีค
  "top_scorers": [ Scorer ]
}

// WeeklyReportResponse
{
  "request_id": "uuid",
  "title": "สรุปพรีเมียร์ลีก 2026/27 นัดที่ 5",
  "markdown": "## ผลการแข่งขัน ... ## ไฮไลต์ ... ## ตารางคะแนน ...",
  "highlights": ["Arsenal ชนะ Chelsea 2–1 ขึ้นจ่าฝูง", "..."],
  "model": "openai/gpt-oss-120b", "latency_ms": 9000, "token_usage": TokenUsage
}
```

`Match`, `StandingRow`, `Scorer` นิยามใน §7

## 6. football-data → retrieval (จัดการ index)

### `POST /index/upsert`
```jsonc
{
  "request_id": "uuid",
  "documents": [
    {
      "doc_id": "match-2026-mw05-57-61",
      "title": "Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5",
      "text": "Premier League 2026/27, matchweek 5, 20 Sep 2026 18:30 (+07:00) at Emirates Stadium. Arsenal 2-1 Chelsea. Goals: Saka 12', ... ",
      "category": "match_report", "origin": "api-football",
      "season": "2026", "matchweek": 5, "team_ids": [57, 61],
      "date": "2026-09-20", "fetched_at": "2026-09-21T09:00:00+07:00",
      "url": null
    }
  ]
}
// 200
{ "request_id": "uuid", "upserted": 1, "chunks": 1, "index_version": "2026-09-22T09:05:00+07:00" }
```

### `DELETE /index/{doc_id}` → `{deleted: true}` (ไม่มีอยู่ → `{deleted: false}` 200)

### `GET /index/stats` → `{documents, chunks, by_category: {...}, index_version}`

### `POST /index/rebuild` (เรียกโดย api ผ่านหน้า admin · **Could**)
body `{request_id, category?}` (ไม่ใส่ = ทั้งหมด) → `202 {job_id}` · สร้าง BM25 + FAISS ใหม่จากเอกสารที่เก็บไว้ แล้วสลับ index ทีเดียว (ระหว่างสร้าง `/search` ใช้ index เดิมได้ตามปกติ) · ดูสถานะที่ `GET /index/jobs/{job_id}` → `{job_id, status, started_at, finished_at, detail}` · job เก็บในหน่วยความจำของ 05 (50 รายการล่าสุด) **restart แล้วหาย → 404** · หน้า admin ให้ถือว่างานนั้นจบไม่แน่ชัดแล้วสั่งใหม่ได้ (rebuild ที่ไม่จบไม่เปลี่ยน index)

**รูปแบบ `doc_id` (ล็อกแล้ว — upsert ทับด้วย id นี้ จึงไม่มีเอกสารซ้ำ)**

| category | doc_id | หมายเหตุ |
|---|---|---|
| `trivia` | `trivia-<เลขลำดับ 4 หลัก>` | สร้างครั้งเดียวตอน ingest คลัง |
| `match_report` | `match-<season>-mw<NN>-<home_id>-<away_id>` | ทับเมื่อได้ข้อมูลละเอียดจาก API-Football |
| `standings` | `standings-<season>` | ล่าสุด 1 เอกสารต่อฤดูกาล ทับทุกครั้งที่ ingest; legacy `-mw<NN>` รองรับเฉพาะช่วง cleanup |
| `fixtures` | `fixtures-<season>-team-<team_id>` | นัดที่เหลือของทีมนั้น ทับทุกครั้งที่ ingest |
| `weekly_report` | `weekly-<season>-mw<NN>` | ที่มา `origin: generated` · **upsert เมื่อ publish เท่านั้น** และ delete เมื่อ unpublish (§7) |
| `player` | `players-<season>-team-<team_id>` | (v1.5) squad ของทีมนั้น 1 เอกสารต่อทีม ทับทุกครั้งที่ ingest · `origin: football-data.org` · `matchweek: null` · `team_ids: [team_id]` · หัวข้อ `## <ชื่อผู้เล่น>` ต่อคน (05 ตัด 1 chunk ต่อคน) · 07 ส่งก็ต่อเมื่อเปิด `PLAYER_INDEX_ENABLED` · (v1.16) `coach-<season>-team-<team_id>` โค้ชคนปัจจุบันจาก Wikidata P286 1 เอกสารต่อทีม · `origin: wikidata` · topic `head_coach` · `matchweek: null` · `team_ids: [team_id]` · 07 ส่งเมื่อเปิด `COACH_INDEX_ENABLED` และทับทุกรอบที่ Wikidata ตอบสำเร็จ (ล้มแล้วคงเอกสารเดิม) |
| `historical` | `hist-season-<YYYY>` · `hist-team-<YYYY>-<slug>` · `hist-h2h-<slug>-<slug>` · `hist-club-<slug>` · `hist-records` (v1.13) | (v1.11) คลังพรีเมียร์ลีก 1992/93 ถึงฤดูกาลที่แล้ว จาก 07 · slug = ตัวพิมพ์เล็ก ตัวเลข ขีด (h2h เรียงตามตัวอักษร) · ส่งเมื่อรัน `ingest_history.py --index` พร้อม `HISTORICAL_INDEX_ENABLED=true` เท่านั้น (ไม่อยู่ในตารางเวลา) · `season` = ปีเริ่มฤดูกาล (h2h, club, records = null) · (v1.13) `hist-club-<slug>` สรุปสถิติทั้งยุคของสโมสร `hist-records` แชมป์และตารางรวมตลอดกาลทั้งลีก คำนวณจากตารางจบฤดูกาล สถิติยุคพรีเมียร์ลีก และจำนวนแชมป์ลีกสูงสุดทุกยุค (First Division 1888/89–1991/92 จาก Fjelstul) · `team_ids` ว่างได้สำหรับสโมสรที่ไม่มี id · **ห้ามตัดส่วน "Sources and license"** (openfootball CC0, Fjelstul แชร์ต่อแบบ CC-BY-SA 4.0) |

- **ช่วงเปลี่ยนผ่าน standings v1.4:** เมื่อ 07 ingest ฤดูกาลหนึ่งหลัง revision นี้มีผล ให้ upsert `standings-<season>` ก่อน แล้วค่อยลบ legacy `standings-<season>-mw01` ถึง `-mw38` ที่อาจค้างใน 05; งานลบล้มเหลวต้อง retry ได้ และห้ามลบก่อนเอกสารใหม่ index สำเร็จ ระหว่าง cleanup 05 ยังยอมรับ ID ทั้งสองรูปแบบ แต่หลัง cleanup ฝั่งเรียกควรใช้เฉพาะ ID ใหม่
- เอกสาร `standings-<season>` ใน search คือ **snapshot ล่าสุดเท่านั้น** ไม่ใช่ประวัติรายแมตช์วีค; ผู้ใช้ที่ต้องการตารางย้อนหลังรายสัปดาห์ต้องใช้ข้อมูลหรือ endpoint สำหรับประวัติที่ตกลงแยก ไม่อนุมานจาก index นี้

- 05 ตัด chunk: `trivia` = 1 คู่ถาม-ตอบ ต่อ 1 chunk · อื่น ๆ = ตามหัวข้อ (`## `) ไม่ตัดตามจำนวนตัวอักษร
- upsert ต้องอัปเดตทั้ง BM25 และ FAISS ให้ตรงกัน ก่อนเปลี่ยน `index_version`
- **ข้อความใน `text` เป็นภาษาอังกฤษ** (ให้ตรงกับคลัง trivia) — ชื่อเล่นภาษาไทยจัดการด้วย alias ที่ฝั่ง query
- ขอบเขตของ upsert: 1–100 เอกสารต่อคำขอ · body ≤ 5 MB (เกิน → 413) · field ผิด / `doc_id` ไม่ตรงรูปแบบของ category → 422 ทั้งคำขอ · ล้มกลางทาง → 500 และ index ไม่เปลี่ยนเลย
- index ยังโหลดไม่เสร็จ → ทุก endpoint ของ §6 ได้ `INDEX_NOT_READY` (503) (ดูตารางใน §4) · 07 ถือ upsert / delete ที่ล้มเป็น job ล้มแล้ว retry

## 7. api → football-data

| Method | Path | ผู้เรียก | Response 200 |
|---|---|---|---|
| GET | `/football/status` | api | `{current_season, current_matchweek, last_ingest_at, last_report_matchweek, quota: {api_football_used_today, api_football_limit, reset_at}}` |
| GET | `/football/standings` | api | `{season, matchweek, fetched_at, rows: [StandingRow]}` |
| GET | `/football/fixtures` | api | `{season, fetched_at, matches: [Match]}` · query `season, matchweek, team_id, status` |
| GET | `/football/matches/{match_id}` | api | `Match` (มี `events`, `lineups`, `statistics` ถ้ามี) |
| GET | `/football/reports/weekly` | api | `WeeklyReport` · query `season, matchweek` (ไม่ใส่ = ล่าสุด) · **คืนเฉพาะ `published`** · ไม่มี → 404 |
| GET | `/football/teams` | api, router, retrieval | `{teams: [Team]}` (รวม aliases — router cache ไว้ใช้ในชั้น rules · retrieval ใช้ขยายคำค้น BM25 ดึงใหม่ทุก 1 ชม. ถ้าดึงไม่ได้ใช้ไฟล์สำรองของตัวเอง) |
| GET | `/football/predict` | router, api | `EngineResult` ของ 04 + `data.as_of` · query `home_team_id, away_team_id` (ถ้ามีนัดที่ยังไม่แข่งระหว่างสองทีม ใช้ฝั่งเหย้าตามโปรแกรมนัดถัดไป) · 404 ทีมไม่อยู่ฤดูกาลนี้ · 422 ทีมเดียวกัน · 503 `SIMULATION_UNAVAILABLE` (v1.7) |
| GET | `/football/simulation` | router, api | `SimulationSnapshot` · query `season?` (ฤดูกาลอื่น → 404) · 503 `SIMULATION_UNAVAILABLE` เมื่อไม่มีผลเก่าและ 04 ล่ม (v1.7) |
| POST | `/ingest/run` | beat ของ api / admin | `202 {job_id, scope}` · body `{scope: "fixtures" \| "details" \| "all", triggered_by}` |
| POST | `/reports/weekly/run` | beat ของ api / admin | `202 {job_id}` · body `{season?, matchweek?, triggered_by}` (ไม่ใส่ = แมตช์วีคล่าสุดที่จบครบ) |
| GET | `/jobs` | api (admin) | `{jobs: [Job]}` · query `kind, status, limit=20` เรียงใหม่ → เก่า |
| GET | `/jobs/{job_id}` | api | `Job` (นิยามใน §1.1) |
| GET | `/reports/weekly/list` | api (admin) | `{items: [WeeklyReport]}` · query `status, season` · ทุกสถานะ |
| GET | `/reports/weekly/{season}/{matchweek}` | api (admin) | `WeeklyReport` ทุกสถานะ |
| PATCH | `/reports/weekly/{season}/{matchweek}` | api (admin) | `WeeklyReport` · body `{title?, markdown?, edited_by}` · เฉพาะ `draft` / `unpublished` |
| POST | `/reports/weekly/{season}/{matchweek}/publish` | api (admin) | `WeeklyReport` · body `{published_by}` · upsert `weekly-<season>-mw<NN>` เข้า 05 **สำเร็จก่อน** แล้วค่อยเปลี่ยนสถานะ |
| POST | `/reports/weekly/{season}/{matchweek}/unpublish` | api (admin) | `WeeklyReport` · body `{unpublished_by}` · `DELETE /index/weekly-...` ที่ 05 แล้วเปลี่ยนสถานะ |

`triggered_by` / `edited_by` / `published_by` = `"beat"` หรือ `"admin:<user_id>"` · 02 เป็นคนใส่ ห้ามรับค่าจากหน้าเว็บ

```jsonc
// Team
{ "team_id": 57, "name": "Arsenal FC", "short_name": "Arsenal", "tla": "ARS",
  "aliases": ["ปืนใหญ่", "ปืน", "อาร์เซนอล", "the gunners"], "crest_url": "..." }

// Match
{
  "match_id": "uuid",
  "external_ids": { "football_data": 537812, "api_football": 1208123 },
  "season": "2026", "matchweek": 5,
  "kickoff": "2026-09-20T18:30:00+07:00",
  "status": "SCHEDULED | LIVE | FINISHED | POSTPONED | CANCELLED",
  "home": { "team_id": 57, "name": "Arsenal" }, "away": { "team_id": 61, "name": "Chelsea" },
  "score": { "home": 2, "away": 1, "half_time": { "home": 1, "away": 0 } },
  "events": [ { "minute": 12, "type": "goal | own_goal | penalty | yellow | red | sub", "team_id": 57, "player": "B. Saka", "assist": "M. Ødegaard" } ],
  "lineups": null, "statistics": null,           // null = ยังไม่ได้ดึง / ไม่มี
  "fetched_at": "2026-09-21T09:00:00+07:00",
  "detail_source": "api-football | none"
}

// StandingRow
{ "position": 1, "team_id": 57, "name": "Arsenal", "played": 5, "won": 4, "draw": 1, "lost": 0,
  "goals_for": 12, "goals_against": 4, "goal_difference": 8, "points": 13, "form": "WWDWW" }

// Scorer
{ "player": "E. Haaland", "team_id": 65, "goals": 7, "assists": 1 }

// WeeklyReport
{ "season": "2026", "matchweek": 5, "title": "...", "markdown": "...", "highlights": [],
  "status": "draft | published | unpublished",
  "generated_at": "2026-09-22T09:02:00+07:00", "data_as_of": "2026-09-22T09:00:00+07:00",
  "edited_at": null, "edited_by": null,
  "published_at": null, "published_by": null }

// SimulationSnapshot (v1.7)
{ "season": "2026", "as_of": "...", "computed_at": "...", "stale": false,
  "n_sims": 10000, "model": "poisson-mc-v1",
  "teams": [ { "team_id": 57, "name": "Arsenal FC", "short_name": "Arsenal", "points": 12, "expected_points": 74.3,
               "p_title": 0.31, "p_top4": 0.82, "p_relegation": 0.0, "position_probs": [0.31, 0.24] } ] }
```

- v1.7: football-data เรียก engines `/local/predict` และ `/local/simulate` (env `ENGINES_URL`) · ความแข็งทีม = ฤดูกาลนี้ผสมฤดูกาลก่อน k = 10 · เก็บผลจำลองในตาราง `simulation_snapshots` และคำนวณใหม่หลัง ingest

**สถานะของรายงานประจำสัปดาห์**

```
/reports/weekly/run ──> draft ──publish──> published ──unpublish──> unpublished ──publish──> published
                          │ PATCH ได้                                   │ PATCH ได้
                          └── run ซ้ำแมตช์วีคเดิม = เขียนทับ draft (ถ้า published อยู่ → job failed "REPORT_ALREADY_PUBLISHED")
```

- ผู้ใช้ทั่วไปและแชท **เห็นเฉพาะ `published`** — draft ไม่เข้า Knowledge Base จึงไม่มีทางถูกอ้างในคำตอบ
- env `REPORT_AUTO_PUBLISH` (07, ค่าเริ่มต้น `false`): ถ้า `true` รายงานที่ run เสร็จจะ publish ทันที (`published_by: "beat"`) — ใช้เมื่อไม่มีหน้าตรวจรายงาน หรือกันเดโมไม่มีรายงานโชว์

- **ตารางเวลาที่ beat เรียก** (ตั้งใน 02 เวลา Asia/Bangkok): `ingest scope=fixtures` ทุก 30 นาที ช่วง ศ 18:00 – อ 06:00 · วันอื่นทุก 6 ชม. · `ingest scope=details` ทุก 2 ชม. · `reports/weekly/run` จันทร์ 09:00 และอังคาร 09:00 (กรณีนัดวันจันทร์)
- `/reports/weekly/run` สร้างรายงานได้เมื่อทุกนัดของแมตช์วีคอยู่ในสถานะ `FINISHED | POSTPONED | CANCELLED` · ไม่ครบ → job `failed` พร้อม `detail: "MATCHWEEK_NOT_COMPLETE"`
- ทุกครั้งที่ ingest เปลี่ยนข้อมูล → 07 สร้างเอกสารแล้ว `POST /index/upsert` ไปที่ 05 (§6)
- quota API-Football: 07 หยุดเรียกที่ 90 ครั้ง/วัน · `reset_at` = 07:00 (+07:00) ตามรอบ UTC ของผู้ให้บริการ

| code | status | เมื่อไร |
|---|---|---|
| `UPSTREAM_UNAVAILABLE` | 502 | football-data.org / API-Football ล่ม (07 ใช้ข้อมูลล่าสุดใน DB ต่อได้) |
| `QUOTA_EXHAUSTED` | 429 | quota API-Football วันนี้หมด |
| `MATCHWEEK_NOT_COMPLETE` | 409 | สั่งสร้างรายงานทั้งที่ยังแข่งไม่ครบ (เรียกตรงแบบ sync) |
| `JOB_ALREADY_RUNNING` | 409 | มี job ชนิดเดียวกันรันอยู่ |
| `REPORT_NOT_EDITABLE` | 409 | PATCH รายงานที่ `published` |
| `REPORT_ALREADY_PUBLISHED` | 409 | run ทับรายงานที่ `published` อยู่ |
| `INDEX_UPDATE_FAILED` | 502 | publish / unpublish แล้ว 05 upsert / delete ไม่สำเร็จ (สถานะรายงานไม่เปลี่ยน) |
| `SIMULATION_UNAVAILABLE` | 503 | 04 ล่มและยังไม่มีผลจำลองเก่า / ทำนายนัดไม่ได้ (v1.7) |
| `NOT_FOUND` | 404 | ไม่มีนัด / รายงานนั้น |

## 8. LLM provider (ใช้ร่วมทุก service ที่เรียก LLM: 03, 04, 06)

- ใช้ไลบรารี `openai` ตัวเดียว สลับเจ้าด้วย `base_url` · **ห้ามลง SDK ของเจ้าอื่นเพิ่ม**

| provider | `base_url` | env ของ key | env ของโมเดล |
|---|---|---|---|
| Groq (หลัก) | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | `GROQ_MODEL` |
| Gemini (สำรอง) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | `GEMINI_MODEL` |

- ลำดับ: หลัก → error / 429 / timeout → สำรอง 1 ครั้ง → ล่มทั้งคู่ส่ง error `LLM_UNAVAILABLE` (503) ให้ผู้เรียก
- ทุก response ที่มาจาก LLM ต้องบอก `model` ที่ใช้จริง และ `token_usage`
- โมเดลเล็กสำหรับงานเขียนคำค้นของ router (condense v1.8, คำค้นอังกฤษ v1.9): env `GROQ_CONDENSE_MODEL` / `GEMINI_CONDENSE_MODEL` (ว่าง = ใช้ `GROQ_MODEL` / `GEMINI_MODEL`) · timeout provider ละ 2s · คำขอที่ไม่มี field ที่ต้องการถือว่าล้มและลอง provider ถัดไป
- (v1.12) `ROUTER_CHAT_ENABLED` (ค่าเริ่มต้น `true`; `false` = ปิด route `chat` กลับเป็นพฤติกรรมเดิม) · `ROUTER_CHAT_TIMEOUT` (วินาทีต่อ provider ค่าเริ่มต้น 6) · ใช้โมเดลเล็กเดียวกับ condense
- env ของ API ฟุตบอล (07 เท่านั้น): `FOOTBALL_DATA_API_KEY`, `API_FOOTBALL_KEY`, `API_FOOTBALL_DAILY_LIMIT=90`
- `HISTORICAL_INDEX_ENABLED` (07, ค่าเริ่มต้น `false`, v1.11): อนุญาตให้ `ingest_history.py --index` ส่งคลังย้อนหลังเข้า 05

---

## Changelog

| version | วันที่ | เปลี่ยนอะไร |
|---|---|---|
| v1.0 | (D1) | ฉบับแรก |
| v1.1 | (D1) | **เพิ่มระบบ Admin** — §1.1 ใหม่ (`/api/admin/*`, สิทธิ์ `role=admin`, audit, error code ใหม่) · ย้าย `GET /api/stats` → `GET /api/admin/stats` · รายงานประจำสัปดาห์มีสถานะ `draft → published → unpublished` และเข้า KB เมื่อ publish เท่านั้น (+ env `REPORT_AUTO_PUBLISH`) · §6 เพิ่ม `POST /index/rebuild` · §7 เพิ่ม `GET /jobs`, endpoint จัดการรายงาน, `triggered_by` · field เดิมไม่ถูกลบ/เปลี่ยนชื่อ ยกเว้น path `/api/stats` ที่ย้าย |
| v1.2 | (D4) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — §4 / §6 เพิ่ม error `INDEX_NOT_READY` (503) · §6 ระบุขอบเขตของ upsert (1–100 เอกสาร, 5 MB, 422 ทั้งคำขอ) · §7 เพิ่ม retrieval เป็นผู้เรียก `GET /football/teams` · §4 ฝั่ง vector ของ 05 ใช้ `query` แทน `query_original` field และความหมายต่อผู้เรียกเหมือนเดิม — router ต้องส่ง `query` เป็นอังกฤษที่เขียนใหม่แล้ว · **มีผลเมื่อ PR #10 merge** (ก่อนนั้นโค้ดยัง embed `query_original`) · ตัวเลขที่ใช้ตัดสิน (ชุด match hit@1 0.70 → 0.90) วัดกับเอกสาร**จำลอง** 20 คำถามและคำอังกฤษที่เตรียมไว้ ไม่ใช่เอกสารของ 07 หรือคำที่ router เขียนจริง ต้องวัดซ้ำหลังต่อระบบ · §6 upsert / delete / rebuild ตอบ `INDEX_NOT_READY` ตอน index ยังโหลดไม่เสร็จ · §6 job ของ rebuild หายเมื่อ restart |
| v1.3 | (26 ก.ย.) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — §2 `RouteRequest.context` เพิ่ม `last_ingest_at` (optional, null ได้) ที่ api คัดจาก `GET /football/status` · §3 ข้อความ fallback ของ intent ข้อมูลแมตช์อ่านเวลาจาก `context.last_ingest_at` และตัดท่อนเวลาออกเมื่อเป็น null · เดิม §3 อ้าง `<last_ingest_at>` แต่ §2 ไม่ได้ส่งค่านี้ให้ router |
| v1.4 | 28 ก.ย. 2026 (มีผลแล้ว · PR #23) | **เปลี่ยนความหมาย §6 `standings` doc_id** จาก `standings-<season>-mw<NN>` ที่เก็บแยกตามแมตช์วีค เป็น `standings-<season>` ที่แทน snapshot ล่าสุด 1 เอกสารต่อฤดูกาล · 07 upsert ID ใหม่ก่อน queue ลบ legacy `-mw01`–`-mw38` แบบ retry ได้ · 05 ยอมรับทั้งสองรูปแบบเฉพาะช่วง cleanup · ไม่ใช้ search index นี้แทนประวัติตารางคะแนนรายสัปดาห์ · ต้องแจ้งทีมและได้ approval ตามกฎต้นไฟล์ก่อน merge |
| v1.5 | 30 ก.ย. 2026 (มีผลแล้ว · PR #25, #28) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — `category` ใหม่ `player` (§0 enum, §6 ตาราง `doc_id` `players-<season>-team-<team_id>`) · intent ใหม่ `player_info` ในตารางที่ล็อก (8 → 9 หมวด) ส่ง `filters.category = ["player"]` และถอยแบบเดียวกับ intent ข้อมูลแมตช์ (ห้ามถอยไป `general_ai`) · ผลต่อโมดูล: 05 รับ category ใหม่, 04 เพิ่ม intent และเทรนใหม่, 03 map intent, 02/01 เพิ่มค่าใน enum, 07 ส่งเอกสารเมื่อเปิดธง |
| v1.6 | 30 ก.ย. 2026 (มีผลแล้ว · PR #33, #34) | **เพิ่ม optional field** `scope_team_ids` ใน §5 `POST /generate` จาก 03 ไป 06 เพื่อระบุขอบเขตทีมของคำถามจัดอันดับผู้เล่น · 06 รุ่นก่อนเพิกเฉยต่อ field ใหม่ได้ · ต้องมีทั้งสอง PR จึงใช้การแยกขอบเขตทีมได้ครบ |
| v1.7 | 1 ต.ค. 2026 (มีผลแล้ว · PR #36) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — §3 `/local/predict` เพิ่ม field optional `home_strength`, `away_strength`, `league_avg_goals`, `home_name`, `away_name` และ `data.home_xg`, `away_xg`, `most_likely_score` · ผู้เรียกเปลี่ยนเป็น football-data · §3 เพิ่ม `POST /local/simulate` · §7 เพิ่ม `GET /football/predict`, `GET /football/simulation`, `SimulationSnapshot` และทิศ football-data → engines · §1 เพิ่ม `GET /api/football/predict`, `GET /api/football/simulation` · error `SIMULATION_UNAVAILABLE` (503) · `trace.fallback` เพิ่ม `simulation_down`, `prediction_needs_team`, `prediction_team_not_found` |
| v1.8 | 1 ต.ค. 2026 (มีผลแล้ว · PR #38) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — Trace เพิ่ม `standalone_query` และ `condense` · §2 router อาจ condense คำถามต่อเนื่องด้วย LLM ก่อนเลือก route/ค้นหา โดย generation ได้ query เดิม · env ใหม่ `ROUTER_CONDENSE_ENABLED`, `GROQ_CONDENSE_MODEL`, `GEMINI_CONDENSE_MODEL` · `fallback` ไม่มีค่าใหม่ · api (02) ส่งต่อได้เลยเพราะ `Trace` เป็น `extra="allow"` |
| v1.9 | 1 ต.ค. 2026 (มีผลแล้ว · PR #42) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — Trace เพิ่ม `search_query_en` และ `multi_query` · §2 router ค้นคำถามไทยซ้ำด้วยคำค้นอังกฤษจาก LLM แล้วรวมผลด้วย RRF · env ใหม่ `ROUTER_MULTI_QUERY_ENABLED` · `fallback` ไม่มีค่าใหม่ · §4 `/search` ไม่เปลี่ยน |
| v1.10 | 1 ต.ค. 2026 | **เอกสารเท่านั้น ไม่เปลี่ยนพฤติกรรม** — Trace รวบรวมค่า `fallback` ที่ router ใช้อยู่จริงทั้งหมด (เพิ่ม `classifier_down`, `llm_unavailable`, `general_down`, `generation_down`, `historical_scorer_unavailable`, `historical_scorer_invalid`, `router_timeout` พร้อมความหมาย) · §8 ระบุ env โมเดลเล็กของ router · สถานะ v1.4–v1.9 เป็นมีผลแล้ว · หัวไฟล์เป็น v1.10 |
| v1.11 | 1 ต.ค. 2026 (มีผลแล้ว · PR #45, #47) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — `category` ใหม่ `historical` + `origin` `openfootball`/`fjelstul` + `topic` ของคลังย้อนหลัง · §6 รูปแบบ doc_id `hist-*` · §3 `trivia_history` ค้น `["trivia", "historical"]` และค้น `["historical"]` + `season` เมื่อถามฤดูกาลในอดีตหรือสถิติพบกัน · ค้นคลังย้อนหลังไม่เจอห้ามถอยไป `general_ai` · env `HISTORICAL_INDEX_ENABLED` |
| v1.12 | 2 ต.ค. 2026 (มีผลแล้ว · PR #49, #50) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — `route` ใหม่ `chat` + intent `chitchat` · Trace เพิ่ม `chat` · §2 router ตอบเรื่องตัวผู้ช่วยจากแผ่นข้อมูลของระบบ (LLM เรียบเรียง + ตรวจก่อนส่ง + ข้อความสำเร็จรูปสำรอง) · §8 env `ROUTER_CHAT_ENABLED`, `ROUTER_CHAT_TIMEOUT` · สถานะ v1.11 เป็นมีผลแล้ว |
| v1.13 | 4 ต.ค. 2026 (มีผลแล้ว · PR #57) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — `topic` ของ `historical` เพิ่ม `club_record`, `league_records` · §6 doc_id เพิ่ม `hist-club-<slug>` (สรุปสถิติทั้งยุคของสโมสร) และ `hist-records` (แชมป์และตารางรวมตลอดกาล) · `season` = null · ส่งผ่าน `ingest_history.py --index` gate เดิม · router ไม่ต้องแก้ (`trivia_history` ค้น `["trivia", "historical"]` อยู่แล้ว) |
| v1.14 | 4 ต.ค. 2026 (มีผลแล้ว · PR #59) | **เอกสารเท่านั้น ไม่เปลี่ยน field หรือ doc_id** — `hist-club-<slug>` และ `hist-records` นับแชมป์ลีกสูงสุดของอังกฤษทุกยุค (First Division 1888/89–1991/92 จาก Fjelstul `standings.csv` ชุดเดิม · ฤดูกาลลีกดิวิชั่นเดียว 1888/89–1891/92 นับเป็น First Division และเอกสารระบุไว้) นอกจากสถิติยุคพรีเมียร์ลีก |
| v1.15 | 5 ต.ค. 2026 (มีผลแล้ว · PR #62, #64) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — §4 `filters.topic` (list ของ string อย่างน้อย 1 ค่า) กรองตาม `topic` ของเอกสาร เอกสารที่ `topic` เป็น null ไม่ผ่านเมื่อใช้ตัวกรองนี้ · ผลต่อโมดูล: 05 รับ filter ใหม่ · 03 ส่ง `{"category": ["historical"], "team_ids": [id], "topic": ["club_record"]}` เฉพาะการค้นสรุปสถิติแยกทีม (ถ้า 05 ตอบ 422 ใช้ผลค้นปกติ) · โมดูลอื่นไม่ต้องแก้ |
| v1.16 | 5 ต.ค. 2026 (มีผลแล้ว · PR #63, #64) | **เพิ่มเท่านั้น ไม่เปลี่ยน field เดิม** — `origin` ใหม่ `wikidata` · §6 `player` เพิ่ม doc_id `coach-<season>-team-<team_id>` (topic `head_coach`) · ผลต่อโมดูล: 07 สร้างเอกสารเมื่อเปิด `COACH_INDEX_ENABLED` · 05 เพิ่ม `wikidata` ใน `Origin` และรูปแบบ doc_id ของ `player` เป็น `(?:players|coach)-<season>-team-<team_id>` · 03 เขียนคำค้นคำถามโค้ชใหม่ · 02/01 ไม่ต้องแก้ |
