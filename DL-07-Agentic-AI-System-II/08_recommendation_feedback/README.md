# โมดูล 08 — Recommendation & Feedback

เอกสารนี้อธิบายเฉพาะโมดูล 08 (Recommendation & Feedback) ว่าแต่ละไฟล์ทำหน้าที่อะไร
เชื่อมกันอย่างไร รันยังไงให้ขึ้นจริง และตอนนี้ยังขาดอะไรอยู่บ้าง

โมดูลนี้คือ **ปลายทางสุดท้ายก่อนถึงผู้ใช้** — รับผลการตัดสินใจที่ผ่านการวิเคราะห์มาแล้ว
จากโมดูล 07 (Decision & LLM Engine) มาจัดรูปแบบ ตรวจสอบความปลอดภัยของข้อมูลฉุกเฉิน
บันทึกลงฐานข้อมูล แล้วส่งต่อให้ 01 (Web App) แสดงผล พร้อมทั้งรับ feedback จากผู้ใช้กลับเข้าคิว
ตรวจสอบความปลอดภัย

---

## ภาพรวมการไหลของข้อมูล

```
07 (Decision Engine) --> [08: build response + validate emergency contacts]
                                    |
                                    v
                          Postgres (recommendation_log)
                                    |
                                    v
                          01 (Web App) แสดงผลให้ผู้ใช้
                                    |
                                    v
                    ผู้ใช้กด feedback --> [08: classify + เก็บ user_feedback]
                                    |
                                    v
                          ถ้า UNSAFE/INCORRECT --> คิว safety review (มนุษย์ตรวจ)
                                    |
                                    v
                    อนุมัติแล้วเท่านั้น --> ใช้ retrain/evaluate ได้
```

Redis ใช้แยกต่างหากสำหรับ **live update** — ส่งแจ้งเตือนเมื่อความเสี่ยงเปลี่ยน
โดยมี consent, dedup และ cooldown กันแจ้งเตือนถี่เกินไป

---

## แต่ละไฟล์ทำหน้าที่อะไร

### `app/config.py`
อ่านค่า environment variable ทั้งหมดผ่าน `pydantic-settings` (เช่น
`RECOMMENDATION_SCHEMA_VERSION`, `FEEDBACK_RETENTION_DAYS`, `DATABASE_URL`, `REDIS_URL`)
เป็นจุดเดียวที่ทุกไฟล์อื่นเรียกใช้ค่าคอนฟิก ไม่มีไฟล์ไหน hardcode ค่าคอนฟิกเอง

### `app/schema.py`
หัวใจของ contract ทั้งโมดูล — นิยาม `RecommendationResponse` (สิ่งที่ 08 ส่งให้ 01)
และ `FeedbackSubmission` (สิ่งที่ 01 ส่งกลับมา) ด้วย Pydantic model รวม enum ทั้งหมด
(`ActionCode`, `RiskLevel`, `ConfidenceLevel`, `FeedbackCategory` ฯลฯ) มี validator สองตัวสำคัญ:
- แปลง `null` เป็นลิสต์ว่างสำหรับ `emergency_instructions`/`official_contacts` (เผื่อ 07/03 ยังไม่ส่งมา)
- บังคับว่า `expires_at` ต้องมาหลัง `fetched_at` เสมอ

### `app/mock_data.py`
fixture จำลอง 5 สถานการณ์ (`travel_normally`, `change_route`, `delay_travel`,
`avoid_travel`, `emergency_instructions`) ให้ 01 (Web App) เอาไปทดสอบ UI ได้ก่อนที่ 07
จะพร้อมส่งข้อมูลจริง ทุก fixture ต้องผ่าน validator ใน `schema.py` เหมือนข้อมูลจริงทุกประการ

### `app/emergency.py`
ตรวจ `official_contacts` ก่อนส่งให้ผู้ใช้ทุกครั้ง (ไม่ใช่แค่ตอนสร้าง) — ตัดเบอร์ที่
`effective_date` ยังไม่ถึง, รูปแบบเบอร์ผิด, หรือ region ไม่ตรงกับผู้เดินทาง เบอร์ที่ถูกตัด
จะไม่ถูก "แก้" แต่ถูก "ถอดออก" แล้วบันทึกเหตุผลไว้ใน `limitations` และ `degraded_services`
ให้ทีมปฏิบัติการเห็นว่ามีอะไรถูกซ่อนไป

### `app/db.py`
ชั้นเขียน/อ่าน Postgres จริงด้วย SQLAlchemy async + asyncpg มี:
- `wait_for_db()` — retry ตอนเริ่มระบบ เผื่อ Postgres ยังไม่พร้อม
- `save_recommendation()` / `get_recommendation()` — บันทึก/ดึงคำแนะนำ (ตาราง `recommendation_log`)
- `save_feedback()` / `mark_reviewed()` / `fetch_pending_safety_review()` /
  `fetch_reviewed_for_training()` — จัดการ feedback (ตาราง `user_feedback`)

ใช้ `engine` แบบ global ตัวเดียวทั้งโมดูล (สำคัญตอนเขียนเทสต์ async — ดูหัวข้อ "จุดที่ต้องระวัง" ด้านล่าง)

### `app/feedback.py`
รับ feedback จากผู้ใช้ แยกเป็น 2 กลุ่ม: `UNSAFE`/`INCORRECT` ต้องเข้าคิว safety review
ก่อนเสมอ ส่วนที่เหลือบันทึกตรง ๆ มีฟังก์ชัน `classify_free_text()` เป็น fallback
จัดหมวดจากคำในข้อความ (ใช้ regex) กรณี UI ไม่ได้ส่ง category มาให้เอง

### `app/live_update.py`
ตัวจัดการแจ้งเตือนแบบ real-time ผ่าน Redis เก็บเวลาส่งล่าสุดและความเสี่ยงล่าสุดต่อผู้ใช้
1 คน มีกฎ 3 ข้อ: (1) ต้องได้รับ consent ก่อนส่งเสมอ (2) มี cooldown กันสแปม
(3) **ห้ามระงับแจ้งเตือนถ้าความเสี่ยงเพิ่มขึ้น** แม้จะยังอยู่ในช่วง cooldown ก็ตาม
มี `FakeRedis` สำรองไว้ให้ unit test ใช้โดยไม่ต้องพึ่ง Redis จริง

### `app/monitoring.py`
ตั้งค่า structured logging (`structlog`) และ Prometheus metrics โดย**แยก metric ด้าน
ความปลอดภัย** (เช่น `reco_unsafe_feedback_total`) ออกจาก **metric ด้าน UX**
(เช่น `reco_viewed_total`) ตามหลักที่ว่า metric ความปลอดภัยห้ามถูกกลบด้วยตัวเลข UX

### `app/main.py`
ประกอบทุกอย่างเป็น FastAPI app มี endpoint หลัก (เน้นเป็น internal service / worker):
- `GET /health` — เช็คสถานะ service + DB
- `GET /recommendation/mock/{scenario}` — ดึง fixture จำลอง แล้วบันทึกลง DB จริง
- `POST /recommendation/generate` — รับผลประเมินจากโมดูล 07 ตัวจริงมาแปลง ตรวจเบอร์ฉุกเฉิน และบันทึกลง DB จริง
- `GET /recommendation/{request_id}` — ดึงคำแนะนำที่เคยบันทึกไว้ ตรวจ schema ซ้ำก่อนส่ง
  (ถ้าแถวเก่าไม่ตรง schema ปัจจุบัน จะตอบ 500 โดยตั้งใจ ไม่ส่งข้อมูลผิดออกไป)
- `POST /feedback`, `GET /feedback/safety-queue`, `POST /feedback/{id}/review` —
  วงจร feedback และ human safety review queue ทั้งหมด
- `POST /feedback/cleanup` — trigger ลบข้อมูล feedback ที่เก่าเกิน 180 วันตาม retention policy

### `db_schema.sql`
DDL ของตาราง `recommendation_log` และ `user_feedback` มี `CHECK` constraint บังคับค่า
`action_code` และ `risk_level` ให้ตรงตาม enum ใน `schema.py` เป๊ะ — กันไม่ให้แถวที่ผิด
หลุดเข้า DB ได้เลยตั้งแต่ระดับฐานข้อมูล รันอัตโนมัติแค่ตอน Postgres container
เริ่มครั้งแรกเท่านั้น (ผ่าน `docker-entrypoint-initdb.d`)

### `migrations/001_three_risk_levels_four_actions.sql`
สคริปต์ SQL สำหรับรันมือครั้งเดียว ใช้ตอนมี volume `pgdata` เก่าที่ยังมีแถวค่า
`MODERATE`/`CRITICAL` ค้างอยู่ (จาก schema เวอร์ชันก่อนหน้า) ให้แปลงเป็น `LOW/MEDIUM/HIGH`

### `pytest.ini`
ตั้งค่า `pytest-asyncio` ให้ทุกเทสต์ async ใช้ event loop เดียวกันตลอดการรัน
(`asyncio_mode = auto`, `loop_scope = session`) จำเป็นมากเพราะ `db.py` ใช้ engine
แบบ global ตัวเดียว ถ้า loop ไม่ตรงกัน connection pool จะข้ามเทสต์ไม่ได้

### `Dockerfile`
Build image จาก `python:3.12-slim` ติดตั้ง dependency จาก `requirements.txt` แล้วก๊อปปี้
`app/`, `tests/`, และ `pytest.ini` เข้า image รันด้วย `uvicorn app.main:app`

### `docker-compose.yml`
ประกอบ 3 service: `app` (โมดูลนี้), `postgres:16-alpine`, `redis:7-alpine` ทั้งคู่มี
healthcheck และ `app` จะรอให้ทั้งสอง service เป็น `healthy` ก่อนเริ่มทำงาน
mount `db_schema.sql` เข้า Postgres โดยตรงผ่าน volume

### `tests/test_recommendation.py` (26 เคส)
เทสต์ที่ไม่ต้องพึ่ง DB/Redis — ตรวจ schema, ตรวจว่าค่าที่ล้าสมัย (`MODERATE`, `CRITICAL`)
ถูกปฏิเสธจริง, ตรวจการจัดหมวด feedback, และตรรกะ cooldown/consent ของ live update

### `tests/test_emergency_validation.py` (21 เคส)
เทสต์กฎตรวจเบอร์ฉุกเฉินทุกกรณี (เบอร์ผิดรูปแบบ, region ไม่ตรง, วันที่ยังไม่ถึง) รวมถึง
ทดสอบผ่าน endpoint จริงด้วย `TestClient` โดย patch `db` ไว้ไม่ให้ต้องพึ่ง Postgres

### `tests/test_db_integration.py` (3 เคส)
เทสต์ที่ต้องมี Postgres/Redis จริง (เขียน-อ่านคำแนะนำจริง, feedback เข้าคิว safety
review จริง, feedback ที่ reviewed แล้วเข้าชุด training จริง) จะ `skip` อัตโนมัติถ้าต่อ
DB ไม่ได้ ไม่ทำให้ CI แดงทั้งที่แค่ไม่มี Docker

---

## วิธีรันให้ขึ้นจริง

```powershell
# 1) เตรียมค่า config
cp .env.example .env            # หรือ Copy-Item .env.example .env บน PowerShell

# 2) build และรันทั้ง 3 service
docker compose up -d --build

# 3) เช็คว่าทั้ง 3 service healthy
docker compose ps

# 4) ทดสอบเรียก API จริง (บน Windows PowerShell ต้องใช้ curl.exe ไม่ใช่ curl เฉย ๆ)
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/recommendation/mock/avoid_travel

# 5) รัน unit test (ไม่ต้องพึ่ง DB)
docker compose exec app pytest tests/test_recommendation.py tests/test_emergency_validation.py -v

# 6) รัน integration test (ต้องมี Postgres/Redis จาก stepที่ 2 พร้อมแล้ว)
docker compose exec app pytest tests/test_db_integration.py -v

# 7) หยุดระบบ (เก็บข้อมูลไว้)
docker compose down
# หรือ docker compose down -v ถ้าต้องการล้างข้อมูลทั้งหมดเริ่มใหม่
```

**ผลการรันจริงล่าสุด (19 ก.ย. 2026): ผ่านทั้งหมด 50/50 เคส**
(26 + 21 unit test ไม่พึ่ง DB, 3 integration test พึ่ง DB จริง)

### จุดที่ต้องระวังเวลาตั้งค่าใหม่บนเครื่องอื่น

1. **`Dockerfile` ต้องมี `COPY pytest.ini .`** ถ้าลืมบรรทัดนี้ pytest ในคอนเทนเนอร์จะหา
   config ไม่เจอ แล้วตกไปใช้ค่า default ของ `pytest-asyncio` (`loop_scope=function`)
   ทำให้ `test_db_integration.py` รายงานผิดว่า "Postgres is not reachable" ทั้งที่ต่อได้จริง
2. **`require_db` fixture ใน `test_db_integration.py` ต้องใช้ `@pytest_asyncio.fixture`**
   ไม่ใช่ `@pytest.fixture` เฉย ๆ เพราะเป็น async fixture — pytest-asyncio โหมด strict
   ไม่รองรับแบบเดิม
3. **แก้ไฟล์บนเครื่องแล้วต้อง `docker compose up -d --build` ใหม่เสมอ** เพราะ Dockerfile
   copy โค้ดเข้า image ตอน build เท่านั้น ไม่ใช่ live-mounted volume แก้ไฟล์เฉย ๆ
   จะไม่มีผลกับคอนเทนเนอร์ที่รันอยู่

---

## งานนี้ยังต้องการอะไรเพิ่มอีก

### ข้อยุติทางสถาปัตยกรรม (Architecture Alignment)
- **บทบาท 02 vs 08**: 02 (API Backend) ทำหน้าที่เป็น **Single Public Gateway / BFF** หน้าบ้านสำหรับ 01 (Web App) ส่วน 08 ทำหน้าที่เป็น **Internal Domain Service & Worker** (Formatting, Emergency Safety Validation, Feedback Safety Review Queue, และ Live Alert Engine) เพื่อไม่ให้สับสน ไม่มี alias `/v1/` ใน 08
- **`confidence` เป็นตัวเลขหรือหมวดหมู่**: 07 ยังส่งเป็น `LOW/MEDIUM/HIGH` (ordinal) ตอนนี้ 08 รองรับทั้งสองแบบผ่าน `confidence` และ `confidence_level`
- **`FEEDBACK_RETENTION_DAYS`**: ปรับเป็น 180 วันตรงกันแล้วทั้งใน 08 และ root `.env.example` ตามข้อกำหนด P-23 ของ 02 (Contract Register v4)
- **เจ้าของข้อมูล emergency contacts**: 07 สร้างโมดูล `emergency.py` และ `handoff.py` พร้อม catalog เรียบร้อยแล้ว รูปแบบส่งออกตรงกับ `EmergencyContact` ของ 08 เป๊ะ (Contract Register v4)
- **พื้นที่ให้บริการ (coverage)**: เบื้องต้นรับไทยอย่างเดียว (TH, D-11)

### งานที่ 08 ทำเรียบร้อยแล้ว
- **ต่อกับ 07 ตัวจริง (เรียบร้อยแล้ว)**: เพิ่ม `DecisionEngineClient` (`app/decision_client.py`),
  `adapter.py` และ endpoint `POST /recommendation/generate` ใน `main.py` เพื่อเรียก API
  `POST /v1/decisions` ของ 07 พร้อม mapping ผลลัพธ์และตรวจสอบเบอร์ฉุกเฉินบันทึกลง Postgres เรียบร้อยแล้ว
- **ฟื้นฟู Internal `GET /recommendation/{request_id}` (เรียบร้อยแล้ว)**: สำหรับดึงคำแนะนำที่เคยบันทึกไว้ ตรวจ schema ซ้ำและ validate emergency contacts ตาม region
- **เขียน job ลบข้อมูลตาม retention policy จริง (เรียบร้อยแล้ว)**: เพิ่ม `purge_expired_feedback()` ใน `app/db.py`, periodic background cleaner ใน FastAPI `lifespan`, และ endpoint `POST /feedback/cleanup`
- **แก้ deprecation warning 2 จุดเรียบร้อยแล้ว**:
  - `db.py` เปลี่ยน `datetime.utcnow()` เป็น `datetime.now(timezone.utc)` แล้ว
  - `main.py` เปลี่ยน `@app.on_event("startup")` เป็น FastAPI `lifespan` handler แล้ว
- **Dispatcher แจ้งเตือน fallback (เรียบร้อยแล้ว)**: มีฟังก์ชัน `dispatch_notification()` ใน `app/live_update.py` รองรับ fallback structured logging เมื่อยังไม่ได้ใส่ provider keys
- **ผลทดสอบล่าสุด**: ผ่านครบ 58/58 unit tests (100% pass)