# 02 API Backend + Response/Log · `api`, `worker`, `beat`

Gateway ระหว่างหน้าเว็บกับระบบ AI — auth, session/history, เรียก router, บันทึก log/feedback, ระบบ Admin และ Celery beat ที่สั่ง 07 ตามเวลา
ทุก endpoint ตอบตาม [`docs/CONTRACT.md`](../../docs/CONTRACT.md) §0, §1, §1.1 · เรียก 03 ตาม §2, 07 ตาม §7, 05 ตาม §6

## ยกอะไรมาจาก Travel Safety และตัดอะไรทิ้ง

| ยกมา (ปรับแล้ว) | อยู่ที่ |
|---|---|
| Problem-JSON + error code กลาง | `app/core/errors.py`, `app/api/problem.py`, `app/api/error_handlers.py` |
| middleware: `X-Request-ID`, body guard (413/415), security headers | `app/api/middleware/` |
| AgentClient → **RouterClient** (deadline 45s รวมทั้ง call, retry 1 ครั้งเฉพาะ connect error / 502 / 503, circuit breaker) | `app/clients/router_client.py`, `app/clients/circuit_breaker.py` |
| rate limit (Redis, ถ้า Redis ล่มจะปล่อยผ่าน) | `app/infra/store.py`, `app/infra/rate_limit.py` |
| conversations + follow-up history, feedback | `app/response_log/` |
| admin + audit log (ย่อเหลือ §1.1) | `app/api/routes/admin/`, `app/services/audit.py` |
| Celery worker + beat (เปลี่ยนเป็นงาน "สั่ง 07 ตามเวลา") | `app/workers/` |
| Alembic, pytest | `migrations/`, `tests/` |

ตัดทิ้งตาม `00_PLAN_OVERVIEW.md` หัวข้อ 5: Keycloak/JWKS (ใช้ JWT HS256 + httpOnly cookie), MinIO/export, OpenTelemetry, idempotency key, column encryption/retention, safety review queue, trips/alerts

## โครงสร้าง

```
app/
  main.py               create_app() + ประกอบ client ทั้งหมด
  core/                 config, errors, ids (UUIDv7), logging (JSON), security (bcrypt + JWT), clock (+07:00)
  api/                  deps (auth, require_admin), middleware, routes/{health,auth,chat,football,admin/*}
  clients/              RouterClient, circuit breaker, ServiceClient (07 / 05)
  response_log/         บันทึก log/history/feedback (background task) + query ของหน้า admin
  services/             chat_service, audit, users
  db/                   models (schema `app`), session
  workers/              celery_app, schedule (ตาราง beat ตาม CONTRACT §7), tasks
  seed.py               admin + demo1–demo3
migrations/             Alembic (สร้าง schema `app`)
stubs/                  stub ของ 03 router และ 07 football-data (+ ส่วน index ของ 05) สำหรับ dev
tests/                  pytest 117 เคส
```

## ตัวแปร env

| ชื่อ | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://app:app@postgres:5432/football` | ตาราง อยู่ใน schema `app` |
| `REDIS_URL` | `redis://redis:6379/0` | rate limit, cache, broker ของ Celery · ค่าว่าง = เก็บในหน่วยความจำ (dev/test เท่านั้น) |
| `JWT_SECRET_KEY` | **ต้องตั้ง** (≥ 32 ตัวอักษร) | ไม่ตั้ง = service ไม่ขึ้น |
| `COOKIE_SECURE` | `false` | ตั้ง `true` เมื่อเปิดผ่าน HTTPS |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | คั่นด้วย `,` |
| `AI_ROUTER_SERVICE_URL` | `http://router:8000` | |
| `FOOTBALL_DATA_URL` | `http://football-data:8000` | |
| `RETRIEVAL_URL` | `http://retrieval:8000` | ใช้เฉพาะหน้า admin Knowledge Base |
| `SEED_ADMIN_PASSWORD` | ว่าง | ว่าง = ไม่สร้าง `admin` |
| `SEED_DEMO_PASSWORD` | ว่าง | ว่าง = ไม่สร้าง `demo1`–`demo3` |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `20` | CONTRACT §1 |
| `GIT_SHA` | `0.1.0` | ค่า `version` ใน `/health` |
| `ENVIRONMENT` | `dev` | `prod` = ปิด `/docs` |

## รัน

**รันเครื่องตัวเองโดยไม่ต้องมี service อื่น** (ใช้ stub)

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/pip

uvicorn stubs.router_stub:app --port 8003 &
uvicorn stubs.football_data_stub:app --port 8007 &

export DATABASE_URL=sqlite+aiosqlite:///./dev.db REDIS_URL= \
       JWT_SECRET_KEY=dev-only-secret-key-at-least-32-chars \
       SEED_ADMIN_PASSWORD=admin1234 SEED_DEMO_PASSWORD=demo1234 \
       AI_ROUTER_SERVICE_URL=http://localhost:8003 \
       FOOTBALL_DATA_URL=http://localhost:8007 RETRIEVAL_URL=http://localhost:8007
alembic upgrade head && python -m app.seed
uvicorn app.main:app --port 8000 --reload          # เอกสาร API: http://localhost:8000/docs
```

stub ของ router: ข้อความ `__error__` → router ตอบ 500 (api ตอบ 502) · `__slow__` → ช้า 50 วิ (api ตอบ 504)

**ใน docker compose** (Dockerfile / compose เป็นของ member6)

| service | command |
|---|---|
| `api` | `sh scripts/entrypoint.sh` (migrate → seed → uvicorn :8000) |
| `worker` | `celery -A app.workers.celery_app worker --loglevel=INFO` |
| `beat` | `celery -A app.workers.celery_app beat --loglevel=INFO` |

`api` ต้องรอ `postgres` และ `redis` พร้อมก่อน · healthcheck ใช้ `GET /health` (มี `GET /ready` ที่เช็ก DB ด้วย)

## เทส

```bash
pytest -q          # ใช้ SQLite + stub ผ่าน ASGI transport ไม่ต้องมี Postgres/Redis/docker
ruff check . && ruff format --check .
```

ครอบคลุม: รูปแบบ response ตาม contract · follow-up ส่ง history ≤ 10 ข้อความ · 401/403/404/409/413/415/422/429/502/504 · feedback 409 `MESSAGE_NOT_READY` · user ธรรมดาเรียก `/api/admin/*` ได้ 403 · audit ทุก action · ระงับบัญชีแล้ว cookie เดิมใช้ไม่ได้ทันที · circuit breaker · ตาราง beat (ช่วง ศ 18:00 – อ 06:00 ทุก 30 นาที)

## จุดที่ควรรู้

- **บันทึก log หลังตอบ** — `/api/chat` สร้าง `message_id` แล้วตอบทันที ส่วนการเขียนข้อความ/log ลง DB ทำใน background task · ระหว่างนั้น id ถูกทำเครื่องหมาย "pending" ใน Redis ถ้า feedback มาก่อน api รอได้ 3 วิ แล้วตอบ 409 · ถ้า id ไม่เคยมีจริงตอบ 404 ทันที
- **session ใหม่** ถูกสร้างเมื่อ router ตอบสำเร็จเท่านั้น คำถามแรกที่ล้มจึงไม่ทิ้งแชทว่างไว้ในรายการ
- **context ให้ router** มาจาก 07 `/football/status` (cache 5 นาที) · ส่ง `last_ingest_at` ต่อให้ router ใช้ในข้อความ fallback (CONTRACT v1.3) · ถ้า 07 ล่ม แชทยังใช้ได้ โดยใช้ฤดูกาลจากปฏิทิน และ `current_matchweek` / `last_ingest_at` เป็น `null`
- **สิทธิ์ admin** ตรวจที่ api ทุกครั้งจาก DB (ไม่เชื่อ role ใน token) เปลี่ยน role / ระงับบัญชีจึงมีผลทันที
- **error จาก 07** ที่หน้าเว็บต้องเห็น (`JOB_ALREADY_RUNNING`, `REPORT_NOT_EDITABLE`, `NOT_FOUND`, …) ส่งต่อด้วย code เดิม ที่เหลือเป็น 502 `FOOTBALL_DATA_UNAVAILABLE`
- **`triggered_by` / `edited_by`** api ใส่เองเป็น `admin:<user_id>` หรือ `beat` ไม่รับจากหน้าเว็บ
