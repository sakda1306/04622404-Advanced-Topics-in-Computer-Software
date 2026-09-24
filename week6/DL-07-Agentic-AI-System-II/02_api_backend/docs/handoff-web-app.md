# Handoff: API Backend → Web App (Module 01)

สถานะ ณ 2026-09-18: Phase 5 (5.1–5.12) ของ `02_api_backend` เสร็จหมดแล้ว พร้อมให้เริ่ม integrate

## 1. Base URL

| Environment | URL |
|---|---|
| Local dev (`docker compose up -d --build --wait`) | `http://localhost:8000` |
| Mock Travel AI Agent (ไม่เกี่ยวกับ Web App โดยตรง) | `http://localhost:8010` |

## 2. Contract

- Swagger UI: `http://localhost:8000/docs` (เปิดอยู่ default, `ENABLE_DOCS=true`)
- `openapi.json`: [`../openapi.json`](../openapi.json) — commit ไว้ที่ root ของโมดูลนี้ อัปเดตด้วย `make openapi` ทุกครั้งที่ API เปลี่ยน (มี test กันไม่ให้หลุด)
- Error ทุกตัวเป็น RFC 9457 Problem Details (`application/problem+json`) — field `code` เป็นค่าคงที่ที่ใช้ switch ได้ (`RATE_LIMITED`, `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT`, ...), `422` ตอนนี้ตรงกับ schema จริงแล้ว (ไม่ใช่ `HTTPValidationError` ที่ FastAPI generate เอง)

## 3. Auth (dev)

```bash
docker compose exec api python -m scripts.dev_token --sub alice --scope travel:read --scope travel:write
```

ได้ JWT (HS256, dev-only) เอาไปใส่ `Authorization: Bearer <token>` — ใช้พอสำหรับ dev/demo

ถ้าอยากทดสอบกับ JWKS จริงก่อน 01 มี OIDC library ของตัวเอง มี Keycloak กลางให้แล้ว (`identity/README.md`
ที่ root ของ repo) client `web-app` รองรับ authorization code + PKCE ตรงกับที่ 01 จะต้องใช้ตอน implement จริง

`CORS_ALLOWED_ORIGINS` default เปิดให้ `http://localhost:3000` แล้ว

## 4. Recommendation flow: request → 202 → SSE

Diagram: [`diagrams/sse-recommendation-flow.html`](diagrams/sse-recommendation-flow.html)

จุดที่ต้องระวัง (ไม่ทำตามนี้จะพังเงียบๆ):

1. **`EventSource` ส่ง header ไม่ได้** — ห้ามพยายามแนบ `Authorization` เข้ากับ SSE connection ตรงๆ ต้องขอ **stream ticket** ก่อนเสมอ: `POST /v1/jobs/{job_id}/stream-ticket` (ใช้ JWT ปกติ) → เอา `ticket` ที่ได้ไปต่อ query string `GET /v1/jobs/{job_id}/events?ticket=...`
2. **`EventSource` reconnect เองโดย default** — พอ backend ปิด response หลังส่ง `event: completed` เบราว์เซอร์จะพยายามต่อใหม่อัตโนมัติถ้าไม่สั่ง `.close()` เอง ต้องเรียก `eventSource.close()` ทันทีที่ได้ event `completed` / `failed` / `cancelled`
3. Progress event มาเป็นลำดับ `queued → fetching_data → assessing_risk → generating_advice → completed` (หรือ `partial_result` / `failed` / `needs_clarification` แทน `completed`) — ห้าม hardcode ว่าต้องมีครบทุก stage เสมอ
4. Endpoint บางอันตอบ `200` แบบ sync ได้เลยถ้า backend มีคำตอบพร้อม (ไม่ต้องเปิด SSE) — เช็ค status code ที่ได้กลับมาก่อนตัดสินใจเปิด SSE เสมอ

## 4.1 Trip live alert: อ่านด้วย polling (ตั้งใจไม่ push)

Diagram: [`diagrams/trip-live-alert-flow.html`](diagrams/trip-live-alert-flow.html)

Trip ที่เปิด live alert ไว้ (`consent_at` ตั้งแล้ว) จะถูก Celery beat สแกนซ้ำเป็นระยะ (ทุก P-56 นาที) แล้ว re-assess ผ่าน Travel AI Agent เอง **โดย Web App ไม่ได้เป็นคนสั่ง** — ถ้า risk level หรือชนิดคำแนะนำเปลี่ยนจากครั้งก่อน backend จะเติม message ใหม่ใน conversation ของ trip นั้นให้เงียบๆ

**สำคัญ:** ทีมตัดสินใจแล้วว่า**ไม่ทำ WS ในรอบนี้** (D-04 — โจทย์อาจารย์ให้เลือก SSE หรือ WS อย่างใดอย่างหนึ่ง ไม่บังคับทั้งคู่) ดังนั้นไม่มี push channel ไปหา Web App เลย Web App **ต้อง poll เองเป็นระยะ** ด้วย `GET /v1/conversations/{conversation_id}/messages` ถึงจะเห็น alert ใหม่ ไม่ต้อง poll ถี่กว่า P-56 นาที เพราะ backend เองก็ไม่ scan ถี่กว่านั้น — เป็นดีไซน์ตั้งใจ ไม่ใช่ของที่รอทำเพิ่ม

## 5. Architecture reference

ใช้ diagram เดิมที่มีอยู่ได้เลย ยังตรงกับโค้ดปัจจุบัน (เช็คแล้วหลังทำ step 5.12 ไม่มีอะไรกระทบ):

- [`diagrams/backend-architecture.html`](diagrams/backend-architecture.html) — ภาพรวมระบบ (client → API → Redis/PostgreSQL → Celery worker → Agent/MinIO)
- [`diagrams/api-layers.html`](diagrams/api-layers.html) — ชั้นภายใน API (middleware → HTTP → services → domain → infrastructure)

## 6. รู้ไว้ก่อนเริ่ม

- **WebSocket `/v1/ws` descoped แล้ว ไม่ทำในโปรเจกต์นี้** (D-04) — real-time ใช้ SSE อย่างเดียว (ดูข้อ 4), trip alert ใช้ poll (ดูข้อ 4.1)
- Auth ใช้ dev token สำหรับ dev/demo ได้เลย ถ้าต้องการ Keycloak จริงดู `identity/README.md` ที่ root
- Rate limit: user 60 req/min, IP 120 req/min (default) —ตอบ `429` + header `Retry-After`
