# แผนงานทีม D-II · DL-06 Agentic AI System I — ผู้ช่วยฟุตบอล (Football Assistant)

> เอกสารนี้คือ "แผนตั้งต้น" (implementation plan) ปรับได้หลังคุยกันรอบแรก แต่ **`CONTRACT.md` ต้องล็อกภายใน D1**
> ลำดับการอ่าน: ไฟล์นี้ → `CONTRACT.md` → `GIT_FLOW.md` → `SCHEDULE.md`
> สถานะ: กำลังพัฒนา — สถานะรายบริการอยู่ใน `README.md` หัวข้อ "สถานะ" · ชื่อ `member1`–`member6` ในเอกสาร map กับ GitHub username ตามตารางใน `GIT_FLOW.md` ข้อ 0.4

---

## 1. ระบบนี้คืออะไร

ผู้ช่วย AI ที่ตอบคำถามเรื่องฟุตบอล **Premier League** ได้สองแบบ

1. **ความรู้ฟุตบอล** (ประวัติ สถิติ ถ้วยรางวัล นักเตะ) — ตอบจากคลังความรู้พร้อมอ้างอิง
2. **ผลและโปรแกรมการแข่งขันรายสัปดาห์** — ผลนัดล่าสุด ตารางคะแนน โปรแกรมนัดถัดไป และ **รายงานสรุปประจำสัปดาห์** ที่ระบบเขียนให้อัตโนมัติทุกวันจันทร์

ผู้ใช้ถามเป็นภาษาไทยหรืออังกฤษก็ได้ ทุกคำตอบที่มาจากข้อมูลต้องบอกได้ว่ามาจากไหน และข้อมูลแมตช์ต้องบอกเวลาที่ดึงมา

## 2. ของที่นำมาต่อยอด (ไม่เริ่มจากศูนย์)

| ของเดิม | อยู่ที่ | ใช้ทำอะไรในงานนี้ |
|---|---|---|
| RAG week4 — hybrid BM25 + FAISS + RRF, reranker, query transform, memory, eval | `sakda1306/04622404-Advanced-Topics-in-Computer-Software` → `week4/.../RAG-Project` | แกนของ service `05_retrieval_knowledge` |
| คลัง `football_trivia_qa.txt` 1,996 ข้อ 14 หมวด + `golden_set.json` | repo เดียวกัน | Knowledge Base ส่วนที่ 1 + ชุดวัดผล retrieval ตั้งแต่วันแรก |
| ตัวแก้ 5 ปัญหาจาก week5 | `week5/DL-05-RAG System Development II` | ต้องติดมาใน 05/03 ทุกข้อ (ดูหัวข้อ 7) |
| API Backend ของ Travel Safety — FastAPI, JWT, Problem-JSON, request context, rate limit, Celery + Redis, Postgres, AgentClient (deadline / retry / circuit breaker), conversations, feedback | `sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D` → `DL-07.../02_api_backend` | แม่แบบของ `02_api_backend` (ตัดส่วนที่ไม่จำเป็นออก ดูหัวข้อ 5) |

## 3. สถาปัตยกรรม — map กับผังของอาจารย์ทีละกล่อง

ผังอาจารย์: `User → Web App → API/Backend → AI Router/Agent → {General AI | University RAG | Local AI Model} → Retrieval/Knowledge → LLM Generation → Response/Log → User` พร้อมกล่องเสริม User Data/Context, Knowledge Base, Monitoring & Analytics ทั้งหมดอยู่ใน Docker

| กล่องในผัง | ในระบบเรา | service (ชื่อใน compose) | เจ้าของ |
|---|---|---|---|
| Web App | แชท · หน้ารายงานประจำสัปดาห์ · ตารางคะแนน/โปรแกรม · history · ปุ่ม feedback · **ระบบ Admin `/admin/*`** (หัวข้อ 5.1) | `web` | member1 |
| API / Backend | gateway, auth, จัดการ session/history, เรียก router, Celery beat สั่งงานตามเวลา | `api`, `worker`, `beat` | **sakda1306** |
| User Data / Context | users, ทีมที่เชียร์ (preference), conversation history | `postgres` (schema `app`) | **sakda1306** |
| AI Router / Agent | เข้าใจเจตนา → เลือก route → วางลำดับ → จัดการบริบท follow-up | `router` | member2 |
| General AI | `/general` — คำถามฟุตบอลทั่วไปที่คลังไม่มี | `engines` | member3 |
| University RAG → **Football RAG** | เส้นที่ตอบจาก Knowledge Base พร้อมอ้างอิง (router → 05 → 06) | – | – |
| Local AI Model | `/local/classify` จำแนก intent (router ใช้เป็นชั้น classifier) · `/local/predict` ทำนายผลนัด (Could) | `engines` | member3 |
| Retrieval / Knowledge | hybrid search + กรองตาม season / matchweek / team / category | `retrieval` | **sakda1306** |
| Knowledge Base | ① คลัง trivia 1,996 ข้อ ② **เอกสารข้อมูลสด** ที่สร้างจาก API (match report, standings, fixtures, weekly report) | volume ของ `retrieval` · ผลิตโดย `football-data` | sakda1306 (index) · member5 (ข้อมูล) |
| (ใหม่) แหล่งข้อมูลฟุตบอล | ดึงจาก football-data.org + API-Football → Postgres + เอกสารเข้า KB · pipeline รายงานประจำสัปดาห์ | `football-data` | member5 |
| LLM Generation | ตอบแบบ grounded + citation · passthrough · เขียนรายงานประจำสัปดาห์ · safety | `generation` | member4 |
| Response / Log | log ทุกคำตอบ · history · feedback · stats · audit ของ admin — **เป็น package ใน 02 ไม่แยก service** | (ใน `api`) | **sakda1306** |
| Monitoring & Analytics + Docker | compose, Makefile, CI, `eval/report.html`, (Prometheus + Grafana = Could) | root, `deploy/` | member6 |

### ภาพรวมการไหลของข้อมูล

```
User ─HTTPS─> web ─> api ──POST /route──> router ─┬─> engines /general                (General AI)
                      │                           ├─> engines /local/*                (Local AI)
                      │                           └─> retrieval /search ─> generation /generate   (Football RAG)
                      └─ บันทึก log/history/feedback ลง postgres (ภายใน api)

beat (ใน api) ── ตามเวลา ──> football-data /ingest/run            (ช่วงมีแข่ง ศ 18:00–อ 06:00 ทุก 30 นาที · วันอื่นทุก 6 ชม. — ตาราง CONTRACT §7)
                          └─> football-data /reports/weekly/run  (จันทร์ + อังคาร 09:00)

football-data ─┬─> football-data.org  (หลัก: fixtures, results, standings — ไม่มีเพดานรายวัน)
               ├─> API-Football       (เสริม: events, lineups, สถิติ — เฉพาะนัดที่จบแล้ว)
               ├─> postgres (schema football)  ──> api /api/football/* ──> หน้าเว็บ
               ├─> สร้างเอกสาร ──> retrieval /index/upsert ──> Knowledge Base
               └─> generation /report/weekly ──> เก็บรายงานเป็น draft ──(admin publish)──> upsert เข้า KB
```

**หลักคิดสำคัญ 3 ข้อ**

1. **ข้อมูลเดียว สองมุมมอง** — ข้อมูลแมตช์เก็บแบบมีโครงสร้างใน Postgres (หน้าเว็บอ่านตรง ไม่ผ่าน LLM) และถูกแปลงเป็นเอกสารข้อความเข้า Knowledge Base (แชทถามผ่านเส้น RAG ได้พร้อมอ้างอิง) → ผังไม่ต้องมีเส้นพิเศษ ทุกกล่องตรงกับของอาจารย์
2. **แชทไม่เรียก API ภายนอกเด็ดขาด** — quota ฟรีของ API-Football มี 100 ครั้งต่อวัน ถ้าให้แชทเรียกสด หมดกลางเดโมแน่นอน ทุกอย่างถูกดึงล่วงหน้าตามเวลา ตอนสาธิตไม่ต้องพึ่ง API ภายนอก
3. **Router เป็นจุดตัดสินใจจุดเดียว** — เพิ่ม engine ใหม่แก้ที่ router ที่เดียว

### Route ที่ router ส่งออกได้ (5 ค่า ตรงกับ 5 แบบคำตอบใน README อาจารย์)

| route | ใช้เมื่อ | ตัวอย่าง |
|---|---|---|
| `football_rag` | ความรู้ฟุตบอล + ผล/โปรแกรม/ตารางคะแนน/รายงานสัปดาห์ | "ใครได้บัลลงดอร์ 2008" · "เมื่อวานผีเจอใคร ผลเท่าไหร่" · "สรุปพรีเมียร์ลีกสัปดาห์นี้" |
| `general_ai` | เรื่องฟุตบอลที่คลังไม่ครอบคลุม | "อธิบายกฎล้ำหน้าแบบง่าย ๆ" |
| `local_ai` | ขอให้ทำนายผลนัด (Could — ถ้ายังไม่ทำ ให้ตอบว่าฟีเจอร์ยังไม่เปิด) | "ลิเวอร์พูลกับซิตี้ ใครน่าจะชนะ" |
| `clarify` | ความมั่นใจต่ำ / ชื่อทีมกำกวม | "ผลนัดยูไนเต็ดล่าสุด" (แมนยู? นิวคาสเซิล? เวสต์แฮม?) |
| `decline` | ไม่เกี่ยวกับฟุตบอล หรือเป็นคำขอที่ไม่ปลอดภัย (เช่น ทีเด็ดพนัน) | "ช่วยเขียนโค้ดเว็บพนันบอล" |

## 4. ตาราง service

| โฟลเดอร์ | ชื่อใน compose | เจ้าของ | ภาษา/เฟรมเวิร์ก | port ภายใน | เปิดออก host |
|---|---|---|---|---|---|
| `services/01_web_app` | `web` | member1 | TypeScript · Next.js 14 | 3000 | 3000 |
| `services/02_api_backend` | `api`, `worker`, `beat` | **sakda1306** | Python 3.12 · FastAPI · Celery | 8000 | 8000 |
| `services/03_ai_router_agent` | `router` | member2 | Python · FastAPI | 8000 | 8003 (debug) |
| `services/04_ai_engines` | `engines` | member3 | Python · FastAPI · scikit-learn | 8000 | 8004 (debug) |
| `services/05_retrieval_knowledge` | `retrieval` | **sakda1306** | Python · FastAPI · FAISS · rank-bm25 · sentence-transformers | 8000 | 8005 (debug) |
| `services/06_llm_generation` | `generation` | member4 | Python · FastAPI · Jinja2 | 8000 | 8006 (debug) |
| `services/07_football_data` | `football-data` | member5 | Python · FastAPI · httpx | 8000 | 8007 (debug) |
| root + `deploy/` + `eval/` | `postgres`, `redis`, (`prometheus`, `grafana`) | member6 | YAML · Dockerfile · Makefile · Bash | – | – |

- ทุก container (ยกเว้น `web`) ฟัง port 8000 ภายใน คุยกันด้วยชื่อ เช่น `http://router:8000` — **ห้ามใช้ localhost ระหว่าง service**
- Postgres ตัวเดียว แยก schema: `app` (02) · `football` (07) · เจ้าของ schema เท่านั้นที่เขียนได้ คนอื่นอ่านผ่าน API
- Redis ใช้เป็น broker ของ Celery + cache ของ 02

## 5. 02 API Backend — เอาอะไรมาจาก Travel Safety และตัดอะไรทิ้ง

| เอามา (ปรับใช้) | ตัดทิ้งในรอบนี้ | เหตุผลที่ตัด |
|---|---|---|
| โครง `app/api`, `app/core`, `app/domain`, `app/infrastructure` | Keycloak / JWKS | ใช้ JWT HS256 + httpOnly cookie พอ |
| Problem-JSON error handler + error code กลาง | MinIO + data export | ไม่มีไฟล์ให้เก็บ |
| middleware: request context (`X-Request-ID`), body guard, rate limit, security headers | OpenTelemetry | ใช้ `X-Request-ID` + JSON log แทน |
| AgentClient → **RouterClient** (deadline, retry, circuit breaker) | idempotency key | แชทไม่ใช่ธุรกรรม ส่งซ้ำไม่เสียหาย |
| conversations + follow-up, feedback | column encryption, retention/purge | ไม่มีข้อมูลอ่อนไหว |
| Celery worker + beat (เปลี่ยนงานเป็น "สั่ง 07 ตามเวลา") | safety review queue, training data export | เกินขอบเขต 7 วัน |
| admin tools + audit log → **ย่อเหลือระบบ Admin หัวข้อ 5.1** | | |
| Alembic migration, pytest + testcontainers, CI | trips / live alerts | ไม่มีในโดเมนนี้ |

### 5.1 ระบบ Admin (เว็บ `/admin/*` → api `/api/admin/*` · รายละเอียดใน `CONTRACT.md` §1.1)

| หน้า | ทำอะไร | ระดับ | งานที่เกิดใน service อื่น |
|---|---|---|---|
| Dashboard | สถิติ route / layer / feedback / latency / fallback | Must | – |
| Pipeline ข้อมูล | quota API-Football · ingest ล่าสุด · รายการ job · ปุ่มสั่ง ingest / สร้างรายงาน | Must | 07: `GET /jobs` |
| Feedback & Log | คำตอบที่โดนกดไม่ชอบ + trace + sources · ค้น log ด้วย `request_id` / route / fallback | Must | – |
| ตรวจรายงาน | รายงานประจำสัปดาห์เป็น `draft` ก่อน → admin แก้ → publish (เข้า KB ตอนนี้) / unpublish | Should | 07: สถานะรายงาน · 05: upsert/delete ตอน publish |
| Audit log | ใครทำอะไร เมื่อไร กับอะไร | Should | – |
| ผู้ใช้ | รายชื่อ · เปลี่ยน role · ระงับบัญชี (แก้ตัวเองไม่ได้) | Could | – |
| Knowledge Base | สถิติ index · ลบเอกสาร · reindex | Could | 05: `POST /index/rebuild` |

- สิทธิ์ตรวจที่ api ทุกครั้ง (`role = admin`) หน้าเว็บซ่อนเมนูอย่างเดียวไม่พอ · web เรียกได้แค่ api ไม่เรียก service ภายในตรง
- ทุก action ที่เปลี่ยนข้อมูลบันทึก audit (แบบเดียวกับ Travel Safety)
- **กันเดโมไม่มีรายงานโชว์**: env `REPORT_AUTO_PUBLISH=true` ทำให้รายงาน publish เองแบบเดิม — ใช้ถ้าหน้าตรวจรายงาน (Should) ไม่ทัน
- Admin ทำให้ "Feedback Loop" ในผังอาจารย์จับต้องได้: ผู้ใช้กดไม่ชอบ → admin เห็นพร้อม trace → รู้ว่าพังที่ router / retrieval / generation

## 6. ข้อมูลฟุตบอลจาก API

| แหล่ง | บทบาท | ข้อจำกัด free plan | ใช้กับ endpoint |
|---|---|---|---|
| **football-data.org** v4 | **หลัก** — fixtures, ผล, ตารางคะแนน, ดาวซัลโว | 10 ครั้ง/นาที ไม่จำกัดต่อวัน · สกอร์มีดีเลย์ · ไม่มี lineups/events | `competitions/PL/matches`, `competitions/PL/standings`, `competitions/PL/scorers` |
| **API-Football** (api-sports.io) | **เสริม** — events (ใครยิง นาทีไหน), lineups, สถิตินัด | **100 ครั้ง/วัน ต่อ key** · ต้องตรวจ D1 ว่าเข้าถึงฤดูกาลปัจจุบันได้หรือไม่ | `fixtures/events`, `fixtures/lineups`, `fixtures/statistics` |

**กติกาใช้ quota**
- ตอน dev ทุกคนใช้ key ของตัวเอง (สมัครฟรี) · key สำหรับวันสาธิตเก็บแยก ใช้วันนั้นเท่านั้น
- 07 ดึงรายละเอียดจาก API-Football **เฉพาะนัดที่สถานะ FINISHED และยังไม่เคยดึง** — PL สัปดาห์ละ 10 นัด × 3 endpoint = 30 ครั้ง อยู่ในงบ
- 07 นับ quota เองและหยุดที่ 90 ครั้ง/วัน (กันพลาด) · ดูได้ที่ field `quota` ของ `GET /football/status` (CONTRACT §7) · หน้า admin เห็นผ่าน `GET /api/admin/pipeline` (§1.1)
- **แผนสำรองถ้า D1 พบว่า API-Football free ดึงฤดูกาลปัจจุบันไม่ได้**: ใช้ football-data.org อย่างเดียวสำหรับข้อมูลสด (รายงานระดับสกอร์ + ตารางคะแนน) และใช้ API-Football กับฤดูกาลที่แล้วเพื่อสาธิต match report แบบละเอียด — เขียนบอกตรง ๆ ในสไลด์

**ชื่อทีมและชื่อเล่นภาษาไทย** — 07 เป็นเจ้าของไฟล์ `team_aliases.json` (id ทีมจาก football-data.org → ชื่อทางการ + ชื่อเล่น เช่น ผี/แมนยู, หงส์, ปืนใหญ่, สิงห์บลู, เรือใบ, ไก่เดือยทอง) ให้ 03 ใช้ในชั้น rules และ 05 ใช้ขยายคำค้น นี่คือการแก้ปัญหา week5 #1 (vocabulary mismatch) ในโดเมนใหม่

## 7. ตัวแก้ปัญหาจาก week5 ต้องติดมาทุกข้อ

| # | ปัญหา week5 | อยู่ที่ service | ทำอย่างไรในงานนี้ |
|---|---|---|---|
| 1 | Vocabulary mismatch | 03, 05 | ขยายคำค้นด้วย `team_aliases.json` + แปลคำถามไทยเป็นอังกฤษก่อนเข้า BM25 (คลัง trivia เป็นภาษาอังกฤษ) · embedding ใช้โมเดล multilingual เดิม |
| 2 | Data quality (ซ้ำ/ขัดแย้ง) | 05, 07 | dedupe คลัง trivia ตอน ingest · เอกสารข้อมูลสดใช้ `doc_id` คงที่ upsert ทับ ไม่มีวันซ้ำ |
| 3 | Chunking ตัดกลางคำ | 05 | 1 คู่ถาม-ตอบ = 1 chunk · เอกสาร match report ตัดตามหัวข้อ ไม่ตัดตามจำนวนตัวอักษร |
| 4 | Memory ของ follow-up | 03 | router ส่ง history ≤ 10 ข้อความเข้าขั้นเขียนคำถามใหม่ ("แล้วนัดก่อนหน้าล่ะ" → "ผลนัดก่อนหน้าของ Arsenal") |
| 5 | Golden set เอียง | 05, member6 | ใช้ golden set ที่แก้แล้ว + เติมข้อถามผลแข่ง/ตารางคะแนน 20 ข้อ (ตอบตรวจได้กับ DB) |

## 8. การวัดผล (เจ้าของไฟล์ `eval/`: member6 · เจ้าของข้อมูลแต่ละชุดตามตาราง)

| ตัวชี้วัด | ชุดข้อมูล | เจ้าของชุดข้อมูล |
|---|---|---|
| retrieval hit@1 / hit@5 / MRR — เทียบ BM25 / vector / hybrid | `eval/golden_trivia.jsonl` (จาก week4 ที่แก้ตาม week5) + `eval/golden_match.jsonl` 20 ข้อ | sakda1306 |
| route accuracy + % ไม่ต้องเรียก LLM | `services/03_ai_router_agent/tests/routing_cases.jsonl` 40 ข้อ ครบ 5 route | member2 |
| % citation ถูก · % ตัวเลขสกอร์ในคำตอบตรงกับ DB | ผลรัน end-to-end บน golden ทั้งสองชุด | member4 + member5 |
| latency p50 / p95 ต่อ route | log ของ 02 | member6 |

ผลรวมทั้งหมดออกเป็น `eval/report.html` ใน D6 — **จุดขายตอนนำเสนอ**

## 9. ขอบเขต (MoSCoW)

- **Must** (ไม่มี = ไม่ผ่าน): ถามตอบได้ครบ 5 route · RAG มี citation จริง · ถามผลแข่ง / ตารางคะแนน / โปรแกรม PL ฤดูกาลปัจจุบันได้ · รายงานประจำสัปดาห์ (สั่งรันเองได้ + beat รันตามเวลา) · history + follow-up · feedback (ให้คะแนนคำตอบ) · **Admin: Dashboard + Pipeline + Feedback & Log** · `make up` คำสั่งเดียวทั้งระบบขึ้น
- **Should**: ตัวเลขใน `eval/report.html` · **Admin: ตรวจรายงานก่อนเผยแพร่ + Audit log** · หน้าตารางคะแนน/โปรแกรมบนเว็บ · Gemini fallback ทดสอบแล้วจริง · แผงแสดง trace การตัดสินใจของ agent · badge "ข้อมูล ณ เวลา ..."
- **Could**: `/local/predict` (Elo หรือ Poisson จากผลที่เก็บไว้) · reranker · SSE streaming ช่วง api → web · Prometheus + Grafana · รายงานเฉพาะทีมที่ผู้ใช้เชียร์ · **Admin: จัดการผู้ใช้ + Knowledge Base**
- **Won't (รอบนี้)**: ลีกอื่นนอกจาก PL · Keycloak / MinIO / OpenTelemetry · อัปโหลดไฟล์ · ข้อมูลสดแบบวินาทีต่อวินาที

## 10. LLM provider ที่ใช้ร่วมกัน

- **หลัก: Groq** (`LLM_PRIMARY=groq`) · **สำรอง: Gemini** (`LLM_FALLBACK=gemini`) — ใช้ไลบรารี `openai` ตัวเดียวทั้งทีม สลับเจ้าด้วย `base_url` (แบบเดียวกับ RAG week4)
- ชื่อโมเดลอ่านจาก env เสมอ (`GROQ_MODEL`, `GEMINI_MODEL`) และเช็กตอน startup ว่ายังมีอยู่ — provider ถอดโมเดลได้โดยไม่แจ้ง
- ตอน dev ทุกคนใช้ key ของตัวเอง · key อยู่ใน `.env` ที่ root เท่านั้น **ไม่ commit**
- ด่าน safety ทั้งหมดอยู่ที่ 06 (ไม่พึ่ง provider กรองให้) — โดยเฉพาะ **ห้ามให้ทีเด็ด / อัตราต่อรองพนัน**

## 11. ความเสี่ยงหลัก

| ความเสี่ยง | ผลกระทบ | การรับมือ |
|---|---|---|
| API-Football free ดึงฤดูกาลปัจจุบันไม่ได้ | ไม่มีรายละเอียดนัดของสัปดาห์นี้ | ตรวจ D1 · แผนสำรองในหัวข้อ 6 |
| LLM เดาผลแข่งเอง (hallucination) | ตอบผลผิด ทำลายความน่าเชื่อถือ | 06 ห้ามตอบตัวเลขที่ไม่อยู่ใน context · eval ตรวจสกอร์กับ DB |
| คลัง trivia ภาษาอังกฤษ แต่ผู้ใช้ถามไทย | BM25 ค้นไม่เจอ | แปลคำถามก่อน BM25 + embedding multilingual |
| sakda1306 ถือ 2 service บน critical path (02, 05) | ถ้าช้า ทั้งทีมรอ | 05 มาก่อน (โค้ด week4 พร้อมแล้ว) · stub ของ 02 พร้อมตั้งแต่ D1 · member6 รับงาน infra ทั้งหมดแทนหัวหน้า |
| quota หมดระหว่างสาธิต | หน้าเว็บว่าง | แชทไม่เรียก API ภายนอก · `make warmup` ดึงข้อมูลคืนก่อนสาธิต · อัดวิดีโอสำรอง |
