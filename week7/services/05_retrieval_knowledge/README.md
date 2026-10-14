# 05 Retrieval / Knowledge · `retrieval`

ค้นคลังความรู้ฟุตบอลแบบ hybrid (BM25 + FAISS + RRF) ให้ router ตาม [`docs/CONTRACT.md`](../../docs/CONTRACT.md) §4 และรับเอกสารจาก 07 ตาม §6 · แบบระบบอยู่ที่ [`docs/05_RETRIEVAL_DESIGN.md`](../../docs/05_RETRIEVAL_DESIGN.md)

| endpoint | ตาม | สถานะ |
|---|---|---|
| `POST /search` | §4 | ใช้ได้ |
| `GET /health` · `GET /ready` | §0 · healthcheck ของ compose | ใช้ได้ |
| `POST /index/upsert` · `DELETE /index/{doc_id}` · `GET /index/stats` | §6 | ใช้ได้ |
| `POST /index/rebuild` · `GET /index/jobs/{job_id}` | §6 | ใช้ได้ |

## ตัวแก้ปัญหาจาก week5 ที่อยู่ใน service นี้

| # | ปัญหา | อยู่ที่ |
|---|---|---|
| 1 | vocabulary mismatch | `app/search/aliases.py` — ชื่อเล่นทีมไทย/อังกฤษ → ชื่อทางการในคำค้น BM25 · ฝั่ง vector ใช้โมเดล multilingual กับ `query` ที่ router เขียนเป็นอังกฤษ (ดูผลวัด) |
| 2 | data quality | `app/kb/trivia.py` — 1,996 ข้อ → ตัดข้อซ้ำ 39 · ตัดข้อขัดแย้ง 2 กลุ่ม (523/1839, 1804/1838) → 1,953 เอกสาร · เอกสารข้อมูลสด upsert ทับด้วย doc_id |
| 2b | ฉายาไทยไม่มีในคลัง | `data/thai_nicknames_qa.txt` — ฉายาไทยของ 20 สโมสรและที่มา (ผีแดง หงส์แดง เรือใบ ฯลฯ) · doc_id `trivia-2001` ขึ้นไป · แยกไฟล์เพื่อไม่ให้ golden set ของคลัง trivia เปลี่ยน · ingest พร้อมคลัง trivia ตอนเริ่ม container |
| 3 | chunking | `app/kb/chunking.py` — trivia 1 คู่ถาม-ตอบ = 1 chunk · เอกสารอื่นตัดที่ `## ` |
| 5 | golden set เอียง | `scripts/build_golden.py` + `scripts/eval_retrieval.py` — 60 ข้อจริงตามสัดส่วนหมวดของคลัง · partial เก็บหัวข้อไม่ใช่คำขึ้นต้นประโยค · ผลอยู่ในหัวข้อ "ผลวัด" ด้านล่าง |

## ตัวแปร env

| ชื่อ | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `KB_DB_PATH` | `/data/kb.sqlite` | อยู่ใน volume |
| `TRIVIA_FILE` | `data/football_trivia_qa.txt` | |
| `NICKNAME_FILE` | `data/thai_nicknames_qa.txt` | ว่าง = ไม่โหลด |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | เปลี่ยนแล้วตอนเริ่มจะ embed ใหม่ทั้งหมดเอง |
| `HF_HOME` | ค่าของไลบรารี | ชี้ไปที่ volume เพื่อไม่ต้องดาวน์โหลดโมเดลทุกครั้ง |
| `RERANK_MODEL` | ว่าง | ว่าง = ปิด · แนะนำ `cross-encoder/ms-marco-MiniLM-L-6-v2` หลังวัดบนข้อมูลและเครื่องจริง (ดูผลวัด) · เปิดแล้ว image ควรมีโมเดลนี้ใน `HF_HOME` |
| `MIN_VECTOR_SCORE` | `0.0` | 0 = ปิด · ค่าจริงมาจาก eval (MiniLM ให้ cosine ไทย-อังกฤษต่ำ ราว 0.26) |
| `CANDIDATE_K` · `RRF_K` | `20` · `60` | |
| `FOOTBALL_DATA_URL` | `http://football-data:8000` | ดึงชื่อเล่นทีมจาก `GET /football/teams` · ว่าง = ใช้ไฟล์สำรองอย่างเดียว |
| `ALIASES_CACHE_SECONDS` · `ALIASES_RETRY_SECONDS` | `3600` · `60` | ดึงใหม่ทุกกี่วินาที · ดึงไม่ได้แล้วลองใหม่ในกี่วินาที |
| `ALIASES_TIMEOUT_SECONDS` | `3` | |
| `GIT_SHA` | `0.1.0` | ค่า `version` ใน `/health` |

## รัน

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/pip
export KB_DB_PATH=./.hf-cache/kb.sqlite HF_HOME=./.hf-cache
python -m scripts.ingest_trivia                                   # ครั้งแรกราว 1–2 นาที ครั้งต่อไปข้ามทั้งหมด
uvicorn app.main:app --port 8005 --workers 1                      # เอกสาร API: http://localhost:8005/docs
```

**ใน docker compose** (Dockerfile / compose เป็นของ member6): command `sh scripts/entrypoint.sh` · **worker เดียวเท่านั้น** (index อยู่ในหน่วยความจำของ process) · volume ที่ `/data` และ `HF_HOME` · healthcheck `GET /ready` ตั้ง `start_period` ให้พอ ingest ครั้งแรก (ราว 3 นาที) · ถ้าโมเดลอยู่ใน volume แล้ว ตั้ง `HF_HUB_OFFLINE=1` ได้ ไม่งั้นทุกครั้งที่เริ่มจะเช็ก Hugging Face ผ่านเน็ต

## เทส

```bash
pytest -q                 # ใช้ FakeEmbedder ไม่ต้องโหลดโมเดล
pytest -q -m model        # โมเดลจริงกับคลังจริง
RETRIEVAL_URL=http://localhost:8005 python scripts/smoke.py   # รวม upsert → search → rebuild → delete ด้วยเอกสารทดสอบที่ลบคืนเอง
ruff check . && ruff format --check .
```

## ผลวัด (`eval/results/retrieval.json`)

```bash
python -m scripts.build_golden                                     # สร้าง eval/golden_trivia.jsonl ใหม่ (ผลเดิมทุกครั้ง)
python -m scripts.eval_retrieval --kb ./.hf-cache/kb.sqlite \
  --rerank cross-encoder/ms-marco-MiniLM-L-6-v2 --rerank BAAI/bge-reranker-v2-m3
```

**วัดที่ไหน อย่างไร** — Windows-11-10.0.26200-SP0 · Intel64 Family 6 Model 140 Stepping 1, GenuineIntel · 8 cores · Python 3.12.10 · torch 2.14.0+cpu · sentence-transformers 6.1.0 · one process, CPU only, models loaded and warmed up before timing; latency is Searcher.search in process: no HTTP, no model loading, no other load on the machine · คลังเป็นสำเนา (SQLite backup API): trivia 1,953 + เอกสารข้อมูลสด**จำลอง** 14 ชิ้น (`eval/fixtures/live_docs.json`) = 1,967 เอกสาร 1,999 chunk · ฝั่ง vector embed `query`

ค่าในตาราง = hit@1 / MRR (hit@5 ต่ำสุด 0.900 ดูครบใน JSON)

| ชุด (n) | bm25 | vector | hybrid | hybrid + ms-marco | hybrid + bge-m3 |
|---|---|---|---|---|---|
| trivia/verbatim (60) | 1.000 / 1.000 | 0.950 / 0.972 | 0.983 / 0.992 | 1.000 / 1.000 | 1.000 / 1.000 |
| trivia/slang (33) | 0.879 / 0.929 | 0.727 / 0.849 | 0.848 / 0.919 | 0.939 / 0.970 | 0.939 / 0.970 |
| trivia/partial (60) | 0.967 / 0.978 | 0.800 / 0.854 | 0.833 / 0.909 | 0.967 / 0.983 | 0.950 / 0.975 |
| trivia/natural (60) | 0.933 / 0.967 | 0.900 / 0.936 | 0.983 / 0.992 | 1.000 / 1.000 | 0.983 / 0.992 |
| match/match (20) | 0.900 / 0.931 | 0.900 / 0.932 | 0.900 / 0.950 | 0.950 / 0.967 | 0.950 / 0.975 |

| ms ต่อคำค้น | bm25 | vector | hybrid | hybrid + ms-marco | hybrid + bge-m3 |
|---|---|---|---|---|---|
| p50 | 3.1–6.5 | 22.7–29.6 | 25.1–34.4 | 116.9–251.6 | 1,634.0–4,930.8 |
| p95 | 4.2–20.8 | 27.9–45.4 | 31.7–69.2 | 302.0–606.6 | 4,920.3–12,513.6 |

`/search` ผ่าน HTTP จริงเมื่อตั้ง `RERANK_MODEL` เป็น ms-marco (วัดแยก 25 ก.ย. บนโค้ดที่รวม #9 + #10 เครื่องเดียวกัน): ปกติ p50 200 ms / p95 471 ms · **ระหว่าง rebuild ทั้งคลัง** p50 397 ms / p95 678 ms / สูงสุด 718 ms · upsert ระหว่าง rebuild 119 ms

**คำถามที่ตอบไม่ได้** (10 ข้อฟุตบอลที่คลังไม่มี · 10 ข้อนอกฟุตบอล) — retrieval ไม่เคยว่างเองถ้า filter ยังเหลือเอกสาร ที่ว่างคือข้อที่ router ใส่ filter นัดที่ยังไม่มีข้อมูล

| คำถามที่ตอบไม่ได้ | ได้ chunk กลับมา (hybrid) |
|---|---|
| ฟุตบอลที่คลังไม่มี (10) | 70% |
| ไม่ใช่ฟุตบอล (10) | 100% |

ถ้าใช้ top `rerank_score` เป็นเกณฑ์ปฏิเสธตอบ (233 คำถามที่ตอบได้ · 20 ข้อที่ตอบไม่ได้):

| reranker | เกณฑ์ top `rerank_score` | คำถามที่ตอบได้ถูกปฏิเสธ | ตอบได้และเอกสารถูกอยู่อันดับ 1 | ฟุตบอลนอกคลังยังตอบ | นอกฟุตบอลยังตอบ |
|---|---|---|---|---|---|
| ms-marco | ≥ -8 | 0.0% | 97.9% | 70% | 40% |
| ms-marco | ≥ -6 | 0.0% | 97.9% | 70% | 40% |
| ms-marco | ≥ -4 | 0.0% | 97.9% | 60% | 40% |
| ms-marco | ≥ -2 | 0.0% | 97.9% | 50% | 40% |
| ms-marco | ≥ 0 | 0.0% | 97.9% | 20% | 30% |
| ms-marco | ≥ 2 | 0.4% | 97.4% | 20% | 10% |
| ms-marco | ≥ 4 | 0.4% | 97.4% | 0% | 0% |
| bge-m3 | ≥ 0.01 | 0.0% | 97.0% | 40% | 50% |
| bge-m3 | ≥ 0.05 | 0.0% | 97.0% | 10% | 40% |
| bge-m3 | ≥ 0.1 | 0.0% | 97.0% | 10% | 20% |
| bge-m3 | ≥ 0.25 | 0.0% | 97.0% | 10% | 10% |
| bge-m3 | ≥ 0.5 | 0.4% | 96.6% | 10% | 0% |
| bge-m3 | ≥ 0.75 | 0.9% | 96.6% | 0% | 0% |
| bge-m3 | ≥ 0.9 | 1.3% | 96.1% | 0% | 0% |

| MIN_VECTOR_SCORE | hit ที่ถูกโดนตัด | นอกคลังได้ว่าง (vector) | นอกคลังได้ว่าง (hybrid) |
|---|---|---|---|
| 0.00 | 0.0% | 15% | 15% |
| 0.30 | 0.0% | 30% | 15% |
| 0.40 | 0.0% | 40% | 15% |
| 0.50 | 0.4% | 50% | 15% |
| 0.60 | 4.7% | 75% | 15% |

**อ่านผล**
- **reranker ปิดเป็นค่าเริ่มต้น** (รีวิว #10) — ms-marco ได้ hit@1 ต่ำสุด 0.939 (trivia/slang, 31/33) และ p95 สูงสุด 613.7 ms ใน process · แนะนำเปิดด้วย `RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2` **หลัง** วัดซ้ำกับเอกสารจริงจาก 07 คำที่ router เขียนจริง และเครื่องที่ deploy · bge-m3 p95 สูงสุด 13.8 วินาที เกิน timeout router → retrieval 10 วินาที ใช้บน CPU ไม่ได้
- **`rerank_score` ใช้เป็นสัญญาณ "ไม่มีข้อมูล" ได้** — ms-marco ที่เกณฑ์ ≥ 4 ปฏิเสธคำถามที่ตอบได้ 0.4% และปล่อยคำถามที่ตอบไม่ได้ 0% (ฟุตบอล) / 0% (นอกฟุตบอล) · ชุดที่ตอบไม่ได้มีแค่ 20 ข้อ เกณฑ์นี้เป็นจุดตั้งต้นให้ router / generation ไม่ใช่ค่าที่พิสูจน์แล้ว
- **trivia ง่ายเกินจริง** คำถามทุกแบบสร้างจากข้อความในคลังเอง ใช้เทียบโหมดได้ ไม่ใช่คะแนนของผู้ใช้จริง
- **ฝั่ง vector ใช้ `query`** เดิม embed คำถามภาษาไทย ชุด match ได้ hybrid 0.700 / vector 0.600 (hit@1) · เปลี่ยนแล้ว 0.900 / 0.900 · คำอังกฤษใน golden เขียนมาดี ถ้า router แปลแย่ผลจริงจะต่ำกว่านี้
- **`MIN_VECTOR_SCORE` คงไว้ที่ 0.0** — ค่าที่สูงขึ้นไม่ทำให้ hybrid ว่างเพิ่ม เพราะ BM25 ยังเจอคำร่วมเสมอ

## จุดที่ควรรู้

- **SQLite คือแหล่งจริง** FAISS + BM25 เป็น snapshot ในหน่วยความจำที่สร้างจากชุด chunk เดียวกัน แล้วสลับทีเดียว `/search` ไม่เคยเห็น index ครึ่ง ๆ
- **05 ไม่ผ่อน filter เอง** ไม่เจอ = `200` + `chunks: []` การค้นซ้ำโดยตัด matchweek เป็นของ router (§3)
- **filter ที่ไม่รู้จัก → 422** เพื่อไม่ให้ filter ที่พิมพ์ผิดคืนผลแบบไม่กรอง
- **ชื่อเล่นทีมมาจาก 07** task เบื้องหลังดึง `GET /football/teams` ทุก `ALIASES_CACHE_SECONDS` `/search` ไม่เคยรอ 07 · ก่อน 07 ตอบ หรือ 07 ล่ม / ตอบชุดว่าง ใช้ `data/team_aliases.json` (หรือชุดล่าสุดที่ดึงได้) · ชุดของ 07 **รวม** กับไฟล์สำรองตาม `team_id` (ชื่อทางการใช้ของ 07 · ชื่อเล่นเก็บทั้งสองแหล่ง) ทีมที่ 07 ไม่มีชื่อเล่นจึงยังค้นด้วยชื่อเล่นได้
- **upsert และ delete สำเร็จหรือไม่สำเร็จทั้งก้อน** embed และสร้าง snapshot ใหม่ก่อนเขียน SQLite ขั้นไหนล้ม → 500 และทั้ง SQLite กับ `/search` ยังเป็นรุ่นเดิม · เริ่มเขียนแล้วทำจนจบแม้ผู้เรียกถูกยกเลิก (shutdown / request หลุด) และตอนปิด service รอให้จบก่อนปิด SQLite
- **index ยังโหลดไม่เสร็จ → upsert / delete ได้ 503 `INDEX_NOT_READY`** เหมือน `/search` และ `/index/stats` · 07 ถือเป็น job ล้มแล้ว retry
- **`by_category` ใน `/index/stats` นับเป็นจำนวนเอกสาร** ต่อ category ไม่ใช่จำนวน chunk
- **rebuild ไม่ขวาง upsert** embed ทั้งชุดโดยไม่ถือ lock แล้วค่อยถือ lock อ่าน SQLite ใหม่ embed เฉพาะที่เปลี่ยนระหว่างนั้นแล้วสลับ · คลังจริง 1,954 chunk ใช้ราว 24 วินาที ระหว่างนั้น upsert ตอบใน 78 ms · rebuild ได้ทีละงาน (ซ้ำ → 409) · job อยู่ในหน่วยความจำ 50 รายการล่าสุด **restart แล้วหาย `GET /index/jobs/{job_id}` ได้ 404** สั่ง rebuild ใหม่ได้ (rebuild ที่ไม่จบไม่เปลี่ยน index) · ปิด service ระหว่าง rebuild: ถ้ากำลังเขียน SQLite จะเขียนและสลับ snapshot จนจบก่อนปิด
