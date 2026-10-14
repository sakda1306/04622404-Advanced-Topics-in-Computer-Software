# 07 Football Data

FastAPI service สำหรับข้อมูลพรีเมียร์ลีกตาม `docs/CONTRACT.md` §6–7 อยู่ใน branch ของโมดูล 07 โดยเฉพาะ

## สิ่งที่มีแล้ว

- `GET /health`, `/ready`, `/football/status`, `/football/teams`, `/football/teams/{team_id}/squad`, `/football/standings`, `/football/fixtures`, `/football/matches/{match_id}`
- `POST /ingest/run` รับ `scope=fixtures|details|all`: ดึง teams, matches, standings, scorers จาก football-data.org v4 และรายละเอียดนัดที่จบแล้วจาก API-Football; `details`/`all` ต้องตั้ง `API_FOOTBALL_KEY` ไม่เช่นนั้นตอบข้อผิดพลาดก่อนสร้าง job
- เก็บ API-Football quota ในฐานข้อมูล (จำกัด 90 คำขอต่อวัน UTC รวม retry), จับคู่ fixture จากวันเวลาและทีม, และเก็บ events/lineups/statistics ใน payload ของแมตช์
- บันทึกงานส่ง index ในฐานข้อมูล มี background worker ส่งซ้ำอัตโนมัติระหว่าง process ทำงาน (เริ่มรอ 2 วินาที, backoff สูงสุด 60 วินาที) หรือสั่ง `POST /index/reconcile`; `/football/status` แสดงงานค้าง, `last_error` และ quota แยกจากข้อมูลใน DB
- Upsert แบ่ง batch 1–100 เอกสารและ body ไม่เกิน 5,000,000 UTF-8 bytes; ล้างเฉพาะงานที่ส่งสำเร็จ ส่วนเอกสารเดี่ยวที่ใหญ่เกินกำหนดคงไว้พร้อม error ให้แก้
- ingest เก็บ squad ของทุกทีมจาก response เดิมของ `competitions/PL/teams` (ตาราง `squads`, ไม่เพิ่มการเรียก API); เอกสาร `category=player` (`players-<season>-team-<team_id>`) จะเข้า index ก็ต่อเมื่อ `PLAYER_INDEX_ENABLED=true` หลัง 05 รองรับ category `player` แล้วเท่านั้น
- `/football/standings` และ status เลือก snapshot สัปดาห์ที่จบแล้วล่าสุดถ้ามี; snapshot ระหว่างสัปดาห์ติดป้าย `live` ชัดเจน ส่วนดาวซัลโวปัจจุบันอยู่ในเอกสาร `category=standings` พร้อมเวลาข้อมูล
- `GET /jobs`, `/jobs/{job_id}` สำหรับติดตาม job; ป้องกันการสั่ง job ชนิดเดียวกันซ้ำในระดับแอป
- `POST /reports/weekly/run` เรียกโมดูล 06 เพื่อสร้าง draft เมื่อแมตช์วีคจบครบ โดยสร้าง snapshot ตารางคะแนนย้อนหลังจากผลแข่งได้เมื่อ `currentMatchday` ขยับไปแล้ว; รายการ/อ่าน/แก้ไข/publish/unpublish รายงาน โดยมีงานชดเชยกรณีอัปเดต index สำเร็จแต่ DB commit ล้ม
- เก็บ Markdown ภาษาไทยไว้แสดงผล แต่ใช้ `search_text_policy=source_facts`: ข้อความค้นภาษาอังกฤษมาจากผลแข่งและตารางคะแนนใน DB การแก้ Markdown จึงไม่เปลี่ยนข้อเท็จจริงที่ค้นได้; รายงานเก่าที่ไม่มีข้อความค้นจะ backfill ก่อน publish/reconcile หรือปฏิเสธเมื่อข้อมูลต้นทางไม่ครบ ไม่สร้างข้อความทั่วไปแทน; มีชื่อเล่นไทยครบ 20 ทีมของฤดูกาล 2026/27
- `X-Request-ID` และ Problem-JSON, เวลา Asia/Bangkok, `team_id` จาก football-data.org

ฐานข้อมูลใช้ schema `football` ใน PostgreSQL และสร้างตารางเมื่อแอปเริ่ม (`create_all`) ส่วน SQLite ใช้สำหรับพัฒนาในเครื่อง ยังต้องเพิ่ม Alembic ก่อน deploy จริง

## การรันในเครื่อง

ต้องมี Python 3.12+ จากนั้นรันในโฟลเดอร์นี้:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
```

PowerShell:

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./football_data.db"
$env:FOOTBALL_DATA_API_KEY = "<key ของตัวเอง>"
$env:API_FOOTBALL_KEY = "<key ของตัวเอง>" # ต้องมีเมื่อใช้ details/all
$env:RETRIEVAL_URL = "http://localhost:8005"
$env:GENERATION_URL = "http://localhost:8006"
.venv/Scripts/uvicorn app.main:app --reload --port 8007
```

เริ่มดึงข้อมูล:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8007/ingest/run -ContentType application/json -Body '{"scope":"fixtures","triggered_by":"beat"}'
```

ดูสถานะด้วย `GET /jobs/{job_id}` และอ่าน API ที่ `/docs` ได้ เทสด้วย `pytest -q` และตรวจโค้ดด้วย `ruff check .` กับ `ruff format --check .` เทสปกติใช้บริการจำลอง ไม่เรียก API จริง

ตั้ง `RETRIEVAL_TEST_ROOT` เป็น absolute path ของ `services/05_retrieval_knowledge` เพื่อเปิดเทส HTTP ร่วมกับบริการ 05 จริง โดยต้องติดตั้ง `numpy faiss-cpu rank-bm25 pythainlp structlog` เพิ่มใน venv นี้ เทสนี้ใช้ FakeEmbedder และจำลอง API ฟุตบอล/Generation ไม่ใช่ end-to-end ของโมเดลจริง ดูหลักฐานและข้อจำกัดใน [LOCAL_REVIEW_VALIDATION.md](LOCAL_REVIEW_VALIDATION.md)

Worker จะกู้งาน publish/unpublish ที่ค้างหลัง grace period 120 วินาทีโดยยึดสถานะรายงานใน DB และยกเลิก task เมื่อ shutdown ตั้งเวลาได้ด้วย `INDEX_RETRY_SECONDS`, `INDEX_RETRY_MAX_SECONDS`, `INDEX_TRANSITION_TIMEOUT_SECONDS`

## ข้อมูลย้อนหลังและผลทดสอบ API จริง

เพิ่ม pipeline สำหรับ 34 ฤดูกาล, mapping 51 สโมสร และเอกสารย้อนหลัง 1,661 เอกสารแล้ว ดูคำสั่งใช้งาน ผลตรวจ API และข้อจำกัดใน [HISTORICAL_DATA.md](HISTORICAL_DATA.md) โดยยังปิด historical indexing จนกว่าทีมจะตกลง CONTRACT และ 05 รองรับ

`GET /football/history/top-scorer/{season}` อ่านรายชื่อผู้ได้ดาวซัลโวจาก `data/scorer_reference.json` พร้อมลิงก์พรีเมียร์ลีกที่ตรวจทานแล้ว (ปีเริ่มฤดูกาล 2022–2025 เท่านั้น) และคืน 404 เมื่อไม่มีหลักฐาน การตอบคำถามนี้ไม่ได้เปิดดัชนีย้อนหลังทั้งชุดหรือใช้ cache ผู้เล่นที่ตรวจพบข้อมูลขัดแย้ง

ข้อมูลสดแพ็กเกจฟรีที่ทดสอบใช้ `scope=fixtures` จาก football-data.org เท่านั้น ส่วน API-Football ใช้ปี 2024/25 สาธิต เพราะ key ฟรีนี้ไม่รองรับ 2025/26–2026/27

เครดิตข้อมูลย้อนหลัง: © 2024 **Joshua C. Fjelstul, Ph.D.**, [Fjelstul English Football Database](https://github.com/jfjelstul/englishfootball), [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode); ดัดแปลงโดย normalize ชื่อทีมและแปลงตารางเป็นสรุปข้อความ ร่วมกับ [openfootball/england](https://github.com/openfootball/england) (CC0 1.0) เอกสาร/ข้อมูลย้อนหลังที่สร้างเผยแพร่ภายใต้ CC-BY-SA 4.0

## ทำนายผลและจำลองฤดูกาล (CONTRACT v1.7)

- `GET /football/predict?home_team_id=&away_team_id=` — คำนวณความแข็งของสองทีมแล้วเรียก 04 `/local/predict` · ถ้ามีนัดที่ยังไม่แข่งระหว่างสองทีม ใช้ฝั่งเหย้าตามโปรแกรมนัดถัดไป (ลำดับใน query ไม่มีผล) · ไม่เก็บผล
- นัดที่กำลังแข่ง (`LIVE`) ถูกจำลองต่อเฉพาะเมื่อตารางคะแนนยังไม่นับนัดนั้น (ดูจาก `played` เทียบกับนัดที่จบแล้ว) · ถ้าตารางนับแล้วจะไม่จำลองซ้ำ
- `GET /football/simulation` — ผลจำลอง 10,000 ครั้ง (seed 42) ของฤดูกาลปัจจุบัน · เก็บในตาราง `simulation_snapshots` ตาม hash ของ input · คำนวณใหม่หลัง ingest · 04 ล่ม → คืนผลเก่าพร้อม `stale: true` · ไม่เคยมีผล → 503 `SIMULATION_UNAVAILABLE`
- ความแข็งทีม (`app/strengths.py`) = ฤดูกาลนี้ผสมอัตราต่อนัดของฤดูกาลก่อน (k = 10) · ทีมเลื่อนชั้นใช้ค่าเฉลี่ยของ 3 ทีมที่ตกชั้น · ไม่มีข้อมูลฤดูกาลก่อน → ค่าเฉลี่ยลีก 1.35
- env `ENGINES_URL` (ค่าเริ่ม `http://engines:8000`)
- เติมข้อมูลฤดูกาลก่อนให้แม่นขึ้น — ข้อมูลนี้อยู่ใน Postgres ของแต่ละเครื่อง ไม่ได้มากับ git ต้องรันเองครั้งแรก และรันใหม่หลังลบ volume ของ Postgres ถ้าไม่รัน ระบบยังทำงานได้แต่ใช้ค่าเฉลี่ยลีก 1.35 แทนฟอร์มฤดูกาลก่อนของแต่ละทีม (ดู log `strength_prior_league_average`)

  ```bash
  docker compose -p football-assistant exec football-data sh -c 'python scripts/ingest_history.py --database-url "$DATABASE_URL"'
  ```

  - คำสั่งนี้ดาวน์โหลดข้อมูล openfootball / fjelstul ตาม commit ที่ pin ไว้ แล้วเขียนตาราง `historical_matches` และ `historical_standings` · รันซ้ำได้ (upsert) · สำเร็จแล้วจะพิมพ์สรุปที่มี `"seasons": 34`
  - ใน container ไม่มีไฟล์ `.env` ของ repo · script ใช้ env ของ container แทน (`DATABASE_URL` มาจาก `docker-compose.yml`)
  - บนเครื่องที่มี repo ครบ รันจากโฟลเดอร์ `services/07_football_data` ได้ตรง ๆ ตาม [HISTORICAL_DATA.md](HISTORICAL_DATA.md) (ค่าเริ่มต้นเขียนลง SQLite ในเครื่อง ไม่ใช่ DB ของ Docker)
  - เมื่อขึ้นฤดูกาลใหม่ ต้องเลื่อน commit ที่ pin ใน `scripts/ingest_history.py` / `scripts/download_history.py` ให้มีผลของฤดูกาลที่เพิ่งจบ แล้วรันคำสั่งนี้อีกครั้ง

## งานที่ต้องทำต่อ (integration/deploy)

- รีวิวล่าสุด: ตารางคะแนนใน index เปลี่ยนเป็น `standings-<season>` เดียวพร้อม cleanup แบบ retry ได้; ดาวซัลโวย้อนหลังเพิ่มเฉพาะแหล่งที่ผ่านตรวจ (2022/23 และ 2025/26) โดย cache API ของ 2023/24 และ 2024/25 ขัดกับ PL และถูกกันไว้ ดูรายละเอียดใน HISTORICAL_DATA.md

- เพิ่ม Alembic migration และทดสอบกับ PostgreSQL schema `football` จริง
- เพิ่ม lock/job queue ระดับฐานข้อมูลสำหรับหลาย worker และการกู้ job ที่ค้างเมื่อ process หยุด
- ทดสอบร่วมกับบริการ 05/06 และ API ภายนอกจริงหลังพร้อมใช้งาน รวมถึงตรวจความตรงของ alias และ fixture mapping กับข้อมูลจริง

ไม่ต้องใส่ API key ใน repository ให้ตั้งผ่าน environment หรือไฟล์ `.env` ที่ถูก ignore เท่านั้น
