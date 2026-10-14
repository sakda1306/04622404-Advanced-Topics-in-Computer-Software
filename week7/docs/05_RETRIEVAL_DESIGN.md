# 05 Retrieval / Knowledge — แบบระบบ · `retrieval`

> เจ้าของ: sakda1306 · สถานะ: ใช้งานแล้ว (PR ①–③ อยู่ใน `develop` ผ่าน #5 และ #13) · หัวข้อ 10 ยังเป็นข้อเสนอ · อ้างอิง: `00_PLAN_OVERVIEW.md` หัวข้อ 3, 7, 8 · `CONTRACT.md` §0, §4, §6 · `SCHEDULE.md` หัวข้อ 05
> เอกสารนี้บอกว่า 05 ทำอะไร และตัดสินใจอะไรไปแล้วพร้อมเหตุผล ลำดับงานละเอียดอยู่ใน implementation plan แยกต่างหาก

---

## 1. เป้าหมายและขอบเขต

05 เป็นแกน RAG ของระบบ: เก็บ Knowledge Base (คลัง trivia + เอกสารข้อมูลสดจาก 07) และค้นแบบ hybrid (BM25 + FAISS + RRF) ให้ router ตามเส้น `football_rag` ยกแกนมาจาก RAG week4 และติดตัวแก้ปัญหาจาก week5 ข้อ 1, 2, 3, 5

| ผู้เรียก | ใช้อะไร | ตาม |
|---|---|---|
| 03 router | `POST /search` | CONTRACT §4 |
| 07 football-data | `POST /index/upsert`, `DELETE /index/{doc_id}` | CONTRACT §6 |
| 02 api (หน้า admin) | `GET /index/stats`, `POST /index/rebuild`, `GET /index/jobs/{job_id}` | CONTRACT §6 |

**ไม่ทำในรอบนี้**: แปลคำถามไทย → อังกฤษ (03 ทำ) · multi_query (ดูหัวข้อ 9) · เรียก LLM ใด ๆ (§8 จำกัดไว้ที่ 03, 04, 06) · Postgres / pgvector

### การตัดสินใจที่ล็อกแล้ว

| เรื่อง | เลือก | เหตุผล |
|---|---|---|
| ที่เก็บ index | SQLite เป็นแหล่งจริง + snapshot (FAISS + BM25) ในหน่วยความจำ สลับทีเดียว | BM25 กับ FAISS สร้างจากชุด chunk เดียวกันเสมอ จึงตรงกันโดยโครงสร้าง (§6) · ล่มกลางทางไม่เหลือไฟล์ครึ่ง ๆ · restart ไม่ต้อง embed ใหม่ |
| ชื่อเล่นทีม | ดึง `GET /football/teams` ของ 07 + cache 1 ชม. + ไฟล์สำรองใน 05 | แหล่งเดียวกับ router · ต้องแก้ CONTRACT §7 เพิ่ม retrieval เป็นผู้เรียก |
| reranker | **ปิดเป็นค่าเริ่มต้น** (`RERANK_MODEL` ว่าง) · แนะนำ `cross-encoder/ms-marco-MiniLM-L-6-v2` | eval PR ③: ms-marco hit@1 ต่ำสุด 0.939 ที่ p95 สูงสุด 613.7 ms ใน process บนโน้ตบุ๊ก · รีวิว #10: ตัวเลขมาจากเอกสารจำลองและเครื่องที่ไม่ใช่เครื่อง deploy จึงเปิดผ่าน env หลังวัดซ้ำ · bge-reranker-v2-m3 p95 ~14 s เกิน timeout 10 s |
| multi_query | ไม่ทำ | router เขียนคำถามใหม่ 1 แบบอยู่แล้ว + 05 ค้นสองภาษา + ขยายชื่อเล่น · ไม่เพิ่มฟิลด์ใน §4 |

---

## 2. โครงสร้าง service

```
services/05_retrieval_knowledge/
  app/
    main.py            create_app() + lifespan: เปิด SQLite → โหลดโมเดล → สร้าง snapshot แรก
    core/              config, errors + Problem-JSON, request id, logging (JSON)
    api/               middleware (X-Request-ID, body guard) · routes: health, search, index
    kb/
      store.py         SQLite: documents, chunks, meta
      chunking.py      trivia = 1 QA / chunk · เอกสารอื่นตัดที่ "## "
      trivia.py        parse football_trivia_qa.txt + ตัดข้อซ้ำ + ตัดข้อขัดแย้ง
      doc_ids.py       ตรวจรูปแบบ doc_id ตาม category (§6)
    search/
      tokenize.py      จาก week4 (อังกฤษ + ไทยด้วย pythainlp)
      embedder.py      หุ้ม sentence-transformers (เทสใช้ FakeEmbedder)
      reranker.py      หุ้ม CrossEncoder · ปิดได้
      snapshot.py      FAISS + BM25 + metadata ของ chunk · ค้นแบบมี filter
      hybrid.py        โหมด bm25 / vector / hybrid + RRF
      aliases.py       ชื่อเล่นทีม: 07 → cache → ไฟล์สำรอง
    index/service.py   upsert / delete / rebuild · lock · สลับ snapshot · jobs
  scripts/             entrypoint.sh · ingest_trivia.py · eval_retrieval.py · smoke.py
  data/                football_trivia_qa.txt · team_aliases.json (สำรอง)
  tests/
```

**ข้อบังคับ**
- **uvicorn worker เดียวเท่านั้น** — index อยู่ในหน่วยความจำของ process ถ้าหลาย worker แต่ละตัวจะถือ index คนละชุดหลัง upsert
- งานกิน CPU (embed, FAISS, สร้าง BM25, rerank) รันใน threadpool ไม่บล็อก event loop
- error / request id / logging ใช้แบบเดียวกับ 02 (Problem-JSON ตาม §0, `service: "retrieval"`) — โค้ดซ้ำกันได้เพราะแยก container
- embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (week4) อ่านจาก env · cache โมเดลใน volume `HF_HOME`
- ไฟล์ golden อยู่ที่ `eval/` ของ root ตามแผนหัวข้อ 8 · สคริปต์วัดผลอยู่ใน 05

---

## 3. ข้อมูลและการ ingest

### 3.1 SQLite (`KB_DB_PATH`, WAL mode)

| ตาราง | ฟิลด์ | หมายเหตุ |
|---|---|---|
| `documents` | `doc_id` PK · `title` · `category` · `origin` · `season` · `matchweek` · `team_ids` (JSON) · `date` · `fetched_at` · `url` · `topic` · `text` · `content_hash` · `updated_at` | 1 แถวต่อ doc_id |
| `chunks` | `chunk_id` PK (`<doc_id>#c<N>`) · `doc_id` FK ลบตามกัน · `ord` · `text` · `bm25_text` · `embedding` (float32 blob) | |
| `meta` | `index_version` · `embedding_model` | ชื่อโมเดลใน env ไม่ตรงกับที่บันทึก → embed ใหม่ทั้งหมดตอนเริ่ม |

### 3.2 การตัด chunk (week5 #3 — ไม่ตัดตามจำนวนตัวอักษร)

- `trivia`: 1 chunk = `Q: …\nA: …` · `bm25_text` = คำถาม 2 ครั้ง + คำตอบ (แบบ week4)
- อื่น ๆ: ตัดที่บรรทัดขึ้นต้น `## ` · ข้อความก่อนหัวข้อแรก = `c0` · ทุก chunk ขึ้นต้นด้วย `title` ของเอกสาร
- ข้อจำกัด: MiniLM อ่านได้ราว 128 token — chunk ยาวถูกตัดท้ายฝั่ง vector (BM25 ยังเห็นครบ) 07 จึงควรแบ่งหัวข้อด้วย `## `

### 3.3 คลัง trivia (week5 #2)

- `doc_id` = `trivia-NNNN` จากลำดับข้อในไฟล์ต้นฉบับ (0001–1996) · ไม่เปลี่ยนแม้ตัดข้อซ้ำ
- ทำความสะอาด: ตัดช่องว่างหัวท้าย · ยุบช่องว่างซ้ำ
- เทียบคำถามด้วยข้อความที่ normalize แล้ว (ตัวพิมพ์เล็ก · ไม่มีเครื่องหมายวรรคตอน · ไม่มีเครื่องหมายเหนืออักษร) · เทียบคำตอบแบบเดียวกันและไม่สนลำดับคำ ("Petr Cech" = "Petr Čech") · คลังจริง: 1,996 ข้อ → ข้อซ้ำ 39 · ข้อขัดแย้ง 2 กลุ่ม (523/1839, 1804/1838) → 1,953 เอกสาร
  - คำถามซ้ำ + คำตอบเดียวกัน → เก็บข้อแรก
  - คำถามซ้ำ + คำตอบต่างกัน (ขัดแย้ง) → **ตัดทั้งกลุ่ม** · log รายงานจำนวนและ id ที่ตัด
- metadata: `category: "trivia"` · `origin: "kb"` · `season` / `matchweek` / `fetched_at` = null · `team_ids: []` · `title` = คำถาม (≤ 120 ตัวอักษร) · `topic` = หมวดเดิม (World Cup, Ballon d'Or, …) เป็นฟิลด์เสริมแบบ optional ตาม §0
- `entrypoint.sh` รัน ingest ทุกครั้งที่เริ่ม · เอกสารที่ `content_hash` ไม่เปลี่ยนถูกข้าม จึงรันซ้ำได้

---

## 4. การค้นหา — `POST /search` (§4)

**รับ**: `query` (ไม่ว่าง ≤ 1000 ตัวอักษร) · `query_original` (ไม่ส่ง = ใช้ `query`) · `top_k` 1–20 (ค่าเริ่มต้น 5) · `filters` · `mode` (`hybrid` ค่าเริ่มต้น | `bm25` | `vector`) · snapshot ยังไม่พร้อม → 503 `INDEX_NOT_READY`

1. **ขยายคำค้นด้วยชื่อเล่น (week5 #1)** — หาชื่อเล่นใน `query` และ `query_original` แล้วต่อชื่อทางการท้ายคำค้นฝั่ง BM25 · จับชื่อยาวสุดก่อน · ชื่ออังกฤษต้องตรงทั้งคำ · ชื่อไทยต้องตรงกับลำดับคำที่ตัดด้วย pythainlp ทั้งคำ ("ผี" ต้องไม่จับ "ผีเสื้อ" · "แมนยู" ถูกตัดเป็น แมน|ยู ทั้งใน alias และในประโยค จึงยังจับได้) · ไม่เพิ่ม `team_ids` ใน filter เอง
2. **กรอง metadata ก่อนค้น** — `category` อยู่ในรายการ · `season` / `matchweek` ตรง · `team_ids` มีตัวใดตัวหนึ่งตรง · `date_from` / `date_to` เทียบกับ `date` (เอกสารไม่มีวันที่ถูกตัดเมื่อมี filter วันที่) · ไม่เหลือ chunk → `200` + `chunks: []` · **05 ไม่ผ่อน filter เอง** (ลำดับถอยเป็นของ router §3)
3. **BM25** (hybrid, bm25) — คำค้นที่ขยายแล้ว · คะแนนเฉพาะ chunk ที่ผ่าน filter · เก็บ `CANDIDATE_K` อันดับที่คะแนน > 0
4. **vector** (hybrid, vector) — embed `query` (คำถามที่ router เขียนใหม่เป็นอังกฤษ) — เดิม embed `query_original` แต่ eval PR ③ พบว่าภาษาไทยทำชุด match hit@1 ตก (hybrid 0.70 → 0.90 เมื่อใช้ `query` · trivia เท่าเดิม) · FAISS ผ่าน `IDSelectorBatch` เฉพาะ chunk ที่ผ่าน filter · เก็บ `CANDIDATE_K` อันดับ (ตัดที่ `vector_score < MIN_VECTOR_SCORE` เมื่อค่ามากกว่า 0)
5. **รวม** — hybrid: `score` = RRF (`RRF_K` = 60) · โหมดเดี่ยว: `score` = คะแนนดิบของวิธีนั้น · เรียงมาก → น้อย
6. **rerank** (เมื่อตั้ง `RERANK_MODEL`) — ให้คะแนนผู้เข้ารอบ `CANDIDATE_K` อันดับด้วย `query` · ใส่ `rerank_score` แล้วเรียงตามนั้น · โหลดไม่ได้หรือล้ม → ใช้ผลข้อ 5 ต่อและเขียน log
7. **ตอบ** — ตัดเหลือ `top_k` · แต่ละ chunk: `chunk_id`, `text`, `score`, `bm25_score`, `vector_score` (null ถ้าวิธีนั้นไม่เจอ), `rerank_score`, `source` (Source ตาม §0 · `ref` = ลำดับ 1..n) · พร้อม `request_id`, `latency_ms`, `index_version`

**เป้าความเร็ว**: p95 ≤ 300 ms ที่ราว 5,000 chunk บน CPU เมื่อปิด rerank (งบ router → retrieval คือ 10 วินาที)

---

## 5. การจัดการ index (§6)

### `POST /index/upsert`
- ตรวจ: `category` / `origin` อยู่ใน enum · `doc_id` ตรงรูปแบบของ category ตามตาราง §6 · `text` ไม่ว่าง · ≤ 100 เอกสารต่อคำขอ · ผิด → 422 ทั้งคำขอ
- ทำทั้งคำขอเป็นก้อนเดียวใต้ lock: `content_hash` ไม่เปลี่ยน → ข้าม · ตัด chunk + embed เอกสารที่เปลี่ยน และสร้าง snapshot ใหม่ **ก่อนเขียน** → SQLite transaction เดียว (แทน chunk เดิมของ doc_id นั้นทั้งหมด) → สลับ snapshot → `index_version` = เวลาปัจจุบัน (+07:00)
- ขั้นไหนล้ม → 500 และไม่มีอะไรเปลี่ยน ทั้ง SQLite และ snapshot ที่ใช้ค้นอยู่
- index ยังโหลดไม่เสร็จ → 503 `INDEX_NOT_READY` (ใช้กับ DELETE ด้วย) · ไม่รอ lock ของการโหลด เพราะโหลดอาจนานกว่า timeout 30 s ของ 07 · 07 ถือเป็น job ล้มแล้ว retry
- เริ่มเขียนแล้วทำจนจบแม้ผู้เรียกถูกยกเลิก: thread ที่เขียน SQLite หยุดกลางทางไม่ได้ ถ้าหยุดแค่ coroutine SQLite จะถูกเขียนแต่ snapshot ไม่ถูกสลับ · ตอนปิด service `drain()` รองานเหล่านี้ก่อนปิด SQLite
- ตอบ `{request_id, upserted, chunks, index_version}` · `upserted` = จำนวนเอกสารที่รับ (รวมที่ไม่เปลี่ยน) · ไม่มีอะไรเปลี่ยน → `index_version` เดิม

### `DELETE /index/{doc_id}` → `{deleted: true | false}` (200) · ใช้ lock เดียวกัน
- ลำดับเดียวกับ upsert: สร้าง snapshot ที่ไม่มีเอกสารนั้นก่อน → ลบใน SQLite transaction เดียว → สลับ · ไม่มีเอกสาร → `false` และ `index_version` เดิม

### `GET /index/stats` → `{documents, chunks, by_category, index_version}`
- นับจาก snapshot (ตรงกับ SQLite โดยโครงสร้าง) · `by_category` = จำนวน**เอกสาร**ต่อ category · index ยังไม่พร้อม → 503 `INDEX_NOT_READY`

### `POST /index/rebuild` + `GET /index/jobs/{job_id}`
- รับ `{request_id, category?}` → `202 {job_id}` · ทำใน background: ตัด chunk + embed ใหม่จากข้อความใน SQLite แล้วสลับทีเดียว · ระหว่างนั้น `/search` ใช้ index เดิม
- สองขั้นเพื่อไม่ให้ upsert / delete ของ 07 ต้องรอ: **ขั้น 1 ไม่ถือ lock** อ่านเอกสาร ตัด chunk และ embed ทั้งชุด (ส่วนที่ช้า) · **ขั้น 2 ถือ lock** อ่าน SQLite อีกรอบ embed เฉพาะข้อความที่เปลี่ยนระหว่างขั้น 1 → สร้าง snapshot → เขียน SQLite transaction เดียว → สลับ · เอกสารที่ถูก upsert / ลบระหว่างขั้น 1 จึงไม่หายและไม่กลับมา · คลังจริงใช้ราว 24 วินาที
- `status`: `queued | running | done | failed` ตาม `Job` ใน CONTRACT §1.1 · `detail` = สรุปจำนวนเมื่อสำเร็จ หรือชนิดของ error เมื่อล้ม (ไม่เปิดเผยรายละเอียดภายใน) · shutdown ระหว่างขั้น 1 (embed) → `failed` / `cancelled` และ index ไม่เปลี่ยน · ถ้าถึงขั้น 2 (ถือ lock เขียน SQLite) แล้ว ขั้นนี้ทำจนจบและสลับ snapshot ก่อนปิด SQLite (รีวิว #9: thread หยุดกลางทางไม่ได้)
- สั่งซ้ำขณะรันอยู่ → 409 `JOB_ALREADY_RUNNING`
- job อยู่ในหน่วยความจำ 50 รายการล่าสุด: `{job_id, status, started_at, finished_at, detail}` · **restart แล้วหาย → `GET /index/jobs/{job_id}` ได้ 404** หน้า admin ให้ถือว่างานนั้นจบไม่แน่ชัด แล้วสั่ง rebuild ใหม่ได้ ไม่มีอะไรเสียหาย เพราะ rebuild ที่ไม่จบไม่เปลี่ยน index · เลือกไม่เก็บลง SQLite เพราะ rebuild เป็นระดับ Could (ตัดสินหลังรีวิว #9)

### snapshot
- ก้อนที่ไม่ถูกแก้หลังสร้าง: FAISS (`IndexIDMap2` + `IndexFlatIP`) · BM25 · metadata ของ chunk · `index_version`
- `/search` อ่าน snapshot ปัจจุบันโดยไม่รอ lock
- snapshot ใหม่สร้างจาก embedding และ token ที่มีในหน่วยความจำอยู่แล้ว ไม่ embed ซ้ำ
- ไม่เขียน snapshot ลงดิสก์ — ตอนเริ่มระบบสร้างจาก SQLite (embedding ที่เก็บไว้)

### ชื่อเล่นทีม
- task เบื้องหลังใน lifespan ดึง `GET /football/teams` ของ 07 ทุก `ALIASES_CACHE_SECONDS` (3600) · timeout 3 วินาที · ดึงไม่ได้ลองใหม่ใน `ALIASES_RETRY_SECONDS` (60)
- `/search` อ่านชุดชื่อเล่นปัจจุบันเสมอ **ไม่เคยรอ 07** แม้ตอน cache หมดอายุ (เดิมออกแบบให้ `/search` เรียก 07 เองแล้วพัก 60 วินาทีเมื่อล้ม — เปลี่ยนเพราะแบบนี้ไม่มีคำขอไหนช้าเพราะ 07 และไม่ต้องมี circuit breaker)
- ก่อน 07 ตอบ ใช้ `data/team_aliases.json` · 07 ล่ม / ตอบรูปแบบผิด / ไม่มี alias เลย → ใช้ชุดเดิมต่อ ไม่ทับด้วยชุดว่าง
- ชุดของ 07 **รวม** กับไฟล์สำรองตาม `team_id` ไม่ใช่แทนทั้งชุด: ชื่อทางการใช้ของ 07 · ชื่อเล่นเก็บทั้งสองแหล่ง · ทีมที่มีแค่ในไฟล์สำรองยังอยู่ (รีวิว #8: 07 มีชื่อเล่นไทยแค่ 8 ทีม)
- `FOOTBALL_DATA_URL` ว่าง = ไม่ดึง ใช้ไฟล์สำรองอย่างเดียว (เทสและ CI)

### health
- `GET /health` → 200 ตาม §0 เสมอ
- `GET /ready` → 200 เมื่อ snapshot พร้อม ไม่งั้น 503 · ใช้เป็น healthcheck ของ compose

---

## 6. Error และ config

| code | status | เมื่อไร |
|---|---|---|
| `VALIDATION_ERROR` | 422 | ฟิลด์ผิด · doc_id ไม่ตรงรูปแบบ · ข้อความมีอักขระ NUL |
| `PAYLOAD_TOO_LARGE` | 413 | `/search` > 64 KB · `/index/upsert` > 5 MB |
| `NOT_FOUND` | 404 | ไม่มี job id |
| `JOB_ALREADY_RUNNING` | 409 | rebuild ซ้ำขณะรันอยู่ |
| `INDEX_NOT_READY` | 503 | index ยังไม่พร้อมตอนเริ่มระบบ (**code ใหม่ — เพิ่มใน CONTRACT**) |
| `INTERNAL_ERROR` | 500 | อื่น ๆ · ไม่เปิดเผยรายละเอียดภายใน |

| env | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `KB_DB_PATH` | `/data/kb.sqlite` | อยู่ใน volume |
| `TRIVIA_FILE` | `data/football_trivia_qa.txt` | |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | เปลี่ยน = embed ใหม่ทั้งหมดตอนเริ่ม |
| `HF_HOME` | `/models` | cache โมเดล อยู่ใน volume |
| `RERANK_MODEL` | ว่าง | ว่าง = ปิด · แนะนำ `cross-encoder/ms-marco-MiniLM-L-6-v2` (อังกฤษ ให้คะแนนด้วย `query` · ~90 MB cache ใน `HF_HOME`) |
| `MIN_VECTOR_SCORE` | `0.0` | 0 = ปิด · MiniLM ให้ cosine ไทย-อังกฤษต่ำ (ราว 0.26) ค่าจริงมาจาก eval |
| `CANDIDATE_K` / `RRF_K` | `20` / `60` | |
| `FOOTBALL_DATA_URL` | `http://football-data:8000` | ใช้ดึงชื่อเล่นทีม |
| `ALIASES_CACHE_SECONDS` · `ALIASES_RETRY_SECONDS` · `ALIASES_TIMEOUT_SECONDS` | `3600` · `60` · `3` | ว่าง `FOOTBALL_DATA_URL` = ไม่ดึงจาก 07 |
| `GIT_SHA` / `LOG_LEVEL` | `0.1.0` / `INFO` | |

---

## 7. การทดสอบ

- **unit**: parse trivia · ตัดข้อซ้ำ · ตัดข้อขัดแย้ง · ตัด chunk ที่ `## ` · รูปแบบ doc_id ทุก category · จับชื่อเล่น (ต้องไม่จับ "ผีเสื้อ") · filter ทุกแบบ · RRF · snapshot มีจำนวนใน FAISS = BM25 = chunk เสมอ
- **index**: embed ล้มกลางทาง → ไม่มีอะไรเปลี่ยน · hash เดิมไม่ embed ซ้ำ · delete แล้วค้นไม่เจอ · ค้นระหว่าง upsert ได้ผลจาก snapshot เดิมหรือใหม่อย่างใดอย่างหนึ่งครบทั้งชุด · rebuild + สถานะ job + 409
- **API**: รูปร่าง response ตาม §4 / §6 ทุก endpoint · error code ทุกตัว · Problem-JSON
- เทสส่วนใหญ่ใช้ **FakeEmbedder** (deterministic ไม่โหลด torch) · เทสกับโมเดลจริง mark แยก
- **CI** `.github/workflows/retrieval-05.yml`: job 1 ruff + pytest · job 2 ingest คลังจริงด้วยโมเดลจริง (cache `HF_HOME`) แล้วรัน `scripts/smoke.py` กับ `/search` และ `/index/*`

---

## 8. Eval (week5 #5) — `scripts/eval_retrieval.py`

- `eval/golden_trivia.jsonl` สร้างใหม่แก้ข้อบกพร่องที่ week5 พบ: 60 ข้อจริง · สัดส่วนหมวดตามคลัง · ครบ 4 แบบคำถาม (verbatim / slang / partial / natural) · แก้ตัวสร้างแบบ partial · map คำตอบเป็น `trivia-NNNN` ด้วยข้อความคำถาม (เลข chunk ของ week4 ไม่ตรงกับเลขข้อ)
- `eval/golden_match.jsonl` 20 ข้อ: ผลแข่ง · ตารางคะแนน · โปรแกรม · รายงานประจำสัปดาห์ พร้อม filter และ doc_id ที่ควรเจอ · ใช้ชุดเอกสารแช่แข็ง `eval/fixtures/live_docs.json` ให้ตัวเลขรันซ้ำได้
- คำถามนอกคลัง 10 ข้อ สำหรับปรับ `MIN_VECTOR_SCORE` ให้ได้ `chunks: []` เมื่อควร
- ตัวชี้วัด: hit@1 · hit@5 · MRR · latency p50 / p95 · เทียบ bm25 / vector / hybrid / hybrid+rerank (bge-reranker-v2-m3 และ ms-marco-MiniLM-L-6-v2)
- ผลออกเป็น JSON (member6 ใช้ทำ `eval/report.html`) + ตารางใน README
- **ผล (PR ③)** อยู่ใน README ของ 05 · สรุปการตัดสินใจจากตัวเลข:
  - `MIN_VECTOR_SCORE` = **0.0** ต่อไป: hybrid ไม่ได้ `chunks: []` กับคำถามนอกคลังที่ทุกค่า (BM25 เจอคำร่วมเสมอ) ค่าที่สูงขึ้นจึงไม่เปลี่ยนสิ่งที่ router ได้รับ → คำถามนอกคลังเป็นหน้าที่ของ router / generation
  - reranker: ms-marco-MiniLM-L-6-v2 ได้ hit@1 ต่ำสุด 0.939 ที่ p95 สูงสุด 613.7 ms (ใน process โมเดลอุ่นแล้ว ไม่รวม HTTP) · bge-reranker-v2-m3 p95 ~14 s เกิน timeout 10 s ใช้บน CPU ไม่ได้ · **ปิดเป็นค่าเริ่มต้น** (รีวิว #10) เปิดผ่าน `RERANK_MODEL` หลังวัดกับเอกสาร 07 จริง คำ rewrite ของ router จริง และเครื่อง deploy
  - คำถามที่ตอบไม่ได้: retrieval ไม่ว่างเองถ้า filter ยังเหลือเอกสาร · top `rerank_score` ของ ms-marco ≥ 4 แยกได้ (ปฏิเสธคำถามที่ตอบได้ 0.4% · ปล่อยคำถามที่ตอบไม่ได้ 0%) เสนอเป็นจุดตั้งต้นให้ router / generation — ชุดที่ตอบไม่ได้มีแค่ 20 ข้อ
  - ฝั่ง vector เปลี่ยนไป embed `query` แทน `query_original`: ชุด match hybrid hit@1 0.70 → 0.90 · MRR 0.82 → 0.95 · trivia เท่าเดิม · embed ทั้งสองแล้วรวม RRF ทำ trivia ตกเล็กน้อย จึงไม่ใช้ · ข้อควรรู้: คำอังกฤษใน golden เขียนมาดี ถ้า router แปลแย่ ผลจริงจะต่ำกว่านี้
  - `live_docs.json` เป็นข้อมูล**จำลอง** แทนด้วยเอกสารจริงจาก 07 เมื่อมี แล้วรันใหม่

---

## 9. การแบ่ง PR และงานที่พึ่งคนอื่น

| PR | เนื้อหา | ปลดล็อก | วัน |
|---|---|---|---|
| ① | โครง service · SQLite · ingest trivia · snapshot · `/search` ครบทุกโหมด + filter + ชื่อเล่นจากไฟล์ + rerank flag · `/health` · `/ready` · เทส · CI | 03, 06 | D3 |
| ②a | `/index/upsert` · `DELETE /index/{doc_id}` · `/index/stats` · ดึงชื่อเล่นจาก 07 | 07 | D4 |
| ②b | `/index/rebuild` · `/index/jobs/{job_id}` (Could) | 02 หน้า admin | D4 |
| ③ | golden sets · eval script · ตัวเลขใน README | – | D5 |
| CONTRACT (แยก) | §7 เพิ่ม retrieval เป็นผู้เรียก `GET /football/teams` · §4 / §6 เพิ่ม `INDEX_NOT_READY` (503) | – | คู่กับ PR ②a |

ทุก PR เข้า `develop` ให้ member6 รีวิว (GIT_FLOW §2)

**ส่งต่อ member6** (เจ้าของ Dockerfile / compose): worker เดียว · volume `/data` และ `HF_HOME` · healthcheck `GET /ready` พร้อม `start_period` พอสำหรับโหลดโมเดล · ดาวน์โหลดโมเดลตอน build image ได้ถ้าต้องการให้เริ่มเร็ว · มีสองโมเดล: embedding (`EMBEDDING_MODEL`) และ reranker (`RERANK_MODEL`, ms-marco ~90 MB)

**ความเสี่ยง**
- image ใหญ่ (torch CPU + โมเดล) → ใช้ torch แบบ CPU-only และ cache โมเดลใน volume
- `MIN_VECTOR_SCORE` ผิดค่า → ตัดผลที่ควรเจอ หรือไม่เคยว่างเลย · ปรับจาก eval ใน D5 ก่อนเดโม
- 07 ส่งเอกสารไม่มี `## ` → chunk เดียวยาว ฝั่ง vector อ่านไม่ครบ · แจ้ง member5 ตั้งแต่ D4

---

## 10. ข้อเสนอ: ข้อมูลย้อนหลังจาก openfootball + Fjelstul (รอทีมตกลง · ยังไม่ล็อก)

> สถานะ: **ข้อเสนอเพื่อคุยกับทีม** · สัญญาอนุญาตของทั้งสองแหล่งอนุญาตให้ใช้แล้ว ไม่ต้องขอสิทธิ์เพิ่ม (§10.0) · ต้องแก้ CONTRACT (§10.7) ก่อนเริ่มทำ · เสนอเป็นระดับ **Could** ไม่กระทบ Must
> ตัวเลขทุกตัวในหัวข้อนี้วัดจากไฟล์จริงเมื่อ 26 ก.ย. 2026 (openfootball commit `b17e8f0` · Fjelstul commit `ff3c376`)

### 10.0 สิทธิ์การใช้ข้อมูล

| แหล่ง | สัญญาอนุญาต | ข้อผูกพัน |
|---|---|---|
| [openfootball/england](https://github.com/openfootball/england) | **CC0 1.0** — *"dedicated to the public domain. Use as you please with no restrictions whatsoever."* | ไม่มี (ให้เครดิตเป็นมารยาท) |
| [Fjelstul English Football Database](https://github.com/jfjelstul/englishfootball) | **CC-BY-SA 4.0** — ใช้ได้ทั้งเชิงพาณิชย์และไม่ใช่ | ① ให้เครดิต: ชื่อผู้สร้าง (Joshua C. Fjelstul, Ph.D.), ประกาศลิขสิทธิ์, ลิงก์สัญญาอนุญาต, ลิงก์ repo และบอกว่าดัดแปลงอะไร ② งานที่สร้างจากข้อมูลนี้ (เอกสาร historical) ต้องใช้ CC-BY-SA 4.0 ด้วย |

**ไม่ใช้ football-data.co.uk** — หน้า [data.php](https://www.football-data.co.uk/data.php) (ตรวจเมื่อ 26 ก.ย. 2026) เขียนว่า *"its use is intended for private individuals only, NOT commerical or data training products using automated bots/scrapers/AI"* และ *"made available for the purposes of league match prediction only"* ระบบของเราเข้าข่ายที่ห้าม · ไฟล์ที่เคยดาวน์โหลดไว้เพื่อประเมินขนาดข้อมูลต้องไม่ถูกใช้ในระบบหรือใส่ใน repo · ถ้าได้อนุญาตจากเจ้าของภายหลัง ค่อยพิจารณาเพิ่มสถิตินัด (ยิง เตะมุม ใบเหลือง/แดง ผู้ตัดสิน) เป็นงานแยก

### 10.1 ปัญหาที่แก้

KB ตอนนี้มี ① trivia (ความรู้ทั่วไป) ② ข้อมูลสดฤดูกาลปัจจุบันจาก 07 · **ไม่มีผลแข่งย้อนหลังแบบมีโครงสร้าง** คำถามแบบนี้จึงตอบจากคลังไม่ได้และถูกส่งไป `general_ai` ที่เดาได้
- สถิติเจอกัน: "ปืนใหญ่เจอไก่ในลีกมากี่นัด ใครชนะมากกว่า"
- ตารางจบฤดูกาล: "ฤดูกาล 2003/04 อาร์เซนอลได้กี่แต้ม" · "ปี 2016 ใครตกชั้น"
- ผลงานทีมรายฤดูกาล: "ลิเวอร์พูลฤดูกาล 2019/20 แพ้กี่นัด"

### 10.2 แหล่งข้อมูล

| เรื่อง | openfootball (หลัก — ผลแข่งรายนัด) | Fjelstul (เสริม — ตารางจบฤดูกาลทางการ) |
|---|---|---|
| ไฟล์ | `archive/1990s/<yyyy-yy>/1-premierleague.txt` (1992/93–1999/00) · `<yyyy-yy>/1-premierleague.txt` (2000/01 เป็นต้นไป) · ข้อความรูปแบบ Football.TXT | `data-csv/standings.csv` (กรอง `tier == 1`) · `data-csv/teams.csv` |
| ช่วงที่ใช้ | **1992/93 – 2025/26 = 34 ฤดูกาล · 13,166 นัด · 51 สโมสร · 686 ทีม-ฤดูกาล · 941 คู่ที่เคยเจอกัน** · 1992/93–1994/95 มี 22 ทีม (462 นัด) | 1992/93 – 2023/24 (32 ฤดูกาล) · repo อัปเดตล่าสุด 26 พ.ค. 2024 |
| field ที่ใช้ | วันที่ · เวลา (บางนัด) · เจ้าบ้าน · ทีมเยือน · สกอร์ · เลข matchweek (หัว `▪ Matchday N` / `▪ Regular Season - N`) | `position` `team_name` `played` `wins` `draws` `losses` `goals_for` `goals_against` `goal_difference` `points` `point_adjustment` |
| field ที่ไม่ใช้ | สกอร์ครึ่งแรก — ขาดทั้งฤดูกาลใน 1992/93–1997/98 และ 1999/00 และขาดราว 10–50 นัดต่อฤดูกาลในช่วงที่เหลือ · ชื่อคนยิงประตู — มีเฉพาะบางฤดูกาล | `appearances.csv` (ข้อมูลเดียวกับผลแข่ง) |
| ไม่มีทั้งสองแหล่ง | สถิตินัด (ยิง ยิงตรงกรอบ เตะมุม ฟาวล์ ใบเหลือง/แดง) · ผู้ตัดสิน · ราคาต่อรอง | |

**ตรวจความถูกต้องข้ามแหล่งแล้ว**: คำนวณตารางจากผลแข่งของ openfootball แล้วหักแต้มตาม `point_adjustment` ของ Fjelstul → แต้มของทุกทีมตรงกับ Fjelstul **ครบทั้ง 32 ฤดูกาลที่ทับกัน** (1992/93–2023/24)

**ข้อระวังในไฟล์ openfootball**
- มี 3 รูปแบบ: `Home  2-1 (1-0)  Away` (ถึง 2023/24) · `Home v Away  2-1 (1-0)` (2024/25) · หัวรอบ `▪ Regular Season - N` และมีบรรทัดชื่อคนยิงในวงเล็บต่อท้ายนัด (2025/26) → parser ต้องรองรับทั้ง 3 แบบ และมีเทสต่อแบบ
- บรรทัดวันที่ส่วนใหญ่ไม่มีปี (`Sat Aug 16`) ต้องหาปีจากช่วงฤดูกาล (ส.ค.–ธ.ค. = ปีแรก · ม.ค.–พ.ค. = ปีที่สอง) · บรรทัดที่ไม่มีเวลาใช้เวลาของบรรทัดก่อนหน้า
- ชื่อทีมไม่คงที่ข้ามฤดูกาล (95 แบบ สำหรับ 51 สโมสร) เช่น `Arsenal` / `Arsenal FC` · `Newcastle Utd` / `Newcastle United FC` · `Sheffield Wed` · `AFC Bournemouth` / `Bournemouth` → map ทุกแบบไปที่ `club_slug` · ชื่อทีมใน Fjelstul ก็ต่างออกไปอีก (id รูปแบบ `T-002`)

**Fjelstul ไม่มีฤดูกาล 2024/25 เป็นต้นไป** → ฤดูกาลเหล่านี้ใช้ตารางที่คำนวณจาก openfootball + `point_deductions.json` ที่แก้ด้วยมือ (ต้องตรวจกับตารางทางการของพรีเมียร์ลีกทุกครั้งที่เพิ่มฤดูกาล)

**ขอบเขตเวลา**: เอกสาร historical มีเฉพาะฤดูกาล **ก่อน** `current_season` เท่านั้น ฤดูกาลปัจจุบันเป็นของ football-data.org (หลัก) อย่างเดียว ไม่มีข้อมูลสองแหล่งแข่งกันในฤดูกาลเดียว · ฤดูกาลจบเมื่อไร 07 สร้างเอกสาร historical ของฤดูกาลนั้นเพิ่ม (openfootball มีไฟล์ของฤดูกาลปัจจุบันด้วย แต่ไม่ใช้)

### 10.3 ใครทำอะไร

| service | งาน |
|---|---|
| 07 football-data (member5) | ดาวน์โหลดไฟล์จาก `raw.githubusercontent.com` **ที่ commit ซึ่ง pin ไว้** (ไม่ใช้ `master` เพื่อให้ผลเหมือนเดิมทุกครั้ง) → parse → ตาราง `football.historical_matches` และ `football.historical_standings` ใน Postgres → สร้างเอกสาร 3 ชนิด (§10.4) → `POST /index/upsert` ครั้งละ ≤ 50 เอกสาร · รันด้วยคำสั่งเดียว (เช่น `make history`) ไม่ต้องอยู่ใน beat เพราะข้อมูลไม่เปลี่ยน |
| 05 retrieval (sakda1306) | รับ `category` / `origin` ใหม่ · ตรวจรูปแบบ `doc_id` ใหม่ · ตัด chunk และ filter ใช้ของเดิมทั้งหมด (§10.5) |
| 03 router (member2) | ส่ง `category: ["historical"]` ตามกฎใน §10.6 |
| member6 | เติม golden set ย้อนหลังใน eval (§10.8) |
| web | แสดงป้ายที่มาและเครดิตตาม CC-BY-SA (§10.7) |

เลือกให้ 07 ผลิตเอกสาร ไม่ใช่ 05 อ่านไฟล์เอง: ตรงกับหลัก "ข้อมูลเดียว สองมุมมอง" ในแผนหัวข้อ 3 (Postgres ให้หน้าเว็บ + เอกสารให้ KB) และ 07 เป็นเจ้าของการ map ชื่อทีมอยู่แล้ว

### 10.4 รูปแบบเอกสาร

**ไม่ทำ 1 เอกสารต่อ 1 นัด**: 13,166 นัดจะกลายเป็น chunk มากกว่าคลัง trivia 6 เท่า และคำถามส่วนใหญ่ถามระดับฤดูกาลหรือคู่แข่ง ไม่ใช่นัดเดียว · รายละเอียดรายนัดยังอยู่ใน Postgres และอยู่ในรายการผลของเอกสารทีมรายฤดูกาล

ทุกเอกสารเป็นภาษาอังกฤษ (CONTRACT §6) · ใช้ชื่อทางการจาก 07 (เช่น `Arsenal FC`) เพื่อให้ตรงกับชื่อที่การขยายชื่อเล่นต่อท้ายคำค้น · แบ่งหัวข้อด้วย `## ` ให้แต่ละ chunk สั้นพอสำหรับ MiniLM (~128 token, §3.2)

| ชนิด (`topic`) | `doc_id` | จำนวน | chunk โดยประมาณ |
|---|---|---|---|
| ตารางจบฤดูกาล `season_table` | `hist-season-<season>` | 34 | ~6 ต่อเอกสาร → ~200 |
| ทีมรายฤดูกาล `team_season` | `hist-team-<season>-<club_slug>` | 686 | ~4 → ~2,750 |
| สถิติเจอกัน `head_to_head` | `hist-h2h-<club_slug_a>-<club_slug_b>` (เรียงตามตัวอักษร) | 941 | ≤ 3 → ≤ 2,820 |
| **รวม** | | **1,661** | **~5,770** |

`club_slug` คือ key ที่คงที่ในไฟล์ map ชื่อทีม (เช่น `arsenal`, `nottm-forest`) **ไม่ใช้ `team_id`** ใน doc_id เพราะสโมสรที่ยุบไปแล้ว (เช่น Wimbledon) อาจไม่มี id ใน football-data.org · doc_id จึงคงที่เสมอแม้บางทีมไม่มี id

**ตัวอย่าง `hist-season-2003`**
```
Premier League 2003/04 final table
Champions: Arsenal FC, 90 points, unbeaten (26 W, 12 D, 0 L). Runners-up: Chelsea FC, 79 points.
Relegated: Leicester City FC, Leeds United FC, Wolverhampton Wanderers FC.
## Table: positions 1-5
1. Arsenal FC  P38 W26 D12 L0 GF73 GA26 GD+47 Pts90
2. Chelsea FC ...
## Table: positions 6-10
...
## Season facts
Total goals ..., most goals scored: ..., fewest conceded: ..., biggest win: ...
Sources: final table from the Fjelstul English Football Database (CC-BY-SA 4.0); match results from openfootball (CC0).
```

**ตัวอย่าง `hist-h2h-arsenal-tottenham`** (ตัวเลขจริงจาก openfootball)
```
Arsenal FC vs Tottenham Hotspur FC — Premier League head-to-head, 1992/93 to 2025/26
68 meetings: Arsenal FC won 29, draws 24, Tottenham Hotspur FC won 15.
At Arsenal FC home: ... At Tottenham Hotspur FC home: ...
## Recent meetings
2025/26  22 Feb 2026  Tottenham Hotspur FC 1-4 Arsenal FC
2025/26  23 Nov 2025  Arsenal FC 4-1 Tottenham Hotspur FC
...
## Biggest wins
...
```

**ตัวอย่าง `hist-team-2003-arsenal`**: `c0` สรุป (อันดับ แต้ม W/D/L ประตูได้-เสีย) · `## Home and away` · `## Results August-December` · `## Results January-May` (รายการผลเรียงตามวันที่ พร้อมเลข matchweek) · chunk รายการผลยาวราว 200 token ฝั่ง vector อ่านไม่ครบแต่ BM25 เห็นครบ (ข้อจำกัดเดียวกับ §3.2)

**การตัดแต้ม** — ผลแข่งอย่างเดียวคำนวณตารางผิดในฤดูกาลที่มีการตัดแต้ม ตัวอย่างจริง: 1996/97 ถ้าไม่หัก 3 แต้มของ Middlesbrough ตารางจะบอกว่า Sunderland อันดับ 19 และ Middlesbrough รอด ซึ่งผิด
- 1992/93–2023/24: **ใช้ตารางของ Fjelstul เป็นตารางทางการ** (มีคอลัมน์ `point_adjustment` อยู่แล้ว: Middlesbrough 1996/97 −3 · Portsmouth 2009/10 −9 · Everton 2023/24 −8 · Nottingham Forest 2023/24 −4) และเขียนบอกในเอกสารว่าถูกหักแต้ม
- 2024/25 เป็นต้นไป: คำนวณจาก openfootball + `point_deductions.json` (§10.2)

### 10.5 metadata และตัวกรอง

| field | `season_table` | `team_season` | `head_to_head` |
|---|---|---|---|
| `category` | `historical` | `historical` | `historical` |
| `origin` | `fjelstul` (≤ 2023/24) · `openfootball` (2024/25 เป็นต้นไป) | `openfootball` | `openfootball` |
| `season` | `"2003"` | `"2003"` | `null` (ครอบคลุมหลายฤดูกาล) |
| `matchweek` | `null` | `null` | `null` |
| `team_ids` | ทุกทีมในฤดูกาลที่มี id | `[id]` หรือ `[]` ถ้าไม่มี id | ทั้งสองทีมที่มี id |
| `date` | `null` | `null` | `null` |
| `fetched_at` | `null` | `null` | `null` |
| `url` | `https://github.com/jfjelstul/englishfootball` (≤ 2023/24) · URL ไฟล์ openfootball ของฤดูกาลนั้น | URL ไฟล์ openfootball ของฤดูกาลนั้น (ที่ commit ที่ pin) | `https://github.com/openfootball/england` |
| `topic` | `season_table` | `team_season` | `head_to_head` |

- **`origin` ของ `team_season`** เป็น `openfootball` แม้สรุปอันดับ/แต้มใน `c0` มาจากตาราง Fjelstul · เครดิตทั้งสองแหล่งเขียนไว้ท้ายเอกสารเหมือนตัวอย่าง `hist-season-2003`
- **`fetched_at` = null**: เป็นข้อมูลนิ่ง ไม่ใช่ข้อมูลสด · ถ้าใส่เวลาดาวน์โหลด `data_as_of` ของคำตอบ (CONTRACT §1 `ChatResponse`) จะแสดงวันที่เก่าผิดความหมาย
- **ตัวกรองใช้ของเดิมทั้งหมด ไม่เพิ่ม field ใน §4**:
  - `category: ["historical"]` แยกออกจากข้อมูลสดได้ทันที
  - `season` → ได้ตารางจบฤดูกาล + ทีมรายฤดูกาลของปีนั้น · เอกสาร h2h (season = null) ถูกตัดออก ซึ่งถูกต้อง เพราะคำถามที่ระบุฤดูกาลหาผลคู่นั้นได้จากรายการผลของทีม
  - `team_ids` (ตรงตัวใดตัวหนึ่ง) → h2h ของคู่ที่ถามติดมาเสมอ แต่ติด h2h คู่อื่นของทีมเดียวกันมาด้วย ให้การจัดอันดับคัดออก · ถ้า eval พบว่า h2h คู่ที่ถามหลุดจาก top 5 บ่อย ค่อยเสนอ `team_ids_match: "all"` ใน §4 ภายหลัง
  - `matchweek` / `date_from` / `date_to` → เอกสาร historical ไม่มีค่าเหล่านี้ จึงถูกตัดออกเสมอ (§4 ข้อ 2) router ต้องไม่ส่งมากับคำถามย้อนหลัง
- 05 แก้โค้ดแค่: enum `category` / `origin` · รูปแบบ `doc_id` ใน `doc_ids.py` (`hist-season-\d{4}` · `hist-team-\d{4}-[a-z0-9-]+` · `hist-h2h-[a-z0-9-]+`) · `topic` เป็น field เสริมที่มีอยู่แล้ว (§3.3) ไม่ต้องแก้ SQLite

### 10.6 การเลือกเส้นทางใน router (เสนอ — ไม่เพิ่ม intent)

เพิ่ม intent ใหม่ต้องเทรน classifier ของ 04 ใหม่ จึงเสนอให้ใช้ intent เดิมแล้วปรับแค่ `filters.category`:

| intent | เงื่อนไข | `filters.category` |
|---|---|---|
| `trivia_history` | – | `["trivia", "historical"]` (เดิม `["trivia"]`) |
| `match_result` / `standings_stats` | ระบุฤดูกาลก่อน `current_season` หรือถามสถิติเจอกันระหว่างสองทีม | `["historical"]` + `season` (ถ้ามี) + `team_ids` · ไม่ส่ง `matchweek` / `date_*` |
| `match_result` / `standings_stats` | ฤดูกาลปัจจุบัน / ไม่ระบุ | เหมือนเดิม |

ลำดับถอย (CONTRACT §3) ใช้ของเดิม: คำถาม historical ที่ไม่เจอผ่าน `match_result` / `standings_stats` **ห้ามถอยไป `general_ai`** เพราะ LLM จะเดาสกอร์

### 10.7 สิ่งที่ต้องแก้ใน CONTRACT (PR แยก ถ้าทีมตกลง)

- §0 enum: `category` เพิ่ม `historical` · `origin` เพิ่ม `openfootball` และ `fjelstul` · หน้าเว็บแสดงป้าย "ข้อมูลย้อนหลัง (openfootball)" / "ข้อมูลย้อนหลัง (Fjelstul)"
- §1 `ChatResponse`: `data_as_of` ไม่นับเอกสาร `historical` (เพราะ `fetched_at` = null)
- §3: ตาราง intent → `filters.category` ตาม §10.6
- §6: ตารางรูปแบบ `doc_id` เพิ่ม 3 แถวตาม §10.4
- **เครดิตตาม CC-BY-SA** (เงื่อนไขบังคับ ไม่ใช่ทางเลือก): คำตอบที่ใช้เอกสาร `origin = fjelstul` ต้องแสดงลิงก์ `Source.url` · README และสไลด์มีข้อความเครดิตเต็ม (ชื่อผู้สร้าง, ลิงก์สัญญาอนุญาต CC-BY-SA 4.0, ลิงก์ repo, "adapted: tables converted to text summaries") และระบุว่าเอกสาร historical เผยแพร่ภายใต้ CC-BY-SA 4.0 · openfootball ให้เครดิตในที่เดียวกัน
- Changelog: v1.x · field เดิมไม่ถูกลบหรือเปลี่ยนชื่อ

### 10.8 การทดสอบและ eval

- 07 unit: parse ไฟล์ openfootball ครบ 3 รูปแบบ (§10.2) · หาปีของวันที่ถูกทั้งสองครึ่งฤดูกาล · บรรทัดชื่อคนยิงไม่ถูกนับเป็นนัด · จำนวนนัดต่อฤดูกาลตรงกับหัวไฟล์ (`# Matches`) · **ตารางที่คำนวณได้ + `point_adjustment` ต้องตรงกับตาราง Fjelstul ครบ 32 ฤดูกาล** · ทุกชื่อทีมในทั้งสองแหล่งต้องมีใน `club_slug` (ชื่อใหม่ที่ไม่รู้จัก → ล้มดัง ๆ ไม่ข้ามเงียบ)
- 05 unit: รูปแบบ `doc_id` ใหม่ · filter `season` ตัด h2h ออก · filter `date_*` ตัด historical ออกทั้งหมด
- eval: `eval/golden_history.jsonl` 20 ข้อ (ตารางจบฤดูกาล 7 · ทีมรายฤดูกาล 7 · h2h 6 · ครบ 4 แบบคำถามตาม §8) · รัน `golden_trivia` ซ้ำเพื่อยืนยันว่าการเพิ่ม `historical` ใน `trivia_history` ไม่ทำ hit@1 ของ trivia ตก

### 10.9 ขนาดและความเร็ว

- chunk ใน index จะเพิ่มจาก ~2,000 (trivia + ข้อมูลสด) เป็น **~7,800** เกินขนาดที่ตั้งเป้า p95 ≤ 300 ms ไว้ (~5,000 chunk, §4) → **ต้องวัด latency ซ้ำ** ก่อนเปิดใช้
- ถ้าช้าเกิน ตัดตามลำดับนี้: ① รวมรายการผลใน `team_season` เป็น chunk เดียว ② h2h เฉพาะคู่ที่มีอย่างน้อยหนึ่งทีมอยู่ในฤดูกาลปัจจุบัน ③ เริ่มที่ 2000/01
- ingest ครั้งแรก: embed ~5,770 chunk บน CPU (คลัง trivia 1,953 chunk ใช้ ~24 วินาทีตอน rebuild) · 07 ส่งครั้งละ ≤ 50 เอกสารให้อยู่ใน timeout 30 วินาทีของ upsert · รันซ้ำไม่ embed ใหม่เพราะ `content_hash` ไม่เปลี่ยน (§3.3)

### 10.10 คำถามที่ต้องตัดสินในที่ประชุม

1. ทำหรือไม่ และจัดเป็น Could ตามที่เสนอหรือไม่ · member5 มีเวลาทำหลัง Must ของ 07 เสร็จหรือไม่
2. รับเงื่อนไข CC-BY-SA ของ Fjelstul ได้หรือไม่ (เครดิตบนหน้าเว็บ + เอกสาร historical เป็น CC-BY-SA) — ถ้าไม่รับ ใช้ทางเลือกที่ 1 ใน §10.11
3. ใช้ intent เดิมตาม §10.6 หรือเพิ่ม intent ใหม่ (ต้องเทรน classifier ใหม่)
4. ยอมรับว่าไม่มีสถิตินัด (ยิง ใบเหลือง/แดง ผู้ตัดสิน) หรือไม่ — คำถามเช่น "ฤดูกาลไหนใบแดงเยอะสุด" จะตอบว่าไม่มีข้อมูล

### 10.11 แผนสำรอง

1. **ถ้าไม่รับ CC-BY-SA** → ใช้ openfootball (CC0) อย่างเดียว · คำนวณตารางเองทุกฤดูกาลด้วย `point_deductions.json` (4 รายการใน §10.4 + ฤดูกาลหลัง 2023/24) · ตัด `origin = fjelstul` ออก · เทสเทียบแชมป์/ทีมตกชั้นกับรายการที่เขียนด้วยมือแทน
2. **ถ้าไม่มีเวลาทำ** → ตัด §10 ออกจากขอบเขต · คำถามย้อนหลังที่ไม่มีในคลังตอบว่า "ไม่มีข้อมูล" แทนการถอยไป `general_ai` ที่เดาสกอร์ · เขียนบอกข้อจำกัดนี้ในสไลด์
