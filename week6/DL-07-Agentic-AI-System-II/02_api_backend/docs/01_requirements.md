# 01 — Requirements: API & Backend

> สถานะ: **Draft v0.1** — ค่าตัวเลขทั้งหมดเป็นข้อเสนอ ปรับได้ที่ [02_api_spec.md §2 Tunable Parameters](02_api_spec.md#2-tunable-parameters)

## 1. ขอบเขต

Backend คือ **trust boundary** ระหว่าง Web/Mobile App กับ Travel AI Agent

- **In scope:** API contract, authentication/authorization, rate limit, request flow, job queue (Celery), progress streaming, validate/sanitize ผลลัพธ์จาก Agent, data retention, observability, feedback สำหรับ MLOps
- **Out of scope:** เรียก Weather/Transport/Disaster API, Risk Model, RAG, Decision Agent, LLM — เป็นหน้าที่ของ Travel AI Agent (Module 03) ผ่าน `AGENT_SERVICE_URL`

## 2. Actors

| Actor | บทบาท |
|---|---|
| Traveler | ขอคำแนะนำ, ถามต่อ, ให้ feedback, จัดการข้อมูลตัวเอง |
| Web/Mobile App (Module 01) | Client เรียก REST + SSE/WebSocket |
| Travel AI Agent (Module 03) | Downstream service |
| Admin / Ops / Safety Reviewer | ดูสถานะระบบ, audit, ตรวจ unsafe report |
| MLOps Pipeline | รับ prediction record + feedback แบบ anonymized |
| Identity Provider (OIDC) | ออก JWT |

## 3. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | `POST /v1/travel/recommendations` รับ origin, destination, datetime, preferences, question | Must |
| FR-02 | ตรวจ JWT, permission, rate limit, schema | Must |
| FR-03 | สร้าง `request_id` และรับ/สร้าง `correlation_id` | Must |
| FR-04 | Normalize timezone (UTC + IANA), language (BCP-47), coordinates, preferences | Must |
| FR-05 | เรียก Agent พร้อม timeout และ cancellation | Must |
| FR-06 | งานนานใช้ Celery → `202` + `job_id`, ดูสถานะและยกเลิกได้ | Must |
| FR-07 | Progress events ผ่าน SSE/WS | Must |
| FR-08 | Validate และ sanitize response จาก Agent | Must |
| FR-09 | Response มี risk_level, recommendation_type, data_freshness, service_status, emergency_instructions (บังคับเมื่อ HIGH) | Must |
| FR-10 | ข้อมูล disaster/weather ขาดหรือ stale ห้ามตอบ `TRAVEL_NORMALLY` | Must |
| FR-11 | Follow-up ผ่าน `conversation_id` | Must |
| FR-12 | `Idempotency-Key` บน POST (key ซ้ำ + body ต่าง → 409) | Must |
| FR-13 | Agent ขอข้อมูลเพิ่มได้ (`needs_clarification`) แทนการเดา | Must |
| FR-14 | Feedback ต่อ recommendation; unsafe report เข้า safety review queue | Should |
| FR-15 | Trips + ประเมินซ้ำ + live alert เมื่อผู้ใช้ยินยอม | Should |
| FR-16 | `/v1/me` ดู/แก้/ลบ/export ข้อมูล (PDPA) | Should |
| FR-17 | `/v1/service-status` สาธารณะ | Should |
| FR-18 | Admin tools (RBAC + audit log) | Could |
| FR-19 | Export anonymized data สำหรับ retraining | Could |

## 4. Non-Functional Requirements

| ID | หมวด | ข้อกำหนด (อ้างอิงค่าใน Tunable Parameters) |
|---|---|---|
| NFR-01 | Performance | sync p95 ≤ `P-01`; เกิน `P-02` → async job |
| NFR-02 | Availability | `P-03`; dependency ล่มบางตัวยังตอบ `partial_result` |
| NFR-03 | Security | OIDC, JWT อายุ `P-10`, JWKS, CORS allowlist, กัน IDOR, service auth ไป Agent |
| NFR-04 | Privacy | ไม่ log token/PII, ปัดพิกัดเป็น geohash `P-20`, retention `P-21..P-24` |
| NFR-05 | Rate limit | `P-30..P-33` |
| NFR-06 | Observability | correlation_id ทุก log/trace, trace HTTP → Celery → Agent, Prometheus |
| NFR-07 | Caching | เฉพาะข้อมูลสด, key = location + time bucket + language, ไม่แชร์ข้อมูลส่วนตัว |
| NFR-08 | Errors | RFC 9457, error code คงที่, ไม่เปิด stack trace |
| NFR-09 | Testability | layered, contract test, respx, Testcontainers |
| NFR-10 | Deployability | Docker, `/health`, `/ready`, config ผ่าน env/secret manager |

## 5. Assumptions

1. มี OIDC Identity Provider ภายนอก (dev ใช้ local issuer ไปก่อน)
2. Agent มี HTTP API ตาม contract ใน [02_api_spec.md §9](02_api_spec.md#9-agent-contract-backend--travel-ai-agent)
3. Web App ใช้ SSE เป็นช่องทาง real-time เดียว — ไม่ทำ WebSocket รอบนี้ (D-04)
4. รองรับเฉพาะผู้ใช้ที่ login (ไม่มี guest) ในรอบแรก
5. Admin tools อยู่ในแผน แต่ทำหลัง core flow

## 6. Open Questions

| # | คำถาม | ผู้ตัดสิน |
|---|---|---|
| Q1 | Identity Provider ตัวจริง — **ปิดสำหรับ dev:** Keycloak (D-01); ค่า prod ยังเปิดอยู่ (D-101) | ทีม |
| Q2 | Agent contract ตกลงกับ Module 03 | Backend + Module 03 |
| ~~Q3~~ | ~~SSE vs WebSocket~~ — **ปิดแล้ว: SSE เท่านั้น** (D-04, `02_api_spec.md`) | Backend + Module 01 |
| Q4 | รองรับ guest หรือไม่ | ทีม |
| Q5 | ค่าตัวเลข SLO / rate limit / retention | ทีม |
| Q6 | Admin tools รอบนี้หรือไม่ | ทีม |
