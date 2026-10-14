# SCHEDULE.md — ใครทำอะไร วันไหน · ผู้ช่วยฟุตบอล (ทีม D-II · 7 คน · 7 วัน)

> ส่งให้ทุกคน · อ่านคู่กับ `00_PLAN_OVERVIEW.md` และ `CONTRACT.md`
> **กฎข้อเดียวที่สำคัญที่สุด: ไม่มีใครต้องหยุดรอใคร** ระหว่างที่ของคนอื่นยังไม่เสร็จ ให้เรียก stub ของเขา
> (หัวหน้า + member6 ทำ stub ให้ทุก service ใน D1 และ stub ตอบตาม `CONTRACT.md` เป๊ะ)
>
> ชื่อ `member1`–`member6` เป็น placeholder · วันที่จริงเติมในตารางปฏิทินเมื่อทีมตกลงวันเริ่ม

## ใครถืออะไร

| คน | โมดูล | ภาระ | หมายเหตุ |
|---|---|---|---|
| **sakda1306** (หัวหน้า) | 02 API Backend + Response/Log · 05 Retrieval/RAG · รีวิว PR · คุม integration | หนัก — แต่มีต้นแบบพร้อม (backend Travel Safety, RAG week4 + week5) | งาน infra ทั้งหมดยกให้ member6 |
| member1 | 01 Web App (+ หน้า Admin) | กลาง–หนัก | หน้าตาตอนสาธิต · หน้า admin ใช้ component ตาราง/ปุ่มชุดเดียวกันทั้งหมด |
| member2 | 03 AI Router / Agent | หนัก — **critical path** | |
| member3 | 04 AI Engines (General AI + Local AI) | กลาง | predictor เป็น Could |
| member4 | 06 LLM Generation (+ รายงานประจำสัปดาห์) | กลาง | ด่าน safety อยู่ที่นี่ที่เดียว |
| member5 | 07 Football Data (ingestion + pipeline รายสัปดาห์) | กลาง–หนัก | ต้องตรวจ quota API-Football วันแรก |
| member6 | Deploy & Monitoring (compose, stub, CI, eval, monitoring) | กลาง | รีวิว PR ของหัวหน้า |

## ปฏิทิน

| วัน | วันที่ | ชื่อรอบ |
|---|---|---|
| D1 | (เติม) | ล็อก CONTRACT · repo + skeleton + stub ทุก service · ทุกคนอ่านเอกสาร · งานที่ไม่ต้องรอ repo เริ่มได้เลย |
| D2 | (เติม) | ทุกคน `make up` ได้ · แทน stub ด้วยโค้ดจริงชิ้นแรก |
| D3 | (เติม) | **Must ของตัวเองรันเดี่ยวผ่าน · PR แรกเข้า develop** |
| D4 | (เติม) | **Integration รอบ 1** — ถามผ่านหน้าเว็บจริงแล้วได้คำตอบพร้อมอ้างอิง ทั้งคำถาม trivia และคำถามผลแข่ง |
| D5 | (เติม) | แก้บั๊กรอบ 1 · รายงานประจำสัปดาห์ครบวงจร · ทำ Should · **จุดตัดสินใจถ้าใครไม่ทัน** |
| D6 | (เติม) | **Feature freeze 20:00** · รัน eval · merge develop → main |
| D7 | (เติม) | ซ้อมนำเสนอ · ทำสไลด์ · อัดวิดีโอสำรอง |
| **นำเสนอ** | (เติม) | ทุกคนพูดส่วนตัวเองคนละ 2 นาที |

## ตารางรวม — ดูว่าวันนี้ใครต้องส่งอะไร

| | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|
| **01 Web** · member1 | ติดตั้งเครื่องมือ · mock ตาม contract | หน้า login + chat บน mock | ต่อ api จริง · **PR แรก** | sources + ป้าย route + badge "ข้อมูล ณ" · ปุ่มให้คะแนน · sidebar | หน้ารายงาน + ตารางคะแนน + แผง trace · **admin: layout + Dashboard** | **admin: Pipeline + Feedback & Log** (+ ตรวจรายงาน) · error ครบ | ซ้อมสาธิตหน้าเว็บ + หน้า admin |
| **02 API** · sakda1306 | stub `/api/*` ตอบได้ ← 01 รอ | **login + `/api/chat` บน stub router** ← 01 รอ | history / sessions / feedback · **PR แรก** | ต่อ router จริง · RouterClient timeout + breaker | beat สั่ง 07 · `/api/football/*` · **`/api/admin/*` (Must) + audit** | admin Should · เทส + เก็บงาน | ซ้อม |
| **03 Router** · member2 | เขียน `routing_cases.jsonl` 40 ข้อ | cascade guard + rules + LLM บน stub | **5 route ครบบน stub** · **PR แรก** | **ต่อ 04 / 05 / 06 จริง ← ทุกคนรอ** | ชั้น classifier · follow-up rewrite · ลำดับถอย · trace | วัด route accuracy | ซ้อม |
| **04 Engines** · member3 | เริ่ม `data/intents.csv` | **`/general` ใช้ได้จริง** ← 03 รอ | **`/local/classify` ใช้ได้** · **PR แรก** | ปรับ dataset จากคำที่พลาด | เทียบ TF-IDF / embedding / ถาม LLM · (Could) `/local/predict` | เก็บตัวเลข | ซ้อม |
| **05 Retrieval** · sakda1306 | ย้าย RAG week4 เข้า service · map golden set | ingest คลัง trivia (dedupe + 1 QA = 1 chunk) · index ขึ้น | **`/search` + filters ใช้ได้** ← 03, 06 รอ · **PR แรก** | **`/index/upsert` ใช้ได้** ← 07 รอ | eval hit@k / MRR เทียบ 3 แบบ + golden_match 20 ข้อ | เก็บตัวเลข | ซ้อม |
| **06 Generation** · member4 | prompt template + fixtures 5 ชุด | `grounded` บน fixtures | **`grounded` ใช้ได้จริง** ← 03 รอ · **PR แรก** | `passthrough` · citation check | **`/report/weekly`** ← 07 รอ · safety (พนัน) · fallback provider | วัด % citation ถูก | ซ้อม |
| **07 Football Data** · member5 | **ตรวจ quota + ฤดูกาลที่ API-Football free เข้าถึงได้** · ออกแบบตาราง | ดึง teams + fixtures + standings จาก football-data.org ลง DB | `/football/*` ใช้ได้ · `team_aliases.json` · **PR แรก** | ดึงรายละเอียดนัดจาก API-Football · สร้างเอกสาร → upsert เข้า 05 | **`/reports/weekly/run` ครบวงจร** · สถานะ draft/publish · `GET /jobs` | ตรวจ quota + ข้อมูลตรงกับเว็บทางการ | ซ้อม |
| **Deploy** · member6 | **compose + stub ทุก service + Makefile** ← ทุกคนรอ | CI (lint + test) · ช่วยคนที่ติด docker | smoke test `make smoke` · รีวิว PR หัวหน้า | **คุม integration ร่วมกับหัวหน้า** · ไล่ `request_id` | runner ของ `eval/` · smoke เคส admin | **`eval/report.html`** · `make warmup` | อัดวิดีโอสำรอง |

---

## 01 — Web App · member1

| วัน | ต้องเสร็จ |
|---|---|
| D1 | ติดตั้ง Node 20 + clone repo · อ่าน `CONTRACT.md` §0, §1 ให้จบ · สร้าง `mocks/` ที่คืน `ChatResponse`, `WeeklyReport`, standings ปลอมตาม contract |
| D2 | หน้า login + หน้า chat ทำงานบน mock ได้ครบ |
| D3 | สลับไปต่อ `api` จริง (02 มี login + chat บน stub ให้แล้วตั้งแต่ D2) · **เปิด PR แรก** |
| D4 | แสดง `sources` เป็นรายการใต้คำตอบ กด `[1]` แล้วเลื่อนไปถูก · ป้าย route ภาษาไทย (CONTRACT "ป้ายภาษาไทย") · badge "ข้อมูล ณ `data_as_of`" · latency · ปุ่มให้คะแนน · sidebar session |
| D5 | **หน้ารายงานประจำสัปดาห์** (เลือกนัดที่ได้) · **หน้าตารางคะแนน + โปรแกรม** · แผงแสดงการตัดสินใจของ agent จาก `trace` · ปุ่มคำถามตัวอย่าง 5 ปุ่ม (trivia / ผลแข่ง / ตาราง / สรุปสัปดาห์ / นอกขอบเขต) · **admin: layout `/admin/*` (ซ่อนเมนูถ้าไม่ใช่ admin, จัดการ 403) + หน้า Dashboard จาก `/api/admin/stats`** |
| D6 | **admin: หน้า Pipeline (ปุ่มสั่ง + ดูสถานะ job) + หน้า Feedback & Log (เปิดดู `AdminMessage` พร้อม trace)** · ถ้าทัน: หน้าตรวจรายงาน (Should) · จัดการ error ครบ (401/403/409/429/502/504) · responsive · **หยุดเพิ่มฟีเจอร์ 20:00** — หน้า Could (ผู้ใช้, KB) ทำเฉพาะถ้าเสร็จก่อน freeze |
| D7 | ซ้อมสาธิต — คุณเป็นคนกดสาธิตหน้าเว็บ ต้องกดได้ลื่นไม่ติดขัด · เดโม feedback loop: กดไม่ชอบ → เปิดหน้า admin ดู trace |

**คุณรอใคร**: 02 (ใช้ mock ไปก่อนได้ ไม่ต้องหยุด) · **ใครรอคุณ**: ไม่มี แต่คุณคือหน้าตาตอนสาธิต

---

## 02 — API Backend + Response/Log · sakda1306

| วัน | ต้องเสร็จ |
|---|---|
| D1 | ยก skeleton จาก backend Travel Safety (core / errors / middleware / config) · ตัดส่วนที่อยู่ในรายการ "ตัดทิ้ง" ของ `00_PLAN_OVERVIEW.md` หัวข้อ 5 · stub `/api/*` ตอบตาม contract |
| D2 | **login + `/api/chat` เรียก stub ของ router ได้** — ข้อนี้ห้ามเลื่อน เพราะ 01 ต่อของจริงไม่ได้จนกว่าจะมี · ตาราง users (มี `role`, `disabled`) / sessions / messages + seed `admin` 1 + `demo1`–`demo3` · stub `/api/admin/*` ตอบตาม contract ← 01 ใช้ D5 |
| D3 | `/api/sessions`, `/api/history`, `/api/feedback` (กรณี 409 `MESSAGE_NOT_READY`) · **เปิด PR แรก** (member6 รีวิว) |
| D4 | ต่อ router ตัวจริง · RouterClient: timeout 45s, retry, circuit breaker · error mapping 502/504 · ส่ง `trace` ต่อให้หน้าเว็บ |
| D5 | Celery beat ตามตารางใน CONTRACT §7 · proxy `/api/football/*` · **`/api/admin/*` ระดับ Must** (stats, pipeline, jobs, feedback, messages, logs) + dependency ตรวจ `role=admin` + ตาราง audit · rate limit |
| D6 | admin ระดับ Should (reports, audit) · pytest ครบเส้นหลัก + เทสสิทธิ์ (user ธรรมดาเรียก `/api/admin/*` ต้องได้ 403) · เก็บงาน · **หยุดเพิ่มฟีเจอร์ 20:00** |
| D7 | ซ้อม — เตรียมอธิบายว่ายกอะไรมาจาก Travel Safety และตัดอะไรทิ้งเพราะอะไร |

**คุณรอใคร**: 03 และ 07 (ใช้ stub ไปก่อน) · **ใครรอคุณ**: 01 ตั้งแต่ D2

---

## 03 — AI Router / Agent · member2 — **critical path ของทีม**

| วัน | ต้องเสร็จ |
|---|---|
| D1 | **เขียน `tests/routing_cases.jsonl` 40 ข้อ ครบทั้ง 5 route** (อย่างน้อย 8 ข้อต่อ route ใช้ชื่อเล่นทีมภาษาไทยด้วย) ทำก่อนเขียนโค้ด · ไม่ต้องรอ repo |
| D2 | cascade ชั้น guard + rules (ชื่อทีม / คำบอกเวลา / คำพนัน) + LLM บน stub · สคริปต์วัด route accuracy |
| D3 | **5 route ทำงานครบบน stub** · แปลงคำบอกเวลาเป็น `matchweek` / `date_*` จาก `context` · **เปิด PR แรก** |
| D4 | **ต่อ 04 / 05 / 06 ตัวจริง ให้เส้น `football_rag` วิ่งครบทั้ง trivia และผลแข่ง** ← ทั้งทีมรอข้อนี้ ห้ามเลื่อน |
| D5 | ชั้น classifier (ใช้ `/local/classify` + ตาราง map ใน CONTRACT §3) · rewrite follow-up จาก history (แก้ปัญหา week5 #4) · ลำดับถอยของ `football_rag` · คืน `trace` |
| D6 | วัด route accuracy บน 40 ข้อ + % ที่ไม่ต้องเรียก LLM เขียนตัวเลขลง README · **หยุด 20:00** |
| D7 | ซ้อม — เตรียมอธิบายว่าทำไมใช้ cascade และทำไมคำถามผลแข่ง **ห้ามถอยไป general_ai** |

**คุณรอใคร**: 04, 05, 06 (ใช้ stub ไปก่อนได้เต็มที่) · 07 สำหรับ `/football/teams` (D3) · **ใครรอคุณ**: 02 และ integration ทั้งระบบ

---

## 04 — AI Engines · member3

| วัน | ต้องเสร็จ |
|---|---|
| D1 | **เริ่มเขียน `data/intents.csv`** 8 หมวด × 25–30 ตัวอย่าง (ไทย + อังกฤษ) ไม่ต้องรอ repo · ขอ 40 เคสจาก member2 มาดูเป็นตัวอย่าง (แต่ห้ามเอามาเทรน — ใช้เป็นชุดทดสอบ) |
| D2 | **`POST /general` ใช้ได้จริง** ← 03 รอ · fallback Groq → Gemini |
| D3 | `train.py` + **`POST /local/classify` ใช้ได้** (TF-IDF + LogisticRegression) · **เปิด PR แรก** |
| D4 | ปรับ dataset จากคำที่ classifier พลาดบน routing cases · จำกัด token ของ `/general` |
| D5 | เทียบ TF-IDF vs embedding vs ถาม LLM ทำตาราง 3 แถว · (Could) `/local/predict` ด้วย Poisson จากผลที่ 07 เก็บไว้ ถ้าไม่ทำ ตอบ 501 ตาม contract |
| D6 | เขียน accuracy ลง README · **หยุด 20:00** |
| D7 | ซ้อม — เตรียมอธิบายว่าทำไมต้องมีทั้ง General AI และ Local AI |

**คุณรอใคร**: ไม่รอใครเลย เริ่มได้ทันที · **ใครรอคุณ**: 03 (D2 `/general`, D3 `/classify`)

---

## 05 — Retrieval / Knowledge (RAG) · sakda1306 — **เริ่มก่อน 02**

| วัน | ต้องเสร็จ |
|---|---|
| D1 | ย้าย `src/` ของ RAG week4 (hybrid_retriever, vector_store, embedding_model, rerankers, query_transform) เข้าโครง FastAPI · map golden set เดิมให้ใช้ `doc_id` แบบใหม่ |
| D2 | `ingest.py` คลัง trivia: dedupe + ตัดข้อขัดแย้ง (week5 #2) · 1 คู่ถาม-ตอบ = 1 chunk (week5 #3) · index แรกขึ้นใน volume |
| D3 | **`POST /search` + filters ใช้ได้จริง** ← 06 กับ 03 รอ · **เปิด PR แรก** |
| D4 | **`POST /index/upsert` + `DELETE /index/{doc_id}`** ให้ BM25 กับ FAISS ตรงกันเสมอ ← 07 รอ (publish / unpublish รายงานใช้สองตัวนี้) · ขยายคำค้นด้วย `team_aliases.json` (week5 #1) · (Could) `POST /index/rebuild` |
| D5 | `eval_retrieval.py` วัด hit@1 / hit@5 / MRR เทียบ BM25 / vector / hybrid บน golden_trivia + เขียน `golden_match.jsonl` 20 ข้อ (week5 #5) |
| D6 | ตารางตัวเลขลง README · **หยุด 20:00** |
| D7 | ซ้อม — เตรียมอธิบายว่า 5 ปัญหาจาก week5 ถูกแก้ตรงไหนในระบบนี้ พร้อมตัวเลข |

**คุณรอใคร**: 07 สำหรับเอกสารข้อมูลสด (D4) · **ใครรอคุณ**: 06 และ 03 ตั้งแต่ D3 · 07 ตั้งแต่ D4

---

## 06 — LLM Generation · member4

| วัน | ต้องเสร็จ |
|---|---|
| D1 | เขียน `prompts/grounded.j2` + `tests/fixtures/` 5 ชุด (trivia 2 · ผลแข่ง 2 · context ไม่พอ 1) เขียน contexts ตัวอย่างเอง ไม่ต้องรอ 05 |
| D2 | mode `grounded` ทำงานบน fixtures ได้ · กฎ "ตัวเลขต้องมาจาก context เท่านั้น" |
| D3 | **`grounded` ใช้ได้จริง** ← 03 รอ · **เปิด PR แรก** |
| D4 | mode `passthrough` · **citation verification** ตัด `[n]` ที่ไม่มีจริง |
| D5 | **`POST /report/weekly`** ← 07 รอ (เขียนบน fixture ของ matchweek ปลอมก่อนได้) · safety: ทีเด็ด / ราคาพนัน / prompt injection · fallback provider · สคริปต์วัด % citation ถูก |
| D6 | เขียนตัวเลขลง README · **หยุด 20:00** |
| D7 | ซ้อม — เตรียมโชว์ prompt template และตัวอย่างที่ระบบ "ไม่ยอมเดาผล" |

**คุณรอใคร**: 05 (ใช้ fixtures ไปก่อน) · **ใครรอคุณ**: 03 ตั้งแต่ D3 · 07 ตั้งแต่ D5

---

## 07 — Football Data · member5

| วัน | ต้องเสร็จ |
|---|---|
| D1 | **สมัคร key ทั้งสองเจ้า · ยิงทดสอบ 1 ครั้งว่า API-Football free เข้าถึงฤดูกาล 2026 ได้ไหม แล้วรายงานในกลุ่มภายในวันนี้** (ถ้าไม่ได้ → ใช้แผนสำรองใน `00_PLAN_OVERVIEW.md` หัวข้อ 6) · ออกแบบตาราง schema `football` |
| D2 | ดึง teams + fixtures + standings + scorers จาก football-data.org ลง DB · ตัวนับ quota |
| D3 | `/football/status`, `/standings`, `/fixtures`, `/matches/{id}`, `/teams` ใช้ได้ · **`team_aliases.json`** (20 ทีม PL + ชื่อเล่นไทย) ส่งให้ 03 และ 05 · **เปิด PR แรก** |
| D4 | ดึงรายละเอียดนัดที่จบแล้วจาก API-Football (events / lineups / stats) · map id สองแหล่ง · **สร้างเอกสารตามรูปแบบ `doc_id` ใน CONTRACT §6 แล้ว upsert เข้า 05** |
| D5 | **`/reports/weekly/run` ครบวงจร**: ดึงแมตช์วีค → เรียก 06 → เก็บเป็น **draft** · publish / unpublish / PATCH (publish = upsert เข้า 05 สำเร็จก่อนเปลี่ยนสถานะ) · env `REPORT_AUTO_PUBLISH` · `GET /jobs` + `triggered_by` · กันสั่งซ้ำ (`JOB_ALREADY_RUNNING`) |
| D6 | สุ่มตรวจสกอร์ / ตารางคะแนน 10 จุดเทียบเว็บทางการ · **หยุด 20:00** |
| D7 | ซ้อม — เตรียมอธิบายว่าใช้ quota 100 ครั้ง/วันยังไงให้พอ |

**คุณรอใคร**: 05 (`/index/upsert` D4 — ใช้ stub ไปก่อน) · 06 (`/report/weekly` D5 — ใช้ stub ไปก่อน) · **ใครรอคุณ**: 03 (`/football/teams` D3) · 02 (`/football/*` D5) · 05 (เอกสารข้อมูลสด D4)

---

## Deploy & Monitoring · member6

| วัน | ต้องเสร็จ |
|---|---|
| D1 | **`docker-compose.yml` + stub ทุก service (FastAPI ตอบ JSON ตาม contract) + `Makefile` (`up`, `down`, `logs`, `smoke`)** ← ทุกคนรอ ต้องเสร็จก่อนสิ้นวัน · `.env.example` · volume สำหรับ index + HF model cache + postgres |
| D2 | CI บน GitHub Actions: lint + test ต่อ service (รันเฉพาะโฟลเดอร์ที่เปลี่ยน) · ช่วยคนที่ติด docker |
| D3 | `make smoke` ยิง `/health` ทุกตัว + 1 คำถามต่อ route + login `admin` แล้วเรียก `/api/admin/stats` (และ `demo1` ต้องได้ 403) · รีวิว PR แรกของหัวหน้า (02, 05) |
| D4 | **คุม integration รอบ 1 ร่วมกับหัวหน้า** ไล่ `request_id` ทีละ hop · เจอบั๊กเปิด Issue ไม่แก้เอง |
| D5 | runner ของ `eval/` (รวมตัวเลขจากทุกคน) · (Could: Prometheus + Grafana) |
| D6 | **รัน eval → `eval/report.html`** · `make warmup` (ingest + index + รายงานล่าสุด **และ publish ให้** ก่อนสาธิต) |
| D7 | อัดวิดีโอสำรองเดโม · เช็ก `git shortlog -sn` ว่าทุกคนมี commit กระจายทั้งสัปดาห์ |

**คุณรอใคร**: ไม่รอใคร · **ใครรอคุณ**: ทุกคนรอ compose + stub ใน D1

---

## หัวหน้า (sakda1306) — งานคุมทีม นอกจาก 02 และ 05

| วัน | ต้องเสร็จ |
|---|---|
| D1 | **สร้าง repo + branch `develop` + branch ของทุกคน + branch protection + `CODEOWNERS`** · ประชุม 30 นาทีล็อก `CONTRACT.md` v1.1 · ส่งคลัง trivia + golden set ให้ทุกคนที่ต้องใช้ |
| D2–D3 | รีวิว PR (ภายในวันเดียวกับที่เปิด) |
| D4 | คุม integration รอบ 1 ร่วมกับ member6 |
| D5 | **จุดตัดสินใจถ้าใครไม่ทัน** (ดูตารางล่างสุด) |
| D6 | **freeze 20:00** → รัน eval → merge develop → main → สร้าง tag (หัวหน้าเท่านั้น) |
| D7 | คุมซ้อม · ตรวจ repo รอบสุดท้ายตาม `GIT_FLOW.md` หัวข้อ 4.1 ทั้ง repo |

---

## ถ้าตามไม่ทัน ตัดอะไรได้บ้าง

ตัดจากล่างขึ้นบน **ห้ามตัดจากบนลงล่าง**

| ลำดับ | สิ่งที่ต้องมี | ตัดได้ไหม |
|---|---|---|
| 1 | `make up` แล้วทั้งระบบขึ้น | **ไม่ได้** |
| 2 | ถามคำถาม trivia แล้วได้คำตอบพร้อมอ้างอิงผ่านหน้าเว็บ | **ไม่ได้** |
| 3 | ถามผลแข่ง / ตารางคะแนน PL แล้วได้ข้อมูลจริงพร้อมเวลาที่ดึง | **ไม่ได้** |
| 4 | 5 route ทำงานครบ | ไม่ได้ |
| 5 | รายงานประจำสัปดาห์ (อย่างน้อยสั่งรันเองได้) | ไม่ได้ |
| 6 | history + follow-up + feedback | ไม่ได้ |
| 6.5 | Admin: Dashboard + Pipeline + Feedback & Log | ไม่ควรตัด — ใช้คุมเดโมและโชว์ feedback loop |
| 7 | ตัวเลขวัดผลใน `eval/report.html` | ไม่ควรตัด เป็นจุดขาย |
| 8 | หน้าตารางคะแนน / โปรแกรมบนเว็บ · Admin: ตรวจรายงาน + Audit (ตัดแล้วตั้ง `REPORT_AUTO_PUBLISH=true`) | ตัดได้ |
| 9 | `/local/predict` · reranker · streaming · Grafana · Admin: ผู้ใช้ + Knowledge Base | ตัดได้ก่อนอย่างอื่น |

**ทางยุบถ้าคนขาด** (หัวหน้าตัดสินใจ D5)
- 07 ไม่ทัน → ใช้ football-data.org อย่างเดียว ตัดรายละเอียดนัดจาก API-Football · รายงานสัปดาห์เหลือระดับสกอร์ + ตาราง
- 04 ไม่ทัน → router ใช้แค่ rules + LLM (ข้ามชั้น classifier) · `/general` ต้องมี
- **ห้ามยุบ 03 และ 05** — ถ้าไม่มีสองตัวนี้ระบบไม่เป็น agent และไม่เป็น RAG
