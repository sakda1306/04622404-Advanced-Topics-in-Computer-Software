# Week 6 — Team D: AI-Powered Real-Time Travel Safety & Advisory Assistant

> **Team repository (source of truth):** https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D
>
> This folder is a `git subtree` copy of the team repository (squashed, `main` @ `874b8e8`). It is kept here for submission. Full history and all contributors are in the team repository.

## My part (Sakda Baokham)

Team D has 7 members and 8 modules (DL-07: Agentic AI System II). My roles were **API Backend owner (module 02)**, **team coordinator**, and **integrator of all modules**.

### 1. API Backend — module 02 (`DL-07-Agentic-AI-System-II/02_api_backend`)
- FastAPI service that acts as the trust boundary between the Web App and the Travel AI Agent: authentication (Keycloak / JWT), CORS, request validation, error responses (RFC 7807 style `ProblemResponse`).
- Recommendations, conversations (follow-up questions, cursor-paginated history), trips, live alerts (Celery beat), feedback and safety review queue, audit log.
- Background workers (Celery + Redis), PostgreSQL models and Alembic migrations, data export / retention purge on MinIO, AES-GCM column encryption, admin endpoints.
- Observability: `/ready`, `/metrics`, service status, OpenTelemetry tracing.
- Contract-first design: OpenAPI contract (`openapi.json`), contract and schemathesis tests, a mock Agent so the backend did not wait for module 03, CI workflow, and the Web App handoff document with sequence diagrams (`02_api_backend/docs/`).
- Verification: 1029 non-e2e tests with 96% coverage and 45/45 e2e tests passing (2026-09-19).

### 2. Coordination
- Wrote the team workflow in the root [README](#team-d--dl-07-agentic-ai-system-ii): module assignment table, one personal branch per member, PR into `develop`, merge into `main` at milestones, and commit message rules.
- Wrote the contract register and finalised the 02/08 architecture scope (D-12) so that every module agreed on the same interfaces.
- Reviewed and merged teammates' branches (modules 01, 03, 04, 05, 07, 08) into `develop` and resolved conflicts.

### 3. Integration of all modules
- Connected the modules end to end: Web App → API Backend → Travel AI Agent → external data / data integration / risk knowledge → decision LLM engine → recommendation & feedback.
- Shared infrastructure: `docker-compose.yml`, `docker-compose.integration.yml`, Keycloak identity provider and realm (`identity/`).
- Cross-module contract tests and end-to-end tests (`tests/integration/`), plus fixes across modules found during integration (for example passing emergency instructions from module 07 through 03 to 02, and feedback retention in module 08).

---

# Team D — DL-07: Agentic AI System II

โปรเจกต์กลุ่มวิชา Advanced Topics in Computer Software (04622404)
พัฒนาตามแผนของอาจารย์ใน [`DL-07-Agentic-AI-System-II/`](DL-07-Agentic-AI-System-II/)

---

## 👥 ตารางแบ่งงาน — 1 คน 1 โมดูล

7 คน 8 โมดูล → มี 1 คนรับ 2 โมดูล (ตกลงกันในทีม)

| #   | โมดูล                        | งานหลัก                                 | ผู้รับผิดชอบ       | GitHub                         | branch                         |
| --- | ---------------------------- | --------------------------------------- | ------------------ | ------------------------------ | ------------------------------ |
| 01  | `01_web_app`                 | Next.js, TypeScript, แผนที่, live alert | โชคอนันต์ อันโน    | `aunoford89@gmail.com`         | `Chokanan-01-WebApp`           |
| 02  | `02_api_backend`             | FastAPI gateway, auth, CORS             | ศักดา เบ้าคำ       | `sakda130646@gmail.com`        | `sakda-02-api-backend`         |
| 03  | `03_travel_ai_agent`         | LLM planner, tool routing               | ปภาวิทย์ แก้วรักษ์ | `kokayou1234@gmail.com`        | `paphawit-03-traval-ai-agent`  |
| 04  | `04_external_data_services`  | adapter weather / transport / disaster  | ศุภวิชญ์ มหาวงค์   | `mahawongsupawit125@gmail.com` | `supawit-04-external_data`     |
| 05  | `05_data_integration`        | normalize → canonical schema            | ศุภวิชญ์ มหาวงค์   | `mahawongsupawit125@gmail.com` | `supawit-05-data_integration`  |
| 06  | `06_risk_knowledge_services` | risk model + RAG knowledge base         | อธิกรณ์ น้ำฉ่า     | `atikorn.namcham@gmail.com`    | `atikorn-06-risk-knowledge`    |
| 07  | `07_decision_llm_engine`     | ตัดสินใจ + อธิบายผล                     | เมฆใหม่ จันทร์แก้ว | `mekmai4234@gmail.com`         | `mekmai-07-decision-llm`       |
| 08  | `08_recommendation_feedback` | ข้อเสนอแนะ + feedback loop              | พลกฤต สมทรง        | `phonlakrit012@gmail.com`      | `phonlakrit-08-recommendation` |

## 🌿 โครงสร้าง branch

```
main                    ← เวอร์ชันส่งอาจารย์ / ใช้งานได้จริงเสมอ
 │                        merge จาก develop เฉพาะตอนถึง milestone
 └── develop            ← branch รวมงานของทุกคน (integration)
      │
      ├── sakda-03-travel-ai-agent        ← branch ประจำตัว อยู่ยาวทั้งเทอม
      ├── somchai-04-external-data        ← ไม่ลบหลัง merge
      ├── nattapong-01-web-app
      └── ... (1 คน 1 branch)
```

### กฎการตั้งชื่อ branch

```
<ชื่อตัวเอง>-<เลขโมดูล>-<ชื่อโมดูลย่อ>
```

| ตัวอย่าง                    | ถูก/ผิด                              |
| --------------------------- | ------------------------------------ |
| `sakda-03-travel-ai-agent`  | ✅                                   |
| `somchai-04-external-data`  | ✅                                   |
| `nattapong-07-decision-llm` | ✅                                   |
| `sakda`                     | ❌ ไม่รู้ว่าทำโมดูลไหน               |
| `feature-3`                 | ❌ ไม่รู้ว่าใครทำ                    |
| `Sakda_03_Travel_AI_Agent`  | ❌ ใช้ตัวพิมพ์เล็กและขีดกลางเท่านั้น |

**คนที่รับ 2 โมดูล** ให้สร้าง 2 branch แยกกัน เช่น `somchai-07-decision-llm` และ `somchai-08-recommendation`
เพื่อให้ PR แยกกันชัดเจน อาจารย์ตรวจง่าย

### หน้าที่ของแต่ละ branch

| branch          | ใครแก้ได้              | push ตรงได้ไหม                            |
| --------------- | ---------------------- | ----------------------------------------- |
| `main`          | ไม่มีใคร               | ❌ เข้าผ่าน PR จาก `develop` เท่านั้น     |
| `develop`       | ไม่มีใคร               | ❌ เข้าผ่าน PR จาก branch ส่วนตัวเท่านั้น |
| `ชื่อ-NN-โมดูล` | เจ้าของ branch คนเดียว | ✅ push ได้ตามใจ วันละกี่ครั้งก็ได้       |

---

## 🚀 วันแรก — ทำครั้งเดียว

### 1. ตั้งชื่อตัวเองให้ถูก (สำคัญที่สุด เพราะอาจารย์ตรวจรายบุคคล)

```bash
git config --global user.name "ชื่อจริงภาษาอังกฤษ"
```

```bash
git config --global user.email "email-ที่ใช้สมัคร-github@example.com"
```

> ⚠️ **email ต้องตรงกับที่ใช้สมัคร GitHub** ไม่งั้น commit ของคุณจะไม่ผูกกับโปรไฟล์
> และไม่ขึ้นในหน้า Contributors — **แก้ย้อนหลังไม่ได้**

เช็คว่าถูกแล้ว:

```bash
git config --global user.name; git config --global user.email
```

### 2. clone repo

```bash
git clone https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D.git
```

### 3. สร้าง `.env` ของตัวเอง

```bash
copy .env.example .env
```

แล้วเปิด `.env` เติมค่าจริง — **ไฟล์นี้ไม่ขึ้น git** ทุกคนมีของตัวเอง
ถ้าต้องเพิ่มตัวแปรใหม่ ให้เพิ่ม**ชื่อตัวแปรค่าว่าง**ใน `.env.example` แล้ว commit เฉพาะไฟล์นั้น

### 4. สร้าง branch ประจำตัว — ครั้งเดียว ใช้ทั้งเทอม

```bash
git switch develop
```

```bash
git switch -c sakda-03-travel-ai-agent
```

_(เปลี่ยนเป็นชื่อและโมดูลของตัวเอง — ดูตารางแบ่งงานข้างบน)_

```bash
git push -u origin sakda-03-travel-ai-agent
```

---

## 🔄 การทำงานประจำวัน

### A. เขียนงานของตัวเอง — ทำได้ตลอด ไม่ต้องรอใคร

```bash
git switch sakda-03-travel-ai-agent
```

```bash
git add -A; git commit -m "feat(03): เพิ่ม intent router"
```

```bash
git push
```

**commit และ push บ่อย ๆ ได้เลย** วันละ 5 ครั้งก็ได้ ไม่กระทบใคร เพราะอยู่ใน branch ตัวเอง

### B. งานเสร็จเป็นก้อน → ส่งขึ้น `develop`

1. push งานล่าสุดขึ้น branch ตัวเองให้ครบ
2. เปิด PR บนเว็บ: `ชื่อ-03-travel-ai-agent` → **`develop`**
3. ขอเพื่อน 1 คน approve
4. กด **Create a merge commit**
5. **ไม่ต้องลบ branch** — ใช้ต่อได้เลย

### C. ดึงงานเพื่อนมาใช้ — ทำทุกเช้า

พอเพื่อนคนที่ 1 merge ขึ้น `develop` แล้ว คนที่ 2 ดึงมาใช้แบบนี้:

```bash
git switch develop; git pull
```

```bash
git switch sakda-03-travel-ai-agent
```

```bash
git merge develop
```

```bash
git push
```

> 💡 **ทำทุกเช้าก่อนเริ่มงาน** อย่ารอเป็นอาทิตย์
> ยิ่ง branch ตัวเองห่างจาก `develop` นาน ยิ่ง conflict หนักตอน merge
> merge ทุกวัน = conflict เล็ก ๆ แก้ 2 นาที · merge เดือนละครั้ง = conflict 200 บรรทัด

### ภาพรวมทั้งวงจร

```
     branch ตัวเอง                develop                 branch เพื่อน
          |                          |                          |
  commit -|                          |                          |
  commit -|                          |                          |
  push ---|                          |                          |
          |                          |                          |
          |---- PR + merge --------->|                          |
          |                          |<---- PR + merge ---------|
          |                          |                          |
          |<--- git merge develop ---|                          |
          |       (ได้งานเพื่อนมา)      |---- git merge develop -->|
          |                          |                          |
```

## 💬 commit message

```
<type>(<เลขโมดูล>): <ทำอะไร>
```

| type       | ใช้เมื่อ                      | ตัวอย่าง                             |
| ---------- | ----------------------------- | ------------------------------------ |
| `feat`     | เพิ่มของใหม่                  | `feat(04): เพิ่ม weather adapter`    |
| `fix`      | แก้บั๊ก                       | `fix(02): แก้ CORS header ผิด`       |
| `docs`     | เอกสาร                        | `docs(06): อธิบาย risk threshold`    |
| `refactor` | รื้อโค้ดโดยไม่เปลี่ยนพฤติกรรม | `refactor(05): แยก schema validator` |
| `test`     | เทส                           | `test(03): เพิ่มเทส intent router`   |
| `chore`    | งานบ้าน config                | `chore: อัปเดต .env.example`         |

เขียนภาษาไทยได้ ขอแค่บอกให้ชัดว่าทำอะไร

---

## 🚨 ไฟล์ที่ conflict ได้ — ต้องบอกในกลุ่มก่อนแก้

เพราะ 8 โมดูลอยู่คนละโฟลเดอร์ ปกติจะไม่ชนกันเลย ยกเว้นไฟล์กลางเหล่านี้:

| ไฟล์                            | เพราะ                            |
| ------------------------------- | -------------------------------- |
| `.env.example`                  | ทุกคนอยากเพิ่มตัวแปรของตัวเอง    |
| `docker-compose.yml`            | ทุกคนอยากเพิ่ม service ของตัวเอง |
| `README.md`                     | ตารางแบ่งงานอยู่ในนี้            |
| `.gitignore` · `.gitattributes` | มีคนเพิ่ม pattern                |

**กฎ:** แก้ไฟล์กลาง = แยกเป็น PR เล็กของมันเอง merge ให้ไวที่สุด อย่าปนกับ PR ฟีเจอร์

---

## 🛠 Stack ตามแผนอาจารย์

- **Frontend** Node.js 20 LTS · Next.js · TypeScript · Tailwind · MapLibre GL JS
- **Backend** Python 3.12 · FastAPI · Pydantic · httpx · Tenacity
- **Data** PostgreSQL · Redis · Vector DB
- **Orchestration** Docker Compose _(ยังไม่ได้เขียน อยู่ในเฟส implement)_
- **Monitoring** Prometheus · Grafana · OpenTelemetry

---

## 🆘 ติดปัญหาบ่อย

| อาการ                                              | แก้                                                                                      |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `git switch develop` ขึ้น `pathspec did not match` | ยังไม่มี local develop → `git switch -c develop origin/develop`                          |
| merge แล้วขึ้น CONFLICT                            | เปิดไฟล์ หา `<<<<<<<` เลือกเก็บส่วนที่ถูก ลบเครื่องหมายออก แล้ว `git add` + `git commit` |
| push แล้วขึ้น `rejected`                           | มีคน push ทับ → `git pull` ก่อน แล้ว push อีกครั้ง                                       |
| เผลอ commit `.env`                                 | บอกในกลุ่ม**ทันที** และ **revoke API key ทุกตัว** — ลบ commit ทีหลังไม่พอ                |
| ทำงานผิด branch                                    | `git stash` → `git switch <branch-ถูก>` → `git stash pop`                                |
